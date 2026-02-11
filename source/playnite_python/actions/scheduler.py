"""
Action scheduler — executes actions at specific times or intervals, or in
response to event triggers.

Schedule types
--------------
* **once** — Run the action once at a specific :class:`datetime`.
* **interval** — Run every N seconds indefinitely.
* **cron**-like — Run daily at a specific hour:minute.
* **event** — Fire when a :class:`~actions.models.TriggerType` event occurs.

The scheduler runs in a background daemon thread.  It evaluates the job queue
every second and dispatches due jobs.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from .models import Action, ActionLog, TriggerType


# ---------------------------------------------------------------------------
# Scheduled job model
# ---------------------------------------------------------------------------

@dataclass
class ScheduledJob:
    """A single job in the scheduler queue."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action_id: str = ""
    schedule_type: str = "once"       # "once" | "interval" | "daily" | "event"
    run_at: Optional[datetime] = None  # for "once" and "daily"
    interval_seconds: float = 0.0      # for "interval"
    trigger: Optional[TriggerType] = None  # for "event"
    hour: int = 0                      # for "daily" (0-23)
    minute: int = 0                    # for "daily" (0-59)
    enabled: bool = True
    last_run: Optional[datetime] = None
    run_count: int = 0

    def is_due(self, now: datetime) -> bool:
        if not self.enabled:
            return False
        if self.schedule_type == "once":
            if self.run_at and now >= self.run_at and self.run_count == 0:
                return True
        elif self.schedule_type == "interval":
            if self.interval_seconds <= 0:
                return False
            if self.last_run is None:
                return True
            return (now - self.last_run).total_seconds() >= self.interval_seconds
        elif self.schedule_type == "daily":
            if self.last_run and self.last_run.date() == now.date():
                return False
            return now.hour == self.hour and now.minute == self.minute
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action_id": self.action_id,
            "schedule_type": self.schedule_type,
            "run_at": self.run_at.isoformat() if self.run_at else None,
            "interval_seconds": self.interval_seconds,
            "trigger": self.trigger.value if self.trigger else None,
            "hour": self.hour,
            "minute": self.minute,
            "enabled": self.enabled,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "run_count": self.run_count,
        }


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class ActionScheduler:
    """
    Background scheduler that dispatches actions based on time or events.

    Parameters
    ----------
    action_runner:
        Callable ``(action_id: str) -> ActionLog`` invoked to run an action.
    """

    def __init__(
        self,
        action_runner: Callable[[str], Optional[ActionLog]],
    ) -> None:
        self._runner = action_runner
        self._jobs: Dict[str, ScheduledJob] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._on_run: List[Callable[[ScheduledJob, Optional[ActionLog]], None]] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background scheduling thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="action-scheduler",
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def schedule_once(
        self,
        action_id: str,
        when: datetime,
    ) -> str:
        """Schedule *action_id* to run once at *when*."""
        job = ScheduledJob(action_id=action_id, schedule_type="once", run_at=when)
        return self._add_job(job)

    def schedule_interval(
        self,
        action_id: str,
        interval: timedelta,
    ) -> str:
        """Schedule *action_id* to run every *interval*."""
        job = ScheduledJob(
            action_id=action_id,
            schedule_type="interval",
            interval_seconds=interval.total_seconds(),
        )
        return self._add_job(job)

    def schedule_daily(
        self,
        action_id: str,
        hour: int,
        minute: int = 0,
    ) -> str:
        """Schedule *action_id* to run once daily at *hour*:*minute* (24h)."""
        job = ScheduledJob(
            action_id=action_id,
            schedule_type="daily",
            hour=hour,
            minute=minute,
        )
        return self._add_job(job)

    def schedule_on_event(
        self,
        action_id: str,
        trigger: TriggerType,
    ) -> str:
        """Schedule *action_id* to run whenever *trigger* fires."""
        job = ScheduledJob(
            action_id=action_id,
            schedule_type="event",
            trigger=trigger,
        )
        return self._add_job(job)

    def cancel(self, job_id: str) -> bool:
        """Remove job *job_id*. Returns *True* if found."""
        with self._lock:
            return self._jobs.pop(job_id, None) is not None

    def enable(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].enabled = True

    def disable(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].enabled = False

    def list_jobs(self) -> List[ScheduledJob]:
        with self._lock:
            return list(self._jobs.values())

    def fire_event(self, trigger: TriggerType) -> int:
        """
        Immediately dispatch all jobs registered for *trigger*.

        Returns the number of jobs fired.
        """
        with self._lock:
            matching = [
                j for j in self._jobs.values()
                if j.schedule_type == "event" and j.trigger == trigger and j.enabled
            ]
        count = 0
        for job in matching:
            self._dispatch(job)
            count += 1
        return count

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_run(self, callback: Callable[[ScheduledJob, Optional[ActionLog]], None]) -> None:
        """
        Register a callback fired after each scheduled job runs.

        Parameters
        ----------
        callback:
            Callable with signature
            ``(job: ScheduledJob, log: Optional[ActionLog]) -> None``.

            *job* is the :class:`ScheduledJob` that was dispatched.
            *log* is the :class:`~actions.models.ActionLog` returned by
            the action runner, or *None* if the runner raised an unhandled
            exception.

        Multiple callbacks can be registered; they are called in
        registration order.  Exceptions raised by a callback are silently
        swallowed to protect the scheduler loop.
        """
        self._on_run.append(callback)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _add_job(self, job: ScheduledJob) -> str:
        with self._lock:
            self._jobs[job.id] = job
        return job.id

    def _run_loop(self) -> None:
        while self._running:
            now = datetime.now()
            with self._lock:
                due_jobs = [j for j in self._jobs.values() if j.is_due(now)]
            for job in due_jobs:
                self._dispatch(job)
            time.sleep(1.0)

    def _dispatch(self, job: ScheduledJob) -> None:
        log: Optional[ActionLog] = None
        try:
            log = self._runner(job.action_id)
        except Exception:  # noqa: BLE001
            pass
        with self._lock:
            if job.id in self._jobs:
                self._jobs[job.id].last_run = datetime.now()
                self._jobs[job.id].run_count += 1
                # Remove one-shot jobs after execution
                if job.schedule_type == "once":
                    del self._jobs[job.id]
        with self._lock:
            callbacks = list(self._on_run)
        for cb in callbacks:
            try:
                cb(job, log)
            except Exception:  # noqa: BLE001
                pass
