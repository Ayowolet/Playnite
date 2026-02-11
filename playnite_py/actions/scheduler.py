"""Action scheduling: run actions at specific times or recurring intervals."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class ScheduledAction:
    """An action scheduled to run at a specific time or interval."""
    id: str = ""
    action_id: str = ""
    game_id: str | None = None
    # One-shot scheduling
    run_at: str = ""  # ISO datetime; empty = recurring only
    # Recurring scheduling
    interval_seconds: int = 0  # 0 = one-shot
    # State
    last_run: str = ""
    next_run: str = ""
    run_count: int = 0
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "id": self.id,
            "action_id": self.action_id,
            "game_id": self.game_id,
            "run_at": self.run_at,
            "interval_seconds": self.interval_seconds,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
            "enabled": self.enabled,
        }


class ActionScheduler:
    """Manages timed and recurring action execution."""

    def __init__(self, execute_callback: Callable[[str, str | None], Any] | None = None):
        """
        Args:
            execute_callback: Called with (action_id, game_id) when a scheduled action fires.
        """
        self._schedules: dict[str, ScheduledAction] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._execute_callback = execute_callback
        self._counter = 0

    def schedule_once(
        self,
        action_id: str,
        run_at: str | datetime,
        game_id: str | None = None,
    ) -> str:
        """Schedule an action to run once at a specific time."""
        if isinstance(run_at, datetime):
            run_at = run_at.isoformat()

        self._counter += 1
        sched_id = f"sched_{self._counter}"
        entry = ScheduledAction(
            id=sched_id,
            action_id=action_id,
            game_id=game_id,
            run_at=run_at,
            next_run=run_at,
        )
        with self._lock:
            self._schedules[sched_id] = entry
        return sched_id

    def schedule_recurring(
        self,
        action_id: str,
        interval_seconds: int,
        game_id: str | None = None,
    ) -> str:
        """Schedule an action to run at a recurring interval."""
        self._counter += 1
        sched_id = f"sched_{self._counter}"
        now = datetime.now(timezone.utc)
        next_dt = datetime.fromtimestamp(
            now.timestamp() + interval_seconds, tz=timezone.utc
        )
        entry = ScheduledAction(
            id=sched_id,
            action_id=action_id,
            game_id=game_id,
            interval_seconds=interval_seconds,
            next_run=next_dt.isoformat(),
        )
        with self._lock:
            self._schedules[sched_id] = entry
        return sched_id

    def cancel(self, schedule_id: str) -> bool:
        """Cancel a scheduled action by ID and return whether it existed."""
        with self._lock:
            return self._schedules.pop(schedule_id, None) is not None

    def get_schedules(self) -> list[dict[str, Any]]:
        """Return all registered schedules as dictionaries."""
        with self._lock:
            return [s.to_dict() for s in self._schedules.values()]

    def start(self) -> None:
        """Start the background scheduler loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the background scheduler loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _scheduler_loop(self) -> None:
        while self._running:
            now = datetime.now(timezone.utc)
            to_run: list[ScheduledAction] = []

            with self._lock:
                for sched in list(self._schedules.values()):
                    if not sched.enabled or not sched.next_run:
                        continue
                    try:
                        next_dt = datetime.fromisoformat(sched.next_run)
                        if next_dt.tzinfo is None:
                            next_dt = next_dt.replace(tzinfo=timezone.utc)
                        if now >= next_dt:
                            to_run.append(sched)
                    except (ValueError, TypeError):
                        continue

            for sched in to_run:
                self._fire_scheduled(sched)

            time.sleep(1)

    def _fire_scheduled(self, sched: ScheduledAction) -> None:
        logger.info("Firing scheduled action %s (action=%s)", sched.id, sched.action_id)

        if self._execute_callback:
            try:
                self._execute_callback(sched.action_id, sched.game_id)
            except Exception as e:
                logger.error("Scheduled action failed: %s", e)

        sched.last_run = datetime.now(timezone.utc).isoformat()
        sched.run_count += 1

        if sched.interval_seconds > 0:
            # Schedule next run
            next_dt = datetime.fromtimestamp(
                datetime.now(timezone.utc).timestamp() + sched.interval_seconds,
                tz=timezone.utc,
            )
            sched.next_run = next_dt.isoformat()
        else:
            # One-shot: remove
            with self._lock:
                self._schedules.pop(sched.id, None)
