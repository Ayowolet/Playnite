"""Shared pytest fixtures for the gamelibrary test suite."""

import pytest

from gamelibrary.database import Database
from gamelibrary.achievements.tracker import AchievementTracker
from gamelibrary.achievements.stats import AchievementStats
from gamelibrary.achievements.hunting import AchievementHunter
from gamelibrary.achievements.challenge import ChallengeMode
from gamelibrary.achievements.export import AchievementExporter
from gamelibrary.achievements.notifications import NotificationManager
from gamelibrary.backup.engine import BackupEngine
from gamelibrary.backup.restore import RestoreEngine
from gamelibrary.backup.profiles import BackupProfileManager


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary Database instance backed by a file in tmp_path."""
    db_path = tmp_path / "test.db"
    return Database(db_path)


@pytest.fixture
def tracker(tmp_db):
    """AchievementTracker wired to the temporary database."""
    return AchievementTracker(tmp_db)


@pytest.fixture
def stats(tmp_db):
    """AchievementStats wired to the temporary database."""
    return AchievementStats(tmp_db)


@pytest.fixture
def hunter(tmp_db):
    """AchievementHunter wired to the temporary database."""
    return AchievementHunter(tmp_db)


@pytest.fixture
def challenge(tmp_db):
    """ChallengeMode wired to the temporary database."""
    return ChallengeMode(tmp_db)


@pytest.fixture
def exporter(tmp_db):
    """AchievementExporter wired to the temporary database."""
    return AchievementExporter(tmp_db)


@pytest.fixture
def notifications(tmp_db):
    """NotificationManager wired to the temporary database."""
    return NotificationManager(tmp_db)


@pytest.fixture
def backup_engine(tmp_db, tmp_path):
    """BackupEngine with temporary backup and data directories."""
    backup_dir = tmp_path / "backups"
    data_dir = tmp_path / "data"
    return BackupEngine(tmp_db, backup_dir=backup_dir, data_dir=data_dir)


@pytest.fixture
def restore_engine(tmp_db):
    """RestoreEngine wired to the temporary database."""
    return RestoreEngine(tmp_db)


@pytest.fixture
def profile_manager(tmp_db):
    """BackupProfileManager wired to the temporary database."""
    return BackupProfileManager(tmp_db)


@pytest.fixture
def sample_platform_id(tracker):
    """Register a manual platform and return its id."""
    return tracker.register_platform(
        "TestManual", "manual", {"platform_label": "TestManual"}
    )


@pytest.fixture
def sample_game_id(tracker, sample_platform_id):
    """Create a game via tracker.add_manual_game and return its id."""
    return tracker.add_manual_game("TestManual", "Test Game")


@pytest.fixture
def sample_achievements(tracker, sample_game_id):
    """Add 5 achievements (3 unlocked, 2 locked) with varying rarity and return their ids."""
    ach_ids = []

    # Achievement 1 - ultra rare, unlocked
    ach_ids.append(
        tracker.add_manual_achievement(
            sample_game_id,
            name="Ultra Rare Trophy",
            description="Only 5% of players earned this",
            unlocked=True,
            unlock_time="2025-06-01T12:00:00",
            global_pct=5.0,
        )
    )

    # Achievement 2 - rare, unlocked
    ach_ids.append(
        tracker.add_manual_achievement(
            sample_game_id,
            name="Rare Trophy",
            description="Only 15% of players earned this",
            unlocked=True,
            unlock_time="2025-07-15T08:30:00",
            global_pct=15.0,
        )
    )

    # Achievement 3 - uncommon, unlocked
    ach_ids.append(
        tracker.add_manual_achievement(
            sample_game_id,
            name="Uncommon Trophy",
            description="45% of players earned this",
            unlocked=True,
            unlock_time="2025-08-20T18:00:00",
            global_pct=45.0,
        )
    )

    # Achievement 4 - common, locked
    ach_ids.append(
        tracker.add_manual_achievement(
            sample_game_id,
            name="Common Trophy",
            description="75% of players earned this",
            unlocked=False,
            global_pct=75.0,
        )
    )

    # Achievement 5 - very common, locked
    ach_ids.append(
        tracker.add_manual_achievement(
            sample_game_id,
            name="Very Common Trophy",
            description="95% of players earned this",
            unlocked=False,
            global_pct=95.0,
        )
    )

    return ach_ids
