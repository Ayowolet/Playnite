"""Integrated game launch controller tying together action execution, process
monitoring, and session tracking — analogous to C# GenericPlayController.

Provides a single ``launch()`` call that:
1.  Fires ``on_game_starting`` (cancellable).
2.  Runs pre-launch actions.
3.  Starts the game process (File/URL/Script).
4.  Fires ``on_game_started``.
5.  Monitors the process via the configured tracking mode.
6.  When the process exits, calculates session length.
7.  Fires ``on_game_stopped`` with session length.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse
from dataclasses import dataclass, field
from typing import Any, Callable

from playnite_py.models.action import (
    ActionPhase,
    GameAction,
    GameActionType,
    TrackingMode,
)
from playnite_py.models.game import Game
from playnite_py.models.database import GameDatabase
from playnite_py.actions.monitor import MonitoredProcess, ProcessMonitor
from playnite_py.scripting.events import (
    OnGameStartedEventArgs,
    OnGameStartingEventArgs,
    OnGameStoppedEventArgs,
)

logger = logging.getLogger(__name__)


@dataclass
class LaunchResult:
    """Result of a game launch attempt."""
    success: bool = False
    cancelled: bool = False
    cancelled_by: str = ""
    process_id: int | None = None
    error: str = ""
    session_length: int = 0  # seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "cancelled": self.cancelled,
            "cancelled_by": self.cancelled_by,
            "process_id": self.process_id,
            "error": self.error,
            "session_length": self.session_length,
        }


class GameLauncher:
    """Unified game launch controller.

    Orchestrates the full launch lifecycle:
    pre-launch → start → monitor → stop → post-exit.
    """

    def __init__(
        self,
        database: GameDatabase,
        process_monitor: ProcessMonitor,
        execute_hook: Callable[..., dict[str, Any]] | None = None,
        execute_phase: Callable[..., Any] | None = None,
    ):
        self._db = database
        self._monitor = process_monitor
        # Callback to fire script engine hooks (engine.execute_hook)
        self._execute_hook = execute_hook
        # Callback to run action chain for a phase (chain_executor.execute_phase)
        self._execute_phase = execute_phase

    def launch(
        self,
        game_id: str,
        action: GameAction,
        *,
        extra_vars: dict[str, Any] | None = None,
    ) -> LaunchResult:
        """Execute the full launch lifecycle synchronously.

        Returns a ``LaunchResult`` with session length if the game ran
        to completion, or cancellation/error info otherwise.
        """
        result = LaunchResult()
        game = self._db.get_game(game_id)
        if not game:
            result.error = f"Game '{game_id}' not found"
            return result

        # 1. Fire on_game_starting (cancellable)
        if self._execute_hook:
            hook_result = self._execute_hook(
                "on_game_starting",
                game_id=game_id,
                game=game.to_dict(),
                source_action=action.to_dict(),
            )
            if hook_result.get("cancelled"):
                result.cancelled = True
                result.cancelled_by = hook_result.get("cancelled_by", "")
                # Fire on_game_startup_cancelled
                self._execute_hook(
                    "on_game_startup_cancelled",
                    game_id=game_id,
                    game=game.to_dict(),
                    cancelled_by=result.cancelled_by,
                )
                return result

        # 2. Run pre-launch actions
        if self._execute_phase:
            self._execute_phase(game_id, ActionPhase.PRE_LAUNCH, extra_vars)

        # 3. Start the game process
        pid: int | None = None
        try:
            pid = self._start_process(action, game)
            result.process_id = pid
        except Exception as e:
            result.error = f"Failed to start game: {e}"
            return result

        # 4. Fire on_game_started
        if self._execute_hook:
            self._execute_hook(
                "on_game_started",
                game_id=game_id,
                game=game.to_dict(),
                source_action=action.to_dict(),
                process_id=pid,
            )

        # 5. Monitor the process
        proc = self._monitor.start_monitoring(
            game_id=game_id,
            process_name=action.tracking_path or "",
            pid=pid,
            tracking_mode=action.tracking_mode,
            tracking_path=action.tracking_path or game.install_directory,
            tracking_frequency=action.tracking_frequency,
            initial_tracking_delay=action.initial_tracking_delay,
        )

        # Wait for the process to exit (blocking)
        session_start = time.monotonic()
        while self._monitor.is_running(game_id):
            if proc._cancel_event.is_set():
                break
            time.sleep(action.tracking_frequency / 1000.0)

        session_length = int(time.monotonic() - session_start)
        result.session_length = session_length

        # 6. Run post-exit actions
        if self._execute_phase:
            self._execute_phase(game_id, ActionPhase.POST_EXIT, extra_vars)

        # 7. Fire on_game_stopped
        if self._execute_hook:
            status = self._monitor.get_status(game_id)
            self._execute_hook(
                "on_game_stopped",
                game_id=game_id,
                game=game.to_dict(),
                session_length=session_length,
                exit_code=status.get("exit_code") if status else None,
            )

        self._monitor.stop_monitoring(game_id)
        result.success = True
        return result

    def launch_async(
        self,
        game_id: str,
        action: GameAction,
        *,
        extra_vars: dict[str, Any] | None = None,
        callback: Callable[[LaunchResult], None] | None = None,
    ) -> threading.Thread:
        """Launch in a background thread. ``callback`` is called with the result."""
        def _run() -> None:
            r = self.launch(game_id, action, extra_vars=extra_vars)
            if callback:
                callback(r)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    def cancel(self, game_id: str) -> None:
        """Cancel a running game launch (signals the monitor to stop)."""
        self._monitor.cancel(game_id)

    # ------------------------------------------------------------------
    # Process start by action type
    # ------------------------------------------------------------------

    def _start_process(self, action: GameAction, game: Game) -> int | None:
        """Start the game process based on the action's game_action_type."""
        action_type = action.game_action_type

        if action_type == GameActionType.FILE:
            return self._start_file(action, game)
        elif action_type == GameActionType.URL:
            self._start_url(action)
            return None
        elif action_type == GameActionType.EMULATOR:
            return self._start_emulator(action, game)
        elif action_type == GameActionType.SCRIPT:
            # Script actions don't produce a PID — they run inline
            return None
        else:
            raise ValueError(f"Unsupported action type: {action_type}")

    def _start_file(self, action: GameAction, game: Game) -> int:
        """Start a file/executable process.

        Validates that the executable path exists and is a file before
        launching, and resolves the working directory to an absolute path.
        """
        path = action.path or ""
        if not path:
            raise FileNotFoundError("No executable path specified in action")
        resolved = Path(path).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Executable not found: {path}")

        work_dir = action.working_directory or game.install_directory or "."
        work_dir = str(Path(work_dir).resolve())

        args = [str(v) for v in action.arguments.values()]

        proc = subprocess.Popen(
            [str(resolved)] + args,
            cwd=work_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc.pid

    @staticmethod
    def _start_url(action: GameAction) -> None:
        """Open a URL in the default browser.

        Only ``http`` and ``https`` schemes are allowed to prevent protocol
        handler injection (e.g. ``javascript:``, ``file://``, ``data:``).
        """
        url = action.path or ""
        if not url:
            return
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ("http", "https"):
            raise ValueError(
                f"Unsupported URL scheme '{parsed.scheme}'. "
                "Only http and https URLs are allowed."
            )
        webbrowser.open(url)

    def _start_emulator(self, action: GameAction, game: Game) -> int:
        """Start a game via an emulator. Currently delegates to file start."""
        # Emulator support is placeholder — same as file launch
        return self._start_file(action, game)
