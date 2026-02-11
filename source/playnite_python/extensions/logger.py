"""
Per-script logging system.

Every loaded script gets its own rotating log file under
``<log_root>/<script_name>.log``.  The :class:`ScriptLogger` exposes the
Playnite-style ``Info/Warning/Error/Debug`` methods used inside scripts, and
also captures ``stdout``/``stderr`` output from the script.

Internal usage (from manager)
------------------------------
>>> from extensions.logger import ScriptLogManager
>>> log_mgr = ScriptLogManager("/var/lib/playnite/logs/scripts")
>>> logger = log_mgr.get_logger("my_script")
>>> logger.Info("Script started")
"""

from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime
from io import StringIO
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Per-script logger (exposed to script code as ``__logger``)
# ---------------------------------------------------------------------------

class ScriptLogger:
    """
    Logger object injected into the script's global namespace as ``__logger``.

    Methods mirror the Playnite PowerShell script logger so that scripts
    ported from C# Playnite can use the same API.
    """

    def __init__(self, name: str, underlying: logging.Logger) -> None:
        self._name = name
        self._log = underlying
        self._history: List[Dict] = []
        self._lock = threading.Lock()

    # Playnite-compatible API
    def Info(self, message: str) -> None:  # noqa: N802
        self._record("INFO", message)
        self._log.info(message)

    def Warning(self, message: str) -> None:  # noqa: N802
        self._record("WARNING", message)
        self._log.warning(message)

    def Error(self, message: str) -> None:  # noqa: N802
        self._record("ERROR", message)
        self._log.error(message)

    def Debug(self, message: str) -> None:  # noqa: N802
        self._record("DEBUG", message)
        self._log.debug(message)

    # Pythonic aliases
    info = Info
    warning = Warning
    error = Error
    debug = Debug

    def _record(self, level: str, message: str) -> None:
        with self._lock:
            self._history.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "level": level,
                    "message": str(message),
                }
            )
            # Keep only the last 1 000 in-memory entries
            if len(self._history) > 1000:
                self._history = self._history[-1000:]

    def get_history(self, level: Optional[str] = None) -> List[Dict]:
        """Return log history, optionally filtered by *level*."""
        with self._lock:
            if level:
                return [e for e in self._history if e["level"] == level.upper()]
            return list(self._history)

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()


# ---------------------------------------------------------------------------
# stdout/stderr capture wrapper
# ---------------------------------------------------------------------------

class _ScriptIO(StringIO):
    """Redirect script print() calls through the script's logger."""

    def __init__(self, logger: ScriptLogger, level: str = "INFO") -> None:
        super().__init__()
        self._logger = logger
        self._level = level
        self._buf: List[str] = []

    def write(self, s: str) -> int:
        # Accumulate until newline
        self._buf.append(s)
        if "\n" in s:
            line = "".join(self._buf).rstrip("\n")
            if line:
                getattr(self._logger, self._level.capitalize())(line)
            self._buf.clear()
        return len(s)

    def flush(self) -> None:
        if self._buf:
            line = "".join(self._buf).rstrip("\n")
            if line:
                getattr(self._logger, self._level.capitalize())(line)
            self._buf.clear()


# ---------------------------------------------------------------------------
# Manager that creates and tracks per-script loggers
# ---------------------------------------------------------------------------

class ScriptLogManager:
    """
    Manages per-script :class:`logging.Logger` instances with rotating file
    handlers.

    Parameters
    ----------
    log_dir:
        Directory where ``<script_name>.log`` files are written.
    max_bytes:
        Rotate log file when it reaches this size.
    backup_count:
        Number of rotated backups to keep.
    """

    def __init__(
        self,
        log_dir: str = "logs/scripts",
        max_bytes: int = 1 * 1024 * 1024,  # 1 MB
        backup_count: int = 3,
    ) -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._loggers: Dict[str, ScriptLogger] = {}

    def get_logger(self, script_name: str) -> ScriptLogger:
        """Return (creating if needed) the :class:`ScriptLogger` for *script_name*."""
        if script_name in self._loggers:
            return self._loggers[script_name]

        log_name = f"script.{script_name}"
        underlying = logging.getLogger(log_name)
        underlying.setLevel(logging.DEBUG)

        # Avoid duplicate handlers on hot-reload
        if not underlying.handlers:
            log_file = self._log_dir / f"{script_name}.log"
            fh = RotatingFileHandler(
                str(log_file),
                maxBytes=self._max_bytes,
                backupCount=self._backup_count,
                encoding="utf-8",
            )
            fmt = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
            fh.setFormatter(fmt)
            underlying.addHandler(fh)

        logger = ScriptLogger(script_name, underlying)
        self._loggers[script_name] = logger
        return logger

    def remove_logger(self, script_name: str) -> None:
        """Flush and remove the logger for *script_name*."""
        if script_name not in self._loggers:
            return
        self._loggers[script_name].clear_history()
        log_name = f"script.{script_name}"
        underlying = logging.getLogger(log_name)
        for h in list(underlying.handlers):
            h.flush()
            underlying.removeHandler(h)
            h.close()
        del self._loggers[script_name]

    def get_log_path(self, script_name: str) -> str:
        return str(self._log_dir / f"{script_name}.log")

    def list_scripts(self) -> List[str]:
        return list(self._loggers.keys())

    def get_io_wrappers(self, logger: ScriptLogger):
        """Return (stdout_wrapper, stderr_wrapper) for use in exec() context."""
        return _ScriptIO(logger, "info"), _ScriptIO(logger, "error")
