"""Script execution tracking: history, performance metrics, and statistics."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from playnite_py.utils import BoundedList


@dataclass
class ExecutionRecord:
    """A single script execution record."""
    script_id: str = ""
    script_name: str = ""
    hook_name: str = ""
    success: bool = True
    duration: float = 0.0
    error: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "script_id": self.script_id,
            "script_name": self.script_name,
            "hook_name": self.hook_name,
            "success": self.success,
            "duration": self.duration,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class MetricsTracker:
    """Tracks script execution history and performance metrics."""

    def __init__(self, max_history: int = 10000):
        self._lock = threading.Lock()
        self._history: BoundedList[ExecutionRecord] = BoundedList(max_history)
        # Aggregated stats per script
        self._stats: dict[str, dict[str, Any]] = {}

    def record_execution(
        self,
        script_id: str,
        script_name: str,
        hook_name: str,
        success: bool,
        duration: float,
        error: str = "",
    ) -> ExecutionRecord:
        """Record a script execution and update aggregated statistics."""
        record = ExecutionRecord(
            script_id=script_id,
            script_name=script_name,
            hook_name=hook_name,
            success=success,
            duration=duration,
            error=error,
        )
        with self._lock:
            self._history.append(record)
            self._update_stats(record)
        return record

    def _update_stats(self, record: ExecutionRecord) -> None:
        sid = record.script_id
        if sid not in self._stats:
            self._stats[sid] = {
                "script_id": sid,
                "script_name": record.script_name,
                "total_executions": 0,
                "successful_executions": 0,
                "failed_executions": 0,
                "total_duration": 0.0,
                "min_duration": float("inf"),
                "max_duration": 0.0,
                "last_execution": "",
                "last_error": "",
            }
        stats = self._stats[sid]
        stats["total_executions"] += 1
        if record.success:
            stats["successful_executions"] += 1
        else:
            stats["failed_executions"] += 1
            stats["last_error"] = record.error
        stats["total_duration"] += record.duration
        stats["min_duration"] = min(stats["min_duration"], record.duration)
        stats["max_duration"] = max(stats["max_duration"], record.duration)
        stats["last_execution"] = record.timestamp

    def get_history(
        self,
        script_id: str | None = None,
        hook_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return execution history, optionally filtered by script or hook."""
        with self._lock:
            records = list(self._history)
        if script_id:
            records = [r for r in records if r.script_id == script_id]
        if hook_name:
            records = [r for r in records if r.hook_name == hook_name]
        records = records[-limit:]
        return [r.to_dict() for r in records]

    def get_script_stats(self, script_id: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
        """Return aggregated execution statistics for one or all scripts."""
        with self._lock:
            if script_id:
                stats = self._stats.get(script_id)
                if stats:
                    s = dict(stats)
                    total = s["total_executions"]
                    s["avg_duration"] = s["total_duration"] / total if total > 0 else 0.0
                    if s["min_duration"] == float("inf"):
                        s["min_duration"] = 0.0
                    return s
                return {"script_id": script_id, "total_executions": 0}
            result = []
            for stats in self._stats.values():
                s = dict(stats)
                total = s["total_executions"]
                s["avg_duration"] = s["total_duration"] / total if total > 0 else 0.0
                if s["min_duration"] == float("inf"):
                    s["min_duration"] = 0.0
                result.append(s)
            return result

    def clear_history(self, script_id: str | None = None) -> None:
        """Clear execution history, optionally for a single script."""
        with self._lock:
            if script_id:
                self._history[:] = [r for r in self._history if r.script_id != script_id]
                self._stats.pop(script_id, None)
            else:
                self._history.clear()
                self._stats.clear()


class ExecutionTimer:
    """Context manager for timing script execution."""

    def __init__(self):
        self.duration: float = 0.0
        self._start: float = 0.0

    def __enter__(self) -> ExecutionTimer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        self.duration = time.perf_counter() - self._start
