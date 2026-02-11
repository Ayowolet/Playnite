"""Per-script logging system with dedicated log files."""

from __future__ import annotations

import logging
import os
from pathlib import Path


class ScriptLogManager:
    """Manages per-script log files and a combined log."""

    def __init__(self, log_dir: str):
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._loggers: dict[str, logging.Logger] = {}
        self._handlers: dict[str, logging.Handler] = {}

        # Combined log for all scripts
        combined_path = self._log_dir / "all_scripts.log"
        self._combined_handler = logging.FileHandler(
            str(combined_path), encoding="utf-8"
        )
        self._combined_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
        )

    def get_logger(self, script_id: str, script_name: str = "") -> logging.Logger:
        """Get or create a logger for a specific script."""
        if script_id in self._loggers:
            return self._loggers[script_id]

        logger = logging.getLogger(f"script.{script_id}")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        # Clear any leftover handlers from a previous load (e.g., after reload)
        for h in list(logger.handlers):
            h.close()
            logger.removeHandler(h)

        # Per-script file handler
        safe_name = script_name or script_id
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in safe_name)
        log_path = self._log_dir / f"{safe_name}.log"
        handler = logging.FileHandler(str(log_path), encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
        )
        logger.addHandler(handler)
        logger.addHandler(self._combined_handler)

        # Console handler for CLI visibility
        console = logging.StreamHandler()
        console.setLevel(logging.WARNING)
        console.setFormatter(
            logging.Formatter("[%(name)s] %(levelname)s: %(message)s")
        )
        logger.addHandler(console)

        self._loggers[script_id] = logger
        self._handlers[script_id] = handler
        return logger

    def get_log_path(self, script_id: str) -> str | None:
        """Return the file path for a script's log, or None if not found."""
        handler = self._handlers.get(script_id)
        if handler and isinstance(handler, logging.FileHandler):
            return handler.baseFilename
        return None

    def get_log_content(self, script_id: str, tail: int = 100) -> list[str]:
        """Return the last N lines from a script's log file."""
        path = self.get_log_path(script_id)
        if not path or not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return lines[-tail:]

    def close_logger(self, script_id: str) -> None:
        """Close and remove the logger and handlers for a script."""
        script_logger = self._loggers.pop(script_id, None)
        handler = self._handlers.pop(script_id, None)
        if script_logger:
            for h in list(script_logger.handlers):
                h.close()
                script_logger.removeHandler(h)
        elif handler:
            handler.close()

    def close_all(self) -> None:
        """Close all script loggers and the combined log handler."""
        for script_id in list(self._loggers.keys()):
            self.close_logger(script_id)
        self._combined_handler.close()
