"""Automatic achievement sync scheduler."""

from __future__ import annotations

import logging
import threading

from ..database import Database
from ..models import SyncRecord
from .tracker import AchievementTracker
from .notifications import NotificationManager
from .platforms.base import AuthenticationError

logger = logging.getLogger(__name__)


class SyncScheduler:
    """Manages automatic achievement syncing on a schedule."""

    def __init__(self, db: Database, interval_minutes: int = 60):
        self.db = db
        self.interval_minutes = interval_minutes
        self.tracker = AchievementTracker(db)
        self.notifications = NotificationManager(db)
        self._scheduler = None
        self._running = False
        self._lock = threading.Lock()

    def start(self):
        """Start the automatic sync scheduler."""
        with self._lock:
            if self._running:
                return
            try:
                from apscheduler.schedulers.background import BackgroundScheduler
                self._scheduler = BackgroundScheduler()
                self._scheduler.add_job(
                    self.sync_all,
                    "interval",
                    minutes=self.interval_minutes,
                    id="achievement_sync",
                )
                self._scheduler.start()
                self._running = True
                logger.info("Achievement sync scheduler started (interval: %d min)", self.interval_minutes)
            except ImportError:
                logger.warning("APScheduler not installed. Using threading fallback.")
                self._start_threaded()

    def _start_threaded(self):
        """Fallback scheduler using threading.Timer."""
        with self._lock:
            self._running = True
        self._schedule_next()

    def _schedule_next(self):
        with self._lock:
            if not self._running:
                return
        timer = threading.Timer(self.interval_minutes * 60, self._run_and_reschedule)
        timer.daemon = True
        timer.start()

    def _run_and_reschedule(self):
        with self._lock:
            if not self._running:
                return
        self.sync_all()
        self._schedule_next()

    def stop(self):
        """Stop the sync scheduler."""
        with self._lock:
            self._running = False
            if self._scheduler:
                self._scheduler.shutdown(wait=False)
                self._scheduler = None
        logger.info("Achievement sync scheduler stopped")

    def sync_all(self) -> list[dict]:
        """Sync achievements from all enabled platforms."""
        platforms = self.tracker.get_platforms()
        results = []
        for platform in platforms:
            if platform.api_type == "manual":
                continue
            try:
                result = self.tracker.import_achievements(platform.id)
                if result.get("new_unlocks", 0) > 0:
                    self.notifications.notify_new_unlocks(
                        platform.name, result["new_unlocks"]
                    )
                results.append(result)
            except AuthenticationError as e:
                logger.error("Authentication failed for %s: %s", platform.name, e)
                results.append({
                    "platform": platform.name,
                    "status": "auth_failed",
                    "error": str(e),
                })
                self.notifications.notify_auth_failure(platform.name)
            except Exception as e:
                logger.error("Sync failed for %s: %s", platform.name, e)
                results.append({
                    "platform": platform.name,
                    "status": "failed",
                    "error": str(e),
                })
        return results

    def sync_platform(self, platform_id: int) -> dict:
        """Sync achievements from a specific platform."""
        result = self.tracker.import_achievements(platform_id)
        if result.get("new_unlocks", 0) > 0:
            self.notifications.notify_new_unlocks(
                result["platform"], result["new_unlocks"]
            )
        return result

    def get_sync_history(self, limit: int = 20) -> list[SyncRecord]:
        rows = self.db.execute(
            "SELECT * FROM sync_history ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )
        return [SyncRecord.from_row(r) for r in rows]

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running
