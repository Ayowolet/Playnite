"""Scheduled backup management."""

from __future__ import annotations

import logging
import threading

from ..database import Database
from .engine import BackupEngine
from .profiles import BackupProfileManager

logger = logging.getLogger(__name__)


class BackupScheduler:
    """Manages automatic scheduled backups."""

    def __init__(self, db: Database, backup_dir: str, data_dir: str | None = None):
        self.db = db
        self.backup_dir = backup_dir
        self.data_dir = data_dir
        self.engine = BackupEngine(db, backup_dir, data_dir)
        self.profiles = BackupProfileManager(db)
        self._scheduler = None
        self._running = False
        self._lock = threading.Lock()

    def start(self):
        """Start the backup scheduler for all profiles with schedules."""
        with self._lock:
            if self._running:
                return

            scheduled_profiles = [
                p for p in self.profiles.list_profiles() if p.schedule_cron
            ]
            if not scheduled_profiles:
                logger.info("No scheduled backup profiles found")
                return

            try:
                from apscheduler.schedulers.background import BackgroundScheduler
                from apscheduler.triggers.cron import CronTrigger

                self._scheduler = BackgroundScheduler()
                for profile in scheduled_profiles:
                    self._scheduler.add_job(
                        self._run_profile_backup,
                        CronTrigger.from_crontab(profile.schedule_cron),
                        args=[profile.id],
                        id=f"backup_profile_{profile.id}",
                    )
                self._scheduler.start()
                self._running = True
                logger.info("Backup scheduler started with %d profile(s)", len(scheduled_profiles))
            except ImportError:
                logger.warning("APScheduler not installed. Scheduled backups unavailable.")

    def stop(self):
        with self._lock:
            self._running = False
            if self._scheduler:
                self._scheduler.shutdown(wait=False)
                self._scheduler = None

    def run_profile_backup(self, profile_name: str, password: str | None = None) -> dict:
        """Manually trigger a backup using a named profile."""
        profile = self.profiles.get_profile(profile_name)
        if not profile:
            raise ValueError(f"Profile '{profile_name}' not found")
        return self._run_profile_backup(profile.id, password)

    def _run_profile_backup(self, profile_id: int, password: str | None = None) -> dict:
        profile = self.profiles.get_profile_by_id(profile_id)
        if not profile:
            raise ValueError(f"Profile ID {profile_id} not found")

        pw = password if profile.encrypt else None

        try:
            # Use the profile's configured destinations (excluding "local" which is implicit)
            dests = [d for d in profile.destinations if d != "local"] or None

            last_full = self.db.execute(
                """SELECT id FROM backups WHERE profile_id = ? AND backup_type = 'full'
                   ORDER BY created_at DESC LIMIT 1""",
                (profile_id,),
            )
            if last_full:
                record = self.engine.create_incremental_backup(
                    parent_backup_id=last_full[0]["id"],
                    password=pw,
                    profile_id=profile_id,
                    destinations=dests,
                )
            else:
                record = self.engine.create_full_backup(
                    password=pw,
                    profile_id=profile_id,
                    destinations=dests,
                )

            self.engine.cleanup_old_backups(
                max_age_days=profile.retention_days,
                max_count=profile.max_backups,
            )

            return record.to_dict()
        except Exception:
            logger.exception("Scheduled backup failed for profile %d (%s)", profile_id, profile.name)
            raise

    def create_pre_update_backup(self, password: str | None = None) -> dict:
        """Create an automatic pre-update backup before major changes."""
        record = self.engine.create_full_backup(
            password=password,
            components=["database", "config"],
        )
        return record.to_dict()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running
