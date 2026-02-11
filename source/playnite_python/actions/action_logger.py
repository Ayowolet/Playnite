"""
Action execution logger.

Persists :class:`~actions.models.ActionLog` entries to a JSON-lines file
(one JSON object per line) and provides a query interface.

The log file grows unboundedly unless :meth:`ActionExecutionLogger.rotate`
is called.  A maximum in-memory cache of ``max_cache`` entries is maintained
for fast querying.
"""

from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

from .models import ActionLog


class ActionExecutionLogger:
    """
    Records action execution history.

    Parameters
    ----------
    log_path:
        Path to the JSONL log file.
    max_cache:
        Maximum number of entries to keep in memory.
    """

    def __init__(
        self,
        log_path: str = "logs/actions.jsonl",
        max_cache: int = 10000,
    ) -> None:
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._max_cache = max_cache
        self._cache: Deque[ActionLog] = deque(maxlen=max_cache)
        self._lock = threading.Lock()
        self._callbacks: List[Callable[[ActionLog], None]] = []

        # Load tail of existing log into cache
        self._load_tail()

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def record(self, log: ActionLog) -> None:
        """Append *log* to the log file and in-memory cache."""
        with self._lock:
            self._cache.append(log)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(log.to_dict()) + "\n")
        for cb in self._callbacks:
            self._safe_call(cb, log)

    def record_many(self, logs: List[ActionLog]) -> None:
        """Batch-append a list of logs."""
        for log in logs:
            self.record(log)

    # ------------------------------------------------------------------
    # Reading / querying
    # ------------------------------------------------------------------

    def get_recent(self, limit: int = 100) -> List[ActionLog]:
        """Return the *limit* most recent log entries."""
        with self._lock:
            items = list(self._cache)
        return items[-limit:]

    def get_for_action(self, action_id: str, limit: int = 50) -> List[ActionLog]:
        with self._lock:
            items = [e for e in self._cache if e.action_id == action_id]
        return items[-limit:]

    def get_for_game(self, game_id: str, limit: int = 50) -> List[ActionLog]:
        with self._lock:
            items = [e for e in self._cache if e.game_id == game_id]
        return items[-limit:]

    def get_failures(self, limit: int = 50) -> List[ActionLog]:
        with self._lock:
            items = [e for e in self._cache if not e.success]
        return items[-limit:]

    def query(
        self,
        action_id: Optional[str] = None,
        game_id: Optional[str] = None,
        success: Optional[bool] = None,
        after: Optional[datetime] = None,
        before: Optional[datetime] = None,
        limit: int = 200,
    ) -> List[ActionLog]:
        """Flexible query with optional filters."""
        with self._lock:
            items = list(self._cache)
        if action_id:
            items = [e for e in items if e.action_id == action_id]
        if game_id:
            items = [e for e in items if e.game_id == game_id]
        if success is not None:
            items = [e for e in items if e.success == success]
        if after:
            items = [e for e in items if e.started_at >= after]
        if before:
            items = [e for e in items if e.started_at <= before]
        return items[-limit:]

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self, action_id: Optional[str] = None) -> Dict[str, Any]:
        """Return aggregate statistics for an action or the whole log."""
        entries = self.get_for_action(action_id, limit=10000) if action_id else self.get_recent(10000)
        if not entries:
            return {}
        total = len(entries)
        successes = sum(1 for e in entries if e.success)
        durations = [e.duration_ms for e in entries]
        return {
            "total_executions": total,
            "success_rate": round(successes / total * 100, 1) if total else 0,
            "failure_count": total - successes,
            "avg_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0,
            "max_duration_ms": round(max(durations), 2) if durations else 0,
            "min_duration_ms": round(min(durations), 2) if durations else 0,
        }

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def rotate(self, keep_last: int = 1000) -> int:
        """
        Truncate the log file to the last *keep_last* entries.

        Returns the number of entries removed.
        """
        with self._lock:
            if not self._path.exists():
                return 0
            lines: List[str] = []
            with open(self._path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        lines.append(line)
            removed = max(0, len(lines) - keep_last)
            if removed > 0:
                kept = lines[-keep_last:]
                with open(self._path, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(kept) + "\n")
            return removed

    def clear(self) -> None:
        """Remove all log entries from disk and memory."""
        with self._lock:
            self._cache.clear()
            if self._path.exists():
                self._path.unlink()

    # ------------------------------------------------------------------
    # Change callbacks
    # ------------------------------------------------------------------

    def on_entry(self, callback: Callable[[ActionLog], None]) -> None:
        self._callbacks.append(callback)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_tail(self) -> None:
        if not self._path.exists():
            return
        with open(self._path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        for line in lines[-self._max_cache:]:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                log = ActionLog(**{
                    k: v for k, v in d.items()
                    if k in ActionLog.__dataclass_fields__
                })
                if isinstance(log.started_at, str):
                    log.started_at = datetime.fromisoformat(log.started_at)
                if log.finished_at and isinstance(log.finished_at, str):
                    log.finished_at = datetime.fromisoformat(log.finished_at)
                self._cache.append(log)
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _safe_call(fn: Callable, *args: Any) -> None:
        try:
            fn(*args)
        except Exception:  # noqa: BLE001
            pass
