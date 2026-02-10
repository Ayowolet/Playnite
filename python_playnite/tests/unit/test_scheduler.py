"""Unit tests for backup/scheduler.py."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from playnite.backup.scheduler import BackupScheduler


@pytest.fixture
def mock_backup_fn():
    return MagicMock()


@pytest.fixture
def scheduler(tmp_db, mock_backup_fn):
    sched = BackupScheduler(db=tmp_db, backup_fn=mock_backup_fn)
    yield sched
    # Shutdown if still running
    if sched._scheduler.running:
        sched.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestBackupSchedulerLifecycle:
    def test_start_and_shutdown(self, scheduler):
        scheduler.start()
        assert scheduler._scheduler.running
        scheduler.shutdown(wait=False)
        assert not scheduler._scheduler.running

    def test_double_start_is_safe(self, scheduler):
        scheduler.start()
        scheduler.start()  # should not raise
        scheduler.shutdown(wait=False)

    def test_shutdown_when_not_running_is_safe(self, scheduler):
        scheduler.shutdown(wait=False)  # never started — should not raise

    def test_start_sets_scheduler_running(self, tmp_db):
        sched = BackupScheduler(db=tmp_db, backup_fn=MagicMock())
        assert not sched._scheduler.running
        sched.start()
        assert sched._scheduler.running
        sched.shutdown(wait=False)


# ---------------------------------------------------------------------------
# schedule_profile
# ---------------------------------------------------------------------------


class TestScheduleProfile:
    def test_schedule_valid_cron(self, scheduler):
        scheduler.start()
        result = scheduler.schedule_profile(1, "0 2 * * *")
        assert result is True
        jobs = scheduler.get_scheduled_jobs()
        assert any(j["profile_id"] == 1 for j in jobs)
        scheduler.shutdown(wait=False)

    def test_schedule_invalid_cron_returns_false(self, scheduler):
        scheduler.start()
        result = scheduler.schedule_profile(1, "not a cron")
        assert result is False
        scheduler.shutdown(wait=False)

    def test_schedule_without_backup_fn_returns_false(self, tmp_db):
        sched = BackupScheduler(db=tmp_db, backup_fn=None)
        sched.start()
        result = sched.schedule_profile(1, "0 2 * * *")
        assert result is False
        sched.shutdown(wait=False)

    def test_reschedule_replaces_existing(self, scheduler):
        scheduler.start()
        scheduler.schedule_profile(1, "0 2 * * *")
        scheduler.schedule_profile(1, "0 3 * * *")  # replace
        jobs = scheduler.get_scheduled_jobs()
        profile_jobs = [j for j in jobs if j["profile_id"] == 1]
        assert len(profile_jobs) == 1
        scheduler.shutdown(wait=False)

    def test_get_scheduled_jobs_returns_list(self, scheduler):
        scheduler.start()
        jobs = scheduler.get_scheduled_jobs()
        assert isinstance(jobs, list)
        scheduler.shutdown(wait=False)

    def test_get_scheduled_jobs_includes_expected_keys(self, scheduler):
        scheduler.start()
        scheduler.schedule_profile(42, "0 4 * * *")
        jobs = scheduler.get_scheduled_jobs()
        assert len(jobs) == 1
        job = jobs[0]
        assert "job_id" in job
        assert "profile_id" in job
        assert "name" in job
        # next_run may be None or an ISO string
        assert "next_run" in job
        scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# remove_schedule
# ---------------------------------------------------------------------------


class TestRemoveSchedule:
    def test_remove_existing_schedule(self, scheduler):
        scheduler.start()
        scheduler.schedule_profile(2, "0 4 * * *")
        removed = scheduler.remove_schedule(2)
        assert removed is True
        jobs = scheduler.get_scheduled_jobs()
        assert not any(j["profile_id"] == 2 for j in jobs)
        scheduler.shutdown(wait=False)

    def test_remove_nonexistent_schedule_returns_false(self, scheduler):
        scheduler.start()
        removed = scheduler.remove_schedule(9999)
        assert removed is False
        scheduler.shutdown(wait=False)

    def test_remove_one_of_multiple_schedules(self, scheduler):
        scheduler.start()
        scheduler.schedule_profile(10, "0 1 * * *")
        scheduler.schedule_profile(11, "0 2 * * *")
        scheduler.remove_schedule(10)
        jobs = scheduler.get_scheduled_jobs()
        assert not any(j["profile_id"] == 10 for j in jobs)
        assert any(j["profile_id"] == 11 for j in jobs)
        scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# load_profiles
# ---------------------------------------------------------------------------


class TestLoadProfiles:
    def test_load_profiles_empty_db(self, scheduler):
        scheduler.start()
        count = scheduler.load_profiles()
        assert count == 0
        scheduler.shutdown(wait=False)

    def test_load_profiles_with_cron(self, scheduler, tmp_db):
        from playnite.database.models import BackupProfile

        with tmp_db.get_session() as session:
            p = BackupProfile(name="nightly", schedule_cron="0 2 * * *")
            session.add(p)
        scheduler.start()
        count = scheduler.load_profiles()
        assert count == 1
        scheduler.shutdown(wait=False)

    def test_load_profiles_with_null_cron_not_counted(self, scheduler, tmp_db):
        from playnite.database.models import BackupProfile

        with tmp_db.get_session() as session:
            p = BackupProfile(name="no-cron", schedule_cron=None)
            session.add(p)
        scheduler.start()
        count = scheduler.load_profiles()
        assert count == 0
        scheduler.shutdown(wait=False)

    def test_load_multiple_profiles(self, scheduler, tmp_db):
        from playnite.database.models import BackupProfile

        with tmp_db.get_session() as session:
            session.add(BackupProfile(name="daily", schedule_cron="0 2 * * *"))
            session.add(BackupProfile(name="weekly", schedule_cron="0 3 * * 0"))
        scheduler.start()
        count = scheduler.load_profiles()
        assert count == 2
        scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# trigger_now
# ---------------------------------------------------------------------------


class TestTriggerNow:
    def test_trigger_now_calls_backup_fn(self, scheduler, mock_backup_fn):
        scheduler.start()
        scheduler.trigger_now(profile_id=1)
        time.sleep(0.5)  # allow the daemon thread to run
        mock_backup_fn.assert_called_once_with(profile_id=1)
        scheduler.shutdown(wait=False)

    def test_trigger_now_without_backup_fn_is_safe(self, tmp_db):
        sched = BackupScheduler(db=tmp_db, backup_fn=None)
        sched.start()
        sched.trigger_now(profile_id=1)  # should not raise
        sched.shutdown(wait=False)

    def test_trigger_now_backup_fn_exception_does_not_propagate(self, tmp_db):
        """Exceptions in the backup callable must be caught internally."""
        failing_fn = MagicMock(side_effect=RuntimeError("boom"))
        sched = BackupScheduler(db=tmp_db, backup_fn=failing_fn)
        sched.start()
        sched.trigger_now(profile_id=99)
        time.sleep(0.3)
        # No exception should escape to the test
        sched.shutdown(wait=False)
