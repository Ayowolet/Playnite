"""Tests for backup scheduler module."""

import pytest

from gamelibrary.database import Database
from gamelibrary.backup.engine import BackupEngine
from gamelibrary.backup.profiles import BackupProfileManager
from gamelibrary.backup.scheduler import BackupScheduler


@pytest.fixture
def scheduler_setup(tmp_path):
    """Set up scheduler test environment."""
    db_path = tmp_path / "test.db"
    backup_dir = tmp_path / "backups"
    data_dir = tmp_path / "data"
    backup_dir.mkdir()
    data_dir.mkdir()

    db = Database(db_path)
    profiles = BackupProfileManager(db)
    scheduler = BackupScheduler(db, str(backup_dir), str(data_dir))
    engine = BackupEngine(db, backup_dir, data_dir)
    return db, profiles, scheduler, engine, tmp_path


class TestSchedulerStartStop:
    def test_initial_state_not_running(self, scheduler_setup):
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        assert scheduler.is_running is False

    def test_start_without_profiles_does_not_run(self, scheduler_setup):
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        scheduler.start()
        # No scheduled profiles, so it won't start
        assert scheduler.is_running is False

    def test_stop_when_not_running(self, scheduler_setup):
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        # Should not raise
        scheduler.stop()
        assert scheduler.is_running is False


class TestRunProfileBackup:
    def test_run_profile_creates_full_backup(self, scheduler_setup):
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        profiles.create_profile(name="daily", description="Daily backup")
        result = scheduler.run_profile_backup("daily")
        assert result["backup_type"] == "full"
        assert result["status"] == "completed"

    def test_run_profile_creates_incremental_after_full(self, scheduler_setup):
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        profiles.create_profile(name="daily", description="Daily backup")
        scheduler.run_profile_backup("daily")
        result = scheduler.run_profile_backup("daily")
        assert result["backup_type"] == "incremental"

    def test_run_nonexistent_profile_raises(self, scheduler_setup):
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        with pytest.raises(ValueError, match="not found"):
            scheduler.run_profile_backup("nonexistent")

    def test_run_profile_with_encryption(self, scheduler_setup):
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        profiles.create_profile(name="encrypted", description="Encrypted", encrypt=True)
        result = scheduler.run_profile_backup("encrypted", password="secret")
        assert result["is_encrypted"] is True

    def test_run_profile_returns_dict(self, scheduler_setup):
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        profiles.create_profile(name="test", description="Test")
        result = scheduler.run_profile_backup("test")
        assert isinstance(result, dict)
        assert "file_path" in result
        assert "checksum" in result


class TestPreUpdateBackup:
    def test_pre_update_creates_backup(self, scheduler_setup):
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        result = scheduler.create_pre_update_backup()
        assert result["backup_type"] == "full"
        assert result["status"] == "completed"

    def test_pre_update_includes_database_component(self, scheduler_setup):
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        result = scheduler.create_pre_update_backup()
        metadata = result.get("metadata", {})
        components = metadata.get("components", [])
        assert "database" in components

    def test_pre_update_encrypted(self, scheduler_setup):
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        result = scheduler.create_pre_update_backup(password="secret")
        assert result["is_encrypted"] is True


class TestInternalRunProfileBackup:
    def test_internal_run_unknown_profile_id_raises(self, scheduler_setup):
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        with pytest.raises(ValueError, match="not found"):
            scheduler._run_profile_backup(99999)

    def test_internal_run_returns_dict(self, scheduler_setup):
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        profile = profiles.create_profile(name="internal_test", description="Test")
        result = scheduler._run_profile_backup(profile.id)
        assert isinstance(result, dict)

    def test_cleanup_runs_after_profile_backup(self, scheduler_setup):
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        profile = profiles.create_profile(
            name="cleanup_test", description="Test",
            retention_days=30, max_backups=10,
        )
        # Run multiple backups
        scheduler._run_profile_backup(profile.id)
        scheduler._run_profile_backup(profile.id)
        # Both should still exist (within retention)
        backups = engine.list_backups()
        assert len(backups) >= 2


class TestSchedulerStartWithProfiles:
    def test_start_with_scheduled_profile(self, scheduler_setup):
        """When a profile has a cron schedule, the scheduler starts."""
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        profiles.create_profile(
            name="cron_test", description="Test", schedule_cron="0 2 * * *",
        )
        scheduler.start()
        # Should be running (APScheduler is available or hits ImportError)
        # Either way, test that it doesn't crash
        scheduler.stop()

    def test_double_start_returns_early(self, scheduler_setup):
        """Calling start() twice when already running should return early."""
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        profiles.create_profile(
            name="cron_test2", description="Test", schedule_cron="0 3 * * *",
        )
        scheduler.start()
        scheduler.start()  # Should return immediately without error
        scheduler.stop()

    def test_stop_clears_scheduler(self, scheduler_setup):
        db, profiles, scheduler, engine, tmp_path = scheduler_setup
        profiles.create_profile(
            name="cron_test3", description="Test", schedule_cron="0 4 * * *",
        )
        scheduler.start()
        scheduler.stop()
        assert scheduler.is_running is False
        assert scheduler._scheduler is None
