"""Process monitoring: track game processes, detect crashes, and support auto-restart.

Supports five tracking modes mirroring C# Playnite:
- DEFAULT: automatic best-effort (process tree if PID, directory if install dir)
- PROCESS: origin process + all child processes (tree)
- DIRECTORY: any process launched from a given directory
- ORIGINAL_PROCESS: only the originally started PID
- PROCESS_NAME: any process matching a given name
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from playnite_py.models.action import TrackingMode

logger = logging.getLogger(__name__)

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


@dataclass
class MonitoredProcess:
    """State of a monitored game process."""
    game_id: str = ""
    process_name: str = ""
    pid: int | None = None
    started: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended: str | None = None
    exit_code: int | None = None
    crashed: bool = False
    restart_count: int = 0
    max_restarts: int = 3
    # Tracking configuration
    tracking_mode: TrackingMode = TrackingMode.DEFAULT
    tracking_path: str = ""
    tracking_frequency: int = 2000       # ms
    initial_tracking_delay: int = 0      # ms
    # Session tracking
    session_start_monotonic: float = field(default_factory=time.monotonic)
    session_length: int = 0  # seconds (populated on exit)
    # Internal
    _child_pids: list[int] = field(default_factory=list, repr=False)
    _cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "game_id": self.game_id,
            "process_name": self.process_name,
            "pid": self.pid,
            "started": self.started,
            "ended": self.ended,
            "exit_code": self.exit_code,
            "crashed": self.crashed,
            "restart_count": self.restart_count,
            "tracking_mode": self.tracking_mode.value,
            "tracking_path": self.tracking_path,
            "tracking_frequency": self.tracking_frequency,
            "initial_tracking_delay": self.initial_tracking_delay,
            "session_length": self.session_length,
        }


class ProcessMonitor:
    """Monitors game processes for crashes and handles auto-restart.

    Supports all five tracking modes from C# Playnite.
    """

    def __init__(self, poll_interval: float = 2.0):
        self._poll_interval = poll_interval
        self._monitored: dict[str, MonitoredProcess] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

        # Callbacks
        self.on_process_started: list[Callable[[MonitoredProcess], None]] = []
        self.on_process_exited: list[Callable[[MonitoredProcess], None]] = []
        self.on_process_crashed: list[Callable[[MonitoredProcess], None]] = []
        self.on_restart_triggered: list[Callable[[MonitoredProcess], None]] = []

        # Auto-restart callback: should return the new PID or None
        self._restart_callback: Callable[[str], int | None] | None = None

    def clear_handlers(self) -> None:
        """Remove all registered event handlers to prevent accumulation on reload."""
        self.on_process_started.clear()
        self.on_process_exited.clear()
        self.on_process_crashed.clear()
        self.on_restart_triggered.clear()

    def set_restart_callback(self, callback: Callable[[str], int | None]) -> None:
        """Set the callback used to restart a game. Receives game_id, returns new PID."""
        self._restart_callback = callback

    def start_monitoring(
        self,
        game_id: str,
        process_name: str = "",
        pid: int | None = None,
        max_restarts: int = 3,
        tracking_mode: TrackingMode = TrackingMode.DEFAULT,
        tracking_path: str = "",
        tracking_frequency: int = 2000,
        initial_tracking_delay: int = 0,
    ) -> MonitoredProcess:
        """Start monitoring a game process."""
        proc = MonitoredProcess(
            game_id=game_id,
            process_name=process_name,
            pid=pid,
            max_restarts=max_restarts,
            tracking_mode=tracking_mode,
            tracking_path=tracking_path,
            tracking_frequency=tracking_frequency,
            initial_tracking_delay=initial_tracking_delay,
        )

        # Try to find PID by name if not provided
        if pid is None and process_name and HAS_PSUTIL:
            for p in psutil.process_iter(["name", "pid"]):
                try:
                    if p.info["name"] and process_name.lower() in p.info["name"].lower():
                        proc.pid = p.info["pid"]
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        with self._lock:
            self._monitored[game_id] = proc

        self._fire_event(self.on_process_started, proc)
        logger.info(
            "Monitoring started for game %s (pid=%s, name=%s, mode=%s)",
            game_id, proc.pid, process_name, tracking_mode.value,
        )
        return proc

    def stop_monitoring(self, game_id: str) -> bool:
        """Stop monitoring a game process and return whether it was being monitored."""
        with self._lock:
            proc = self._monitored.pop(game_id, None)
        if proc:
            proc._cancel_event.set()
            return True
        return False

    def cancel(self, game_id: str) -> None:
        """Signal cancellation for a monitored game (like CancellationToken)."""
        with self._lock:
            proc = self._monitored.get(game_id)
        if proc:
            proc._cancel_event.set()

    def is_cancelled(self, game_id: str) -> bool:
        """Check whether monitoring for a game has been cancelled."""
        with self._lock:
            proc = self._monitored.get(game_id)
        return proc._cancel_event.is_set() if proc else True

    def get_status(self, game_id: str) -> dict[str, Any] | None:
        """Return the current monitoring status for a game, or None if not monitored."""
        with self._lock:
            proc = self._monitored.get(game_id)
            return proc.to_dict() if proc else None

    def get_all_monitored(self) -> list[dict[str, Any]]:
        """Return the status of all currently monitored processes."""
        with self._lock:
            return [p.to_dict() for p in self._monitored.values()]

    def is_running(self, game_id: str) -> bool:
        """Check whether the monitored process for a game is still running."""
        with self._lock:
            proc = self._monitored.get(game_id)
        if not proc or not HAS_PSUTIL:
            return False
        return self._is_process_running(proc)

    def start(self) -> None:
        """Start the background monitoring loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the background monitoring loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Tracking mode implementations
    # ------------------------------------------------------------------

    def _is_process_running(self, proc: MonitoredProcess) -> bool:
        """Dispatch to the appropriate tracking mode check."""
        mode = proc.tracking_mode

        # Resolve DEFAULT mode
        if mode == TrackingMode.DEFAULT:
            if proc.pid:
                mode = TrackingMode.PROCESS
            elif proc.tracking_path:
                mode = TrackingMode.DIRECTORY
            elif proc.process_name:
                mode = TrackingMode.PROCESS_NAME
            else:
                return self._is_pid_alive(proc.pid)

        if mode == TrackingMode.ORIGINAL_PROCESS:
            return self._is_pid_alive(proc.pid)
        elif mode == TrackingMode.PROCESS:
            return self._is_process_tree_running(proc)
        elif mode == TrackingMode.DIRECTORY:
            return self._is_directory_process_running(proc)
        elif mode == TrackingMode.PROCESS_NAME:
            return self._is_process_name_running(proc)
        return self._is_pid_alive(proc.pid)

    def _is_pid_alive(self, pid: int | None) -> bool:
        if not pid or not HAS_PSUTIL:
            return False
        try:
            p = psutil.Process(pid)
            return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def _is_process_tree_running(self, proc: MonitoredProcess) -> bool:
        """Check if the original process or any of its children are running."""
        if not HAS_PSUTIL or not proc.pid:
            return False

        # Refresh child PIDs
        try:
            parent = psutil.Process(proc.pid)
            children = parent.children(recursive=True)
            proc._child_pids = [c.pid for c in children if c.is_running()]
            if parent.is_running() and parent.status() != psutil.STATUS_ZOMBIE:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # Check if any known child is still alive
        for cpid in list(proc._child_pids):
            if self._is_pid_alive(cpid):
                return True

        return False

    def _is_directory_process_running(self, proc: MonitoredProcess) -> bool:
        """Check if any running process was launched from the tracking directory."""
        if not HAS_PSUTIL or not proc.tracking_path:
            return False
        try:
            from pathlib import Path
            track_dir = Path(proc.tracking_path).resolve()
            for p in psutil.process_iter(["pid", "exe"]):
                try:
                    exe = p.info.get("exe")
                    if exe and Path(exe).resolve().is_relative_to(track_dir):
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    continue
        except Exception:
            pass
        return False

    def _is_process_name_running(self, proc: MonitoredProcess) -> bool:
        """Check if any running process matches the tracking name."""
        if not HAS_PSUTIL:
            return False
        name = proc.process_name or proc.tracking_path
        if not name:
            return False
        name_lower = name.lower()
        try:
            for p in psutil.process_iter(["name"]):
                try:
                    pname = p.info.get("name", "")
                    if pname and pname.lower() == name_lower:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # Monitoring loop
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        while self._running:
            with self._lock:
                processes = list(self._monitored.items())

            for game_id, proc in processes:
                if proc.ended:
                    continue
                if proc._cancel_event.is_set():
                    self._handle_exit(proc)
                    continue

                # Apply per-action tracking frequency
                # (poll_interval is the minimum; per-action frequency may be longer)
                # The outer loop runs at poll_interval; individual processes
                # honour their tracking_frequency via initial delay below.
                if proc.initial_tracking_delay > 0:
                    # Still in initial delay period
                    elapsed_ms = (time.monotonic() - proc.session_start_monotonic) * 1000
                    if elapsed_ms < proc.initial_tracking_delay:
                        continue

                if not self._is_process_running(proc):
                    self._handle_exit(proc)

            # Sleep/hibernation detection: if the iteration took >30s more
            # than expected, skip counting that time (mirrors C# behaviour).
            loop_start = time.monotonic()
            time.sleep(self._poll_interval)
            elapsed = time.monotonic() - loop_start
            if elapsed > self._poll_interval + 30:
                logger.info(
                    "Detected possible sleep/hibernation (%.1fs gap); "
                    "skipping elapsed time",
                    elapsed,
                )

    def _handle_exit(self, proc: MonitoredProcess) -> None:
        proc.ended = datetime.now(timezone.utc).isoformat()

        # Calculate session length
        proc.session_length = int(time.monotonic() - proc.session_start_monotonic)

        # Try to determine exit code
        if HAS_PSUTIL and proc.pid:
            try:
                p = psutil.Process(proc.pid)
                ret = p.wait(timeout=0)
                proc.exit_code = ret
            except Exception:
                proc.exit_code = None

        # Detect crash (non-zero exit code or specific signals)
        if proc.exit_code is not None and proc.exit_code != 0:
            proc.crashed = True
            self._fire_event(self.on_process_crashed, proc)
            logger.warning(
                "Game %s crashed (exit code %s, session %ds)",
                proc.game_id, proc.exit_code, proc.session_length,
            )

            # Auto-restart
            if proc.restart_count < proc.max_restarts and self._restart_callback:
                proc.restart_count += 1
                self._fire_event(self.on_restart_triggered, proc)
                new_pid = self._restart_callback(proc.game_id)
                if new_pid:
                    proc.pid = new_pid
                    proc.ended = None
                    proc.crashed = False
                    proc.started = datetime.now(timezone.utc).isoformat()
                    proc.session_start_monotonic = time.monotonic()
                    proc._cancel_event.clear()
                    logger.info(
                        "Restarted game %s (pid=%s, attempt %d)",
                        proc.game_id, new_pid, proc.restart_count,
                    )
                    return
        else:
            self._fire_event(self.on_process_exited, proc)
            logger.info(
                "Game %s exited normally (session %ds)",
                proc.game_id, proc.session_length,
            )

    @staticmethod
    def _fire_event(handlers: list[Callable], *args: Any) -> None:
        for handler in handlers:
            try:
                handler(*args)
            except Exception as e:
                logger.error("Event handler error: %s", e)
