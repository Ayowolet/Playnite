"""
Process monitor — tracks a game process during play.

Features
--------
* Detect game start by process name or PID.
* Fire ``started``, ``stopped``, ``crashed`` callbacks.
* Optionally auto-restart crashed games.
* Collect CPU/memory statistics.
* Works with or without ``psutil`` (falls back to subprocess polling).
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Process info snapshot
# ---------------------------------------------------------------------------

@dataclass
class ProcessInfo:
    """Point-in-time snapshot of a monitored process."""
    pid: int
    name: str
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    status: str = "running"
    return_code: Optional[int] = None
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None

    @property
    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.stopped_at or datetime.now()
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "cpu_percent": round(self.cpu_percent, 2),
            "memory_mb": round(self.memory_mb, 2),
            "status": self.status,
            "return_code": self.return_code,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class ProcessMonitor:
    """
    Monitors a game process and fires event callbacks.

    Parameters
    ----------
    poll_interval:
        How often (seconds) to poll the process status.
    auto_restart:
        If *True*, attempt to re-launch the process if it crashes
        (non-zero exit code).
    max_restarts:
        Maximum restart attempts before giving up.
    """

    def __init__(
        self,
        poll_interval: float = 1.0,
        auto_restart: bool = False,
        max_restarts: int = 3,
    ) -> None:
        self._poll_interval = poll_interval
        self._auto_restart = auto_restart
        self._max_restarts = max_restarts

        self._pid: Optional[int] = None
        self._process_name: Optional[str] = None
        self._started_at: Optional[datetime] = None
        self._stopped_at: Optional[datetime] = None
        self._return_code: Optional[int] = None
        self._restart_count: int = 0
        self._launch_cmd: Optional[List[str]] = None  # for auto-restart

        self._monitoring = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Callbacks
        self._on_started: List[Callable[[ProcessInfo], None]] = []
        self._on_stopped: List[Callable[[ProcessInfo], None]] = []
        self._on_crashed: List[Callable[[ProcessInfo], None]] = []
        self._on_stats: List[Callable[[ProcessInfo], None]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_monitoring(
        self,
        pid: Optional[int] = None,
        process_name: Optional[str] = None,
        launch_cmd: Optional[List[str]] = None,
    ) -> None:
        """
        Begin monitoring a process.

        Parameters
        ----------
        pid:
            Known PID to attach to.
        process_name:
            Process name to search for (used if *pid* is not known).
        launch_cmd:
            Command used to launch the process (for auto-restart).
        """
        with self._lock:
            if self._monitoring:
                return
            self._pid = pid
            self._process_name = process_name
            self._launch_cmd = launch_cmd
            self._monitoring = True
            self._started_at = datetime.now()
            self._stopped_at = None
            self._return_code = None

        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="process-monitor",
        )
        self._thread.start()

    def stop_monitoring(self) -> None:
        """Signal the monitoring thread to stop."""
        with self._lock:
            self._monitoring = False

    def is_running(self) -> bool:
        """Return *True* if the monitored process appears to be alive."""
        if self._pid is None and self._process_name is None:
            return False
        if self._pid:
            return self._pid_alive(self._pid)
        if self._process_name:
            pid = self._find_pid_by_name(self._process_name)
            return pid is not None
        return False

    def get_info(self) -> Optional[ProcessInfo]:
        """Return the latest :class:`ProcessInfo` snapshot, or *None*."""
        pid = self._pid or (
            self._find_pid_by_name(self._process_name) if self._process_name else None
        )
        if pid is None:
            return None
        return self._snapshot(pid)

    def wait_for_exit(self, timeout: Optional[float] = None) -> Optional[int]:
        """
        Block until the process exits.

        Returns the process return code, or *None* if *timeout* elapses.
        """
        if self._thread:
            self._thread.join(timeout=timeout)
        return self._return_code

    # ------------------------------------------------------------------
    # Event subscriptions
    # ------------------------------------------------------------------

    def on_started(self, callback: Callable[[ProcessInfo], None]) -> None:
        self._on_started.append(callback)

    def on_stopped(self, callback: Callable[[ProcessInfo], None]) -> None:
        self._on_stopped.append(callback)

    def on_crashed(self, callback: Callable[[ProcessInfo], None]) -> None:
        self._on_crashed.append(callback)

    def on_stats(self, callback: Callable[[ProcessInfo], None]) -> None:
        """Fired every poll cycle with a fresh stats snapshot."""
        self._on_stats.append(callback)

    # ------------------------------------------------------------------
    # Monitor loop
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        # Wait for process to appear (if searching by name)
        wait_limit = 30.0  # seconds to wait for process to appear
        waited = 0.0
        while self._monitoring and waited < wait_limit:
            if self._pid or (
                self._process_name and self._find_pid_by_name(self._process_name)
            ):
                break
            time.sleep(0.5)
            waited += 0.5

        if not self._monitoring:
            return

        # Resolve PID if we only had a name
        if not self._pid and self._process_name:
            self._pid = self._find_pid_by_name(self._process_name)

        if not self._pid:
            return  # Could not find process

        # Fire on_started callbacks
        info = self._snapshot(self._pid)
        for cb in self._on_started:
            self._safe_call(cb, info)

        # Poll loop
        while self._monitoring:
            alive = self._pid_alive(self._pid)
            if not alive:
                break
            info = self._snapshot(self._pid)
            for cb in self._on_stats:
                self._safe_call(cb, info)
            time.sleep(self._poll_interval)

        # Process ended
        self._stopped_at = datetime.now()
        self._return_code = self._get_exit_code(self._pid)

        info = ProcessInfo(
            pid=self._pid,
            name=self._process_name or str(self._pid),
            status="stopped",
            return_code=self._return_code,
            started_at=self._started_at,
            stopped_at=self._stopped_at,
        )

        crashed = self._return_code not in (None, 0)
        if crashed:
            for cb in self._on_crashed:
                self._safe_call(cb, info)
            if self._auto_restart and self._restart_count < self._max_restarts and self._launch_cmd:
                self._restart_count += 1
                proc = subprocess.Popen(self._launch_cmd)
                self._pid = proc.pid
                self.start_monitoring(pid=proc.pid, launch_cmd=self._launch_cmd)
                return

        for cb in self._on_stopped:
            self._safe_call(cb, info)
        self._monitoring = False

    # ------------------------------------------------------------------
    # Platform helpers
    # ------------------------------------------------------------------

    def _pid_alive(self, pid: int) -> bool:
        try:
            import psutil  # type: ignore[import]
            return psutil.pid_exists(pid) and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
        except ImportError:
            pass
        # Fallback
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, check=False
            )
            return str(pid) in result.stdout
        else:
            try:
                import os
                os.kill(pid, 0)
                return True
            except (ProcessLookupError, PermissionError):
                return False

    def _find_pid_by_name(self, name: str) -> Optional[int]:
        try:
            import psutil  # type: ignore[import]
            for p in psutil.process_iter(["pid", "name"]):
                if p.info.get("name", "").lower() == name.lower():
                    return p.info["pid"]
        except ImportError:
            pass
        # Fallback
        if sys.platform != "win32":
            result = subprocess.run(
                ["pgrep", "-x", name], capture_output=True, text=True, check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                try:
                    return int(result.stdout.strip().splitlines()[0])
                except ValueError:
                    pass
        return None

    def _snapshot(self, pid: int) -> ProcessInfo:
        info = ProcessInfo(
            pid=pid,
            name=self._process_name or str(pid),
            started_at=self._started_at,
        )
        try:
            import psutil  # type: ignore[import]
            p = psutil.Process(pid)
            info.cpu_percent = p.cpu_percent(interval=None)
            info.memory_mb = p.memory_info().rss / (1024 * 1024)
            info.status = p.status()
            info.name = p.name()
        except (ImportError, Exception):  # noqa: BLE001
            pass
        return info

    def _get_exit_code(self, pid: int) -> Optional[int]:
        try:
            import psutil  # type: ignore[import]
            p = psutil.Process(pid)
            return p.returncode
        except Exception:  # noqa: BLE001
            pass
        return None

    @staticmethod
    def _safe_call(fn: Callable, *args: Any) -> None:
        try:
            fn(*args)
        except Exception:  # noqa: BLE001
            pass
