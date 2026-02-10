"""
Game process detector.

Monitors running system processes to detect when a known game is active,
then enables automatic capture mode.  Falls back gracefully if psutil is
not available (useful for testing without a game running).
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


# Known game executable patterns — partial name match (case-insensitive).
# Extend this list or provide external data via ``add_known_patterns()``.
DEFAULT_KNOWN_PATTERNS: List[str] = [
    r"steam",
    r"epic",
    r"gog",
    r"origin",
    r"battlenet",
    r"ubisoft",
    r"ea_app",
    # Common game engine launchers
    r"unreal",
    r"unity",
    r"godot",
    # Well-known game executables (illustrative)
    r"witcher3",
    r"cyberpunk2077",
    r"eldenring",
    r"baldursgate3",
    r"bg3",
    r"hades",
    r"celeste",
    r"hollow_knight",
    r"factorio",
    r"rimworld",
    r"minecraft",
    r"terraria",
    r"stardewvalley",
    r"among_us",
    r"valheim",
    r"deeprockgalactic",
    r"noita",
    r"returnal",
    r"deathloop",
    r"sekiro",
    r"darksouls",
    r"bloodborne",
    r"nioh",
    r"farcry",
    r"assassinscreed",
    r"hitman",
    r"dishonored",
    r"prey",
    r"bioshock",
    r"deus_ex",
    r"system_shock",
    r"control",
    r"alan_wake",
    r"remedy",
    r"wasteland",
    r"divinity",
    r"pillars_of_eternity",
    r"pathfinder",
    r"tyranny",
    r"planescape",
    r"torment",
]


@dataclass
class RunningGame:
    """Information about a detected running game process."""
    process_id: int
    executable: str
    window_title: str = ""
    game_id: Optional[str] = None    # matched library game id if known
    game_name: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    is_foreground: bool = False

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.started_at


class GameDetector:
    """
    Continuously monitors running processes for known games.

    Usage
    -----
        detector = GameDetector()
        detector.on_game_start(lambda g: print(f"Detected: {g.game_name}"))
        detector.start()
        ...
        detector.stop()
    """

    def __init__(
        self,
        poll_interval: float = 5.0,
        patterns: Optional[List[str]] = None,
    ) -> None:
        self._poll_interval = poll_interval
        self._patterns: List[re.Pattern] = [
            re.compile(p, re.IGNORECASE)
            for p in (patterns or DEFAULT_KNOWN_PATTERNS)
        ]
        self._known_games: Dict[str, str] = {}   # executable_name -> game_name
        self._running: Dict[int, RunningGame] = {}   # pid -> RunningGame
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Callbacks
        self._on_game_start: Optional[Callable[[RunningGame], None]] = None
        self._on_game_stop: Optional[Callable[[RunningGame], None]] = None

        # Simulation mode (for testing without real games)
        self._simulated_game: Optional[RunningGame] = None

    # ------------------------------------------------------------------ #
    # Configuration                                                        #
    # ------------------------------------------------------------------ #

    def add_known_patterns(self, patterns: List[str]) -> None:
        self._patterns.extend(
            re.compile(p, re.IGNORECASE) for p in patterns
        )

    def register_game(self, executable_pattern: str, game_name: str) -> None:
        """Associate an executable pattern with a specific game name."""
        self._known_games[executable_pattern.lower()] = game_name

    def on_game_start(self, callback: Callable[[RunningGame], None]) -> None:
        self._on_game_start = callback

    def on_game_stop(self, callback: Callable[[RunningGame], None]) -> None:
        self._on_game_stop = callback

    # ------------------------------------------------------------------ #
    # Detection logic                                                      #
    # ------------------------------------------------------------------ #

    def detect_running_games(self) -> List[RunningGame]:
        """
        Perform a single scan of running processes.
        Returns list of currently detected games.
        """
        if not _PSUTIL_AVAILABLE:
            return list(self._running.values())

        detected: List[RunningGame] = []
        try:
            for proc in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    name = (proc.info.get("name") or "").lower()
                    exe = (proc.info.get("exe") or "")
                    exe_name = exe.split("/")[-1].split("\\")[-1].lower() if exe else name

                    if self._matches_pattern(exe_name) or self._matches_pattern(name):
                        window_title = ""
                        try:
                            window_title = proc.name()
                        except Exception:
                            pass
                        game_name = self._lookup_game_name(exe_name) or exe_name
                        detected.append(RunningGame(
                            process_id=proc.pid,
                            executable=exe or name,
                            window_title=window_title,
                            game_name=game_name,
                        ))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
        return detected

    def _matches_pattern(self, name: str) -> bool:
        return any(p.search(name) for p in self._patterns)

    def _lookup_game_name(self, exe_name: str) -> Optional[str]:
        for pattern, game_name in self._known_games.items():
            if re.search(pattern, exe_name, re.IGNORECASE):
                return game_name
        return None

    def get_foreground_game(self) -> Optional[RunningGame]:
        """Return the currently active (foreground) game if any."""
        with self._lock:
            for game in self._running.values():
                if game.is_foreground:
                    return game
        return None

    # ------------------------------------------------------------------ #
    # Background monitoring                                                #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Start background monitoring thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="GameDetector"
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop background monitoring thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            self._update_running_games()
            self._stop_event.wait(self._poll_interval)

    def _update_running_games(self) -> None:
        current = {g.process_id: g for g in self.detect_running_games()}

        with self._lock:
            # New games
            for pid, game in current.items():
                if pid not in self._running:
                    self._running[pid] = game
                    if self._on_game_start:
                        try:
                            self._on_game_start(game)
                        except Exception:
                            pass

            # Stopped games
            for pid in list(self._running.keys()):
                if pid not in current:
                    stopped = self._running.pop(pid)
                    if self._on_game_stop:
                        try:
                            self._on_game_stop(stopped)
                        except Exception:
                            pass

    # ------------------------------------------------------------------ #
    # Simulation (for testing without a real game)                        #
    # ------------------------------------------------------------------ #

    def simulate_game_start(
        self,
        game_name: str = "Test Game",
        game_id: Optional[str] = None,
        pid: int = 99999,
    ) -> RunningGame:
        """
        Inject a fake running game for testing purposes.
        """
        game = RunningGame(
            process_id=pid,
            executable=f"{game_name.lower().replace(' ', '_')}.exe",
            window_title=game_name,
            game_id=game_id,
            game_name=game_name,
        )
        with self._lock:
            self._running[pid] = game
            self._simulated_game = game
        if self._on_game_start:
            self._on_game_start(game)
        return game

    def simulate_game_stop(self, pid: int = 99999) -> None:
        """Remove the simulated running game."""
        with self._lock:
            stopped = self._running.pop(pid, None)
            self._simulated_game = None
        if stopped and self._on_game_stop:
            self._on_game_stop(stopped)

    def get_running_games(self) -> List[RunningGame]:
        with self._lock:
            return list(self._running.values())

    def status(self) -> Dict:
        with self._lock:
            return {
                "monitoring": self.is_running(),
                "psutil_available": _PSUTIL_AVAILABLE,
                "running_games": [
                    {
                        "pid": g.process_id,
                        "name": g.game_name,
                        "uptime_seconds": round(g.uptime_seconds, 1),
                    }
                    for g in self._running.values()
                ],
            }
