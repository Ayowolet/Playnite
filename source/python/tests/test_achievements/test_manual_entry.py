"""Tests validating manual achievement entry workflow.

Covers all 8 checklist items:
1. Add a game without API support (e.g., Nintendo Switch)
2. Manually create achievement entries for the game
3. Mark achievements as unlocked manually
4. Set unlock dates manually
5. Verify manually entered achievements appear in statistics
6. Edit manually entered achievement
7. Delete manually entered achievement
8. Verify manual entries are distinguished from API imports
"""

import pytest

from gamelibrary.database import Database
from gamelibrary.achievements.tracker import AchievementTracker
from gamelibrary.achievements.stats import AchievementStats


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "manual_test.db")


@pytest.fixture
def tracker(db):
    return AchievementTracker(db)


@pytest.fixture
def stats(db):
    return AchievementStats(db)


class TestAddGameWithoutAPI:
    """Checklist item 1: Add a game without API support."""

    def test_add_nintendo_switch_game(self, tracker):
        """Can add a game for a platform with no API (Nintendo Switch)."""
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        assert isinstance(game_id, int)
        assert game_id > 0

    def test_manual_platform_auto_registered(self, tracker):
        """Adding a game auto-registers the platform as manual type."""
        tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        platforms = tracker.get_platforms()
        switch = [p for p in platforms if p.name == "Nintendo Switch"]
        assert len(switch) == 1
        assert switch[0].api_type == "manual"

    def test_game_appears_in_list(self, tracker):
        """Manually added game is retrievable via get_games."""
        tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        games = tracker.get_games()
        names = [g.name for g in games]
        assert "Zelda: BOTW" in names

    def test_multiple_games_same_platform(self, tracker):
        """Multiple games can be added to the same manual platform."""
        tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        tracker.add_manual_game("Nintendo Switch", "Mario Odyssey")
        games = tracker.get_games()
        names = [g.name for g in games]
        assert "Zelda: BOTW" in names
        assert "Mario Odyssey" in names


class TestCreateManualAchievements:
    """Checklist item 2: Manually create achievement entries."""

    def test_create_locked_achievement(self, tracker):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "Defeat Ganon", description="Defeat the final boss",
            unlocked=False, global_pct=35.0,
        )
        ach = tracker.get_achievement(ach_id)
        assert ach is not None
        assert ach.name == "Defeat Ganon"
        assert ach.description == "Defeat the final boss"
        assert ach.global_completion_pct == 35.0
        assert ach.unlocked is False

    def test_create_achievement_with_progress(self, tracker):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "All Shrines", description="Complete all 120 shrines",
            unlocked=False, global_pct=8.0,
            max_progress=120, current_progress=80,
        )
        ach = tracker.get_achievement(ach_id)
        assert ach.max_progress == 120
        assert ach.current_progress == 80
        assert ach.progress_pct == pytest.approx(66.67, abs=0.1)

    def test_total_achievements_updated(self, tracker):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        tracker.add_manual_achievement(game_id, "Ach 1", global_pct=50.0)
        tracker.add_manual_achievement(game_id, "Ach 2", global_pct=50.0)
        tracker.add_manual_achievement(game_id, "Ach 3", global_pct=50.0)
        games = tracker.get_games()
        zelda = [g for g in games if g.name == "Zelda: BOTW"][0]
        assert zelda.total_achievements == 3


class TestMarkUnlockedManually:
    """Checklist item 3: Mark achievements as unlocked manually."""

    def test_mark_locked_as_unlocked(self, tracker):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "Defeat Ganon", unlocked=False, global_pct=35.0,
        )
        assert tracker.get_achievement(ach_id).unlocked is False

        tracker.update_manual_achievement(ach_id, unlocked=True)
        ach = tracker.get_achievement(ach_id)
        assert ach.unlocked is True

    def test_create_already_unlocked(self, tracker):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "First Shrine", unlocked=True, global_pct=90.0,
        )
        ach = tracker.get_achievement(ach_id)
        assert ach.unlocked is True

    def test_relock_achievement(self, tracker):
        """Can mark an unlocked achievement back to locked."""
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "Test", unlocked=True, global_pct=50.0,
        )
        tracker.update_manual_achievement(ach_id, unlocked=False)
        ach = tracker.get_achievement(ach_id)
        assert ach.unlocked is False


class TestSetUnlockDates:
    """Checklist item 4: Set unlock dates manually."""

    def test_set_date_at_creation(self, tracker):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "Defeat Ganon", unlocked=True,
            unlock_time="2024-03-15T14:30:00",
            global_pct=35.0,
        )
        ach = tracker.get_achievement(ach_id)
        assert ach.unlock_date == "2024-03-15T14:30:00"

    def test_set_date_via_update(self, tracker):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "Defeat Ganon", unlocked=False, global_pct=35.0,
        )
        tracker.update_manual_achievement(
            ach_id, unlocked=True, unlock_time="2024-06-20T09:00:00",
        )
        ach = tracker.get_achievement(ach_id)
        assert ach.unlock_date == "2024-06-20T09:00:00"

    def test_locked_has_no_date(self, tracker):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "All Shrines", unlocked=False, global_pct=8.0,
        )
        ach = tracker.get_achievement(ach_id)
        assert ach.unlock_date is None


class TestManualInStatistics:
    """Checklist item 5: Verify manually entered achievements appear in statistics."""

    def test_game_stats_include_manual(self, tracker, stats):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        tracker.add_manual_achievement(game_id, "Ach 1", unlocked=True, unlock_time="2024-01-01T00:00:00", global_pct=50.0)
        tracker.add_manual_achievement(game_id, "Ach 2", unlocked=True, unlock_time="2024-01-02T00:00:00", global_pct=30.0)
        tracker.add_manual_achievement(game_id, "Ach 3", unlocked=False, global_pct=10.0)

        game_stats = stats.get_game_stats(game_id)
        assert game_stats.total_achievements == 3
        assert game_stats.unlocked_count == 2
        assert game_stats.locked_count == 1
        assert game_stats.completion_pct == pytest.approx(66.67, abs=0.1)

    def test_overall_stats_include_manual(self, tracker, stats):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        tracker.add_manual_achievement(game_id, "Ach 1", unlocked=True, unlock_time="2024-01-01T00:00:00", global_pct=50.0)
        tracker.add_manual_achievement(game_id, "Ach 2", unlocked=False, global_pct=30.0)

        overall = stats.get_overall_stats()
        assert overall.total_games >= 1
        assert overall.total_achievements >= 2
        assert overall.total_unlocked >= 1

    def test_platform_stats_include_manual(self, tracker, stats):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        tracker.add_manual_achievement(game_id, "Ach 1", unlocked=True, unlock_time="2024-01-01T00:00:00", global_pct=50.0)

        plat_stats = stats.get_platform_stats()
        switch_stats = [p for p in plat_stats if p["platform_name"] == "Nintendo Switch"]
        assert len(switch_stats) == 1
        assert switch_stats[0]["total_achievements"] >= 1
        assert switch_stats[0]["unlocked"] >= 1

    def test_difficulty_distribution_includes_manual(self, tracker, stats):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        tracker.add_manual_achievement(game_id, "Easy", unlocked=True, unlock_time="2024-01-01T00:00:00", global_pct=80.0)
        tracker.add_manual_achievement(game_id, "Hard", unlocked=False, global_pct=3.0)

        dist = stats.get_difficulty_distribution()
        assert dist["common"]["total"] >= 1
        assert dist["very_rare"]["total"] >= 1


class TestEditManualAchievement:
    """Checklist item 6: Edit manually entered achievement."""

    def test_edit_name(self, tracker):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "Old Name", global_pct=50.0,
        )
        tracker.update_manual_achievement(ach_id, name="New Name")
        ach = tracker.get_achievement(ach_id)
        assert ach.name == "New Name"

    def test_edit_description(self, tracker):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "Ach", description="Old desc", global_pct=50.0,
        )
        tracker.update_manual_achievement(ach_id, description="Updated description")
        ach = tracker.get_achievement(ach_id)
        assert ach.description == "Updated description"

    def test_edit_global_pct(self, tracker):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "Ach", global_pct=50.0,
        )
        tracker.update_manual_achievement(ach_id, global_pct=15.0)
        ach = tracker.get_achievement(ach_id)
        assert ach.global_completion_pct == 15.0
        # Difficulty score should also update
        assert ach.difficulty_score == 85.0

    def test_edit_multiple_fields(self, tracker):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "Original", description="Orig desc",
            unlocked=False, global_pct=50.0,
        )
        tracker.update_manual_achievement(
            ach_id, name="Edited", description="Edited desc",
            global_pct=10.0, unlocked=True, unlock_time="2024-12-25T00:00:00",
        )
        ach = tracker.get_achievement(ach_id)
        assert ach.name == "Edited"
        assert ach.description == "Edited desc"
        assert ach.global_completion_pct == 10.0
        assert ach.unlocked is True
        assert ach.unlock_date == "2024-12-25T00:00:00"

    def test_edit_progress(self, tracker):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "Collector", max_progress=100, current_progress=20, global_pct=40.0,
        )
        tracker.update_manual_achievement(ach_id, current_progress=75)
        ach = tracker.get_achievement(ach_id)
        assert ach.current_progress == 75


class TestDeleteManualAchievement:
    """Checklist item 7: Delete manually entered achievement."""

    def test_delete_achievement(self, tracker):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "To Delete", global_pct=50.0,
        )
        assert tracker.get_achievement(ach_id) is not None

        tracker.delete_achievement(ach_id)
        assert tracker.get_achievement(ach_id) is None

    def test_delete_updates_game_count(self, tracker):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        tracker.add_manual_achievement(game_id, "Keep", global_pct=50.0)
        ach2 = tracker.add_manual_achievement(game_id, "Delete", global_pct=50.0)

        games = tracker.get_games()
        zelda = [g for g in games if g.name == "Zelda: BOTW"][0]
        assert zelda.total_achievements == 2

        tracker.delete_achievement(ach2)
        games = tracker.get_games()
        zelda = [g for g in games if g.name == "Zelda: BOTW"][0]
        assert zelda.total_achievements == 1

    def test_delete_removes_unlock_record(self, tracker, db):
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "To Delete", unlocked=True,
            unlock_time="2024-01-01T00:00:00", global_pct=50.0,
        )
        # Verify unlock record exists
        rows = db.execute(
            "SELECT * FROM achievement_unlocks WHERE achievement_id = ?",
            (ach_id,),
        )
        assert len(rows) == 1

        tracker.delete_achievement(ach_id)
        rows = db.execute(
            "SELECT * FROM achievement_unlocks WHERE achievement_id = ?",
            (ach_id,),
        )
        assert len(rows) == 0

    def test_delete_nonexistent_is_safe(self, tracker):
        """Deleting a non-existent achievement should not raise."""
        tracker.delete_achievement(99999)  # Should not raise


class TestManualDistinguishedFromAPI:
    """Checklist item 8: Verify manual entries are distinguished from API imports."""

    def test_manual_source_is_manual(self, tracker):
        """Manual achievements have source='manual'."""
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        ach_id = tracker.add_manual_achievement(
            game_id, "Manual Ach", unlocked=True,
            unlock_time="2024-01-01T00:00:00", global_pct=50.0,
        )
        ach = tracker.get_achievement(ach_id)
        assert ach.source == "manual"

    def test_manual_source_in_recent_unlocks(self, tracker):
        """Recent unlocks from manual entry show source='manual'."""
        game_id = tracker.add_manual_game("Nintendo Switch", "Zelda: BOTW")
        tracker.add_manual_achievement(
            game_id, "Manual Ach", unlocked=True,
            unlock_time="2024-01-01T00:00:00", global_pct=50.0,
        )
        recent = tracker.get_recent_unlocks(limit=10)
        assert len(recent) >= 1
        manual_entries = [r for r in recent if r["source"] == "manual"]
        assert len(manual_entries) >= 1

    def test_api_source_default(self, tracker, db):
        """Achievements inserted via _upsert_unlock without explicit source default to 'api'."""
        from gamelibrary.achievements.platforms.base import PlatformAchievement
        game_id = tracker.add_manual_game("FakePlatform", "API Game")
        pa = PlatformAchievement(
            external_id="api_ach_1",
            name="API Achievement",
            description="From API",
            global_completion_pct=50.0,
            unlocked=True,
            unlock_time="2024-06-01T00:00:00",
        )
        ach_id = tracker._upsert_achievement_def(game_id, pa)
        tracker._upsert_unlock(ach_id, pa)  # source defaults to "api"
        ach = tracker.get_achievement(ach_id)
        assert ach.source == "api"

    def test_manual_and_api_coexist_with_distinct_sources(self, tracker):
        """Both manual and API-sourced achievements exist with correct sources."""
        from gamelibrary.achievements.platforms.base import PlatformAchievement

        game_id = tracker.add_manual_game("TestPlatform", "Mixed Game")

        # Manual entry
        manual_id = tracker.add_manual_achievement(
            game_id, "Manual Entry", unlocked=True,
            unlock_time="2024-01-01T00:00:00", global_pct=50.0,
        )

        # Simulated API entry
        pa = PlatformAchievement(
            external_id="api_ach_mixed",
            name="API Entry",
            description="From API",
            global_completion_pct=50.0,
            unlocked=True,
            unlock_time="2024-06-01T00:00:00",
        )
        api_ach_id = tracker._upsert_achievement_def(game_id, pa)
        tracker._upsert_unlock(api_ach_id, pa)  # source="api"

        manual_ach = tracker.get_achievement(manual_id)
        api_ach = tracker.get_achievement(api_ach_id)

        assert manual_ach.source == "manual"
        assert api_ach.source == "api"
