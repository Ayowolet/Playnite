"""Tests for achievement sync scheduler module."""

import threading

import pytest

from gamelibrary.database import Database
from gamelibrary.achievements.sync import SyncScheduler
from gamelibrary.achievements.tracker import AchievementTracker


@pytest.fixture
def sync_setup(tmp_path):
    """Set up sync scheduler test environment."""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    scheduler = SyncScheduler(db, interval_minutes=1)
    tracker = AchievementTracker(db)
    return db, scheduler, tracker


class TestSyncSchedulerInitialState:
    def test_not_running_initially(self, sync_setup):
        db, scheduler, tracker = sync_setup
        assert scheduler.is_running is False

    def test_has_interval(self, sync_setup):
        db, scheduler, tracker = sync_setup
        assert scheduler.interval_minutes == 1

    def test_has_lock(self, sync_setup):
        db, scheduler, tracker = sync_setup
        assert hasattr(scheduler, "_lock")
        assert isinstance(scheduler._lock, type(threading.Lock()))


class TestSyncStartStop:
    def test_start_threaded_fallback(self, sync_setup):
        """Without APScheduler, should use threaded fallback."""
        db, scheduler, tracker = sync_setup
        scheduler.start()
        assert scheduler.is_running is True
        scheduler.stop()
        assert scheduler.is_running is False

    def test_stop_when_not_running(self, sync_setup):
        db, scheduler, tracker = sync_setup
        scheduler.stop()
        assert scheduler.is_running is False

    def test_double_start_is_idempotent(self, sync_setup):
        db, scheduler, tracker = sync_setup
        scheduler.start()
        scheduler.start()  # Should not raise
        assert scheduler.is_running is True
        scheduler.stop()

    def test_start_stop_cycle(self, sync_setup):
        db, scheduler, tracker = sync_setup
        scheduler.start()
        assert scheduler.is_running is True
        scheduler.stop()
        assert scheduler.is_running is False
        scheduler.start()
        assert scheduler.is_running is True
        scheduler.stop()

    def test_stop_clears_scheduler_ref(self, sync_setup):
        db, scheduler, tracker = sync_setup
        scheduler.start()
        scheduler.stop()
        assert scheduler._scheduler is None
        assert scheduler.is_running is False

    def test_schedule_next_when_not_running(self, sync_setup):
        """_schedule_next should exit early if not running."""
        db, scheduler, tracker = sync_setup
        scheduler._running = False
        scheduler._schedule_next()  # Should not raise

    def test_run_and_reschedule_when_not_running(self, sync_setup):
        """_run_and_reschedule should exit early if not running."""
        db, scheduler, tracker = sync_setup
        scheduler._running = False
        scheduler._run_and_reschedule()  # Should not raise


class TestSyncAll:
    def test_sync_all_with_no_platforms(self, sync_setup):
        db, scheduler, tracker = sync_setup
        results = scheduler.sync_all()
        assert results == []

    def test_sync_all_skips_manual_platforms(self, sync_setup):
        db, scheduler, tracker = sync_setup
        tracker.register_platform("TestManual", "manual", {"platform_label": "Test"})
        results = scheduler.sync_all()
        assert results == []

    def test_sync_all_returns_list(self, sync_setup):
        db, scheduler, tracker = sync_setup
        results = scheduler.sync_all()
        assert isinstance(results, list)


class TestSyncPlatform:
    def test_sync_platform_manual(self, sync_setup):
        db, scheduler, tracker = sync_setup
        pid = tracker.register_platform("TestManual", "manual", {"platform_label": "Test"})
        result = scheduler.sync_platform(pid)
        assert result["status"] == "completed"
        assert result["platform"] == "TestManual"

    def test_sync_nonexistent_platform_raises(self, sync_setup):
        db, scheduler, tracker = sync_setup
        with pytest.raises(ValueError):
            scheduler.sync_platform(99999)


class TestSyncHistory:
    def test_empty_history(self, sync_setup):
        db, scheduler, tracker = sync_setup
        history = scheduler.get_sync_history()
        assert history == []

    def test_history_after_sync(self, sync_setup):
        db, scheduler, tracker = sync_setup
        pid = tracker.register_platform("TestManual", "manual", {"platform_label": "Test"})
        scheduler.sync_platform(pid)
        history = scheduler.get_sync_history()
        assert len(history) >= 1
        assert history[0].status == "completed"


class TestThreadSafety:
    def test_concurrent_start_stop(self, sync_setup):
        """Test that concurrent start/stop doesn't cause race conditions."""
        db, scheduler, tracker = sync_setup
        errors = []

        def start_stop():
            try:
                scheduler.start()
                scheduler.stop()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=start_stop) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert errors == [], f"Thread safety errors: {errors}"

    def test_is_running_property_thread_safe(self, sync_setup):
        db, scheduler, tracker = sync_setup
        scheduler.start()
        results = []

        def check_running():
            results.append(scheduler.is_running)

        threads = [threading.Thread(target=check_running) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        scheduler.stop()
        assert all(isinstance(r, bool) for r in results)
