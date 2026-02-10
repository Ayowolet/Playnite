"""Tests for the AchievementTracker."""




class TestRegisterPlatform:
    def test_register_platform(self, tracker):
        """Registering a new platform returns a positive integer id."""
        pid = tracker.register_platform("MySteam", "manual", {"platform_label": "MySteam"})
        assert isinstance(pid, int)
        assert pid > 0

    def test_register_platform_updates_existing(self, tracker):
        """Registering a platform with the same name returns the existing id and updates it."""
        pid1 = tracker.register_platform("Dup", "manual", {"platform_label": "Dup"})
        pid2 = tracker.register_platform("Dup", "manual", {"platform_label": "DupV2"})
        assert pid1 == pid2


class TestGetPlatforms:
    def test_get_platforms(self, tracker, sample_platform_id):
        """get_platforms returns a list containing the registered platform."""
        platforms = tracker.get_platforms()
        assert len(platforms) >= 1
        names = [p.name for p in platforms]
        assert "TestManual" in names


class TestAddManualGame:
    def test_add_manual_game(self, tracker, sample_platform_id):
        """add_manual_game returns a positive game id and the game is retrievable."""
        gid = tracker.add_manual_game("TestManual", "My Game")
        assert isinstance(gid, int)
        assert gid > 0
        games = tracker.get_games()
        assert any(g.name == "My Game" for g in games)


class TestManualAchievements:
    def test_add_manual_achievement(self, tracker, sample_game_id):
        """Adding a locked manual achievement stores it correctly."""
        aid = tracker.add_manual_achievement(
            sample_game_id,
            name="First Blood",
            description="Win your first match",
            unlocked=False,
            global_pct=60.0,
        )
        assert isinstance(aid, int)
        assert aid > 0
        ach = tracker.get_achievement(aid)
        assert ach is not None
        assert ach.name == "First Blood"
        assert ach.unlocked is False

    def test_add_manual_achievement_unlocked(self, tracker, sample_game_id):
        """Adding an unlocked achievement records the unlock date and state."""
        aid = tracker.add_manual_achievement(
            sample_game_id,
            name="Champion",
            description="Win 10 matches",
            unlocked=True,
            unlock_time="2025-09-01T10:00:00",
            global_pct=25.0,
        )
        ach = tracker.get_achievement(aid)
        assert ach.unlocked is True
        assert ach.unlock_date == "2025-09-01T10:00:00"

    def test_update_manual_achievement_unlock(self, tracker, sample_game_id):
        """Updating an achievement to unlocked changes its state."""
        aid = tracker.add_manual_achievement(
            sample_game_id,
            name="Progress",
            unlocked=False,
            global_pct=50.0,
        )
        tracker.update_manual_achievement(aid, unlocked=True, unlock_time="2025-10-01T00:00:00")
        ach = tracker.get_achievement(aid)
        assert ach.unlocked is True
        assert ach.unlock_date == "2025-10-01T00:00:00"

    def test_update_manual_achievement_progress(self, tracker, sample_game_id):
        """Updating current_progress is reflected in the stored achievement."""
        aid = tracker.add_manual_achievement(
            sample_game_id,
            name="Collector",
            description="Collect 100 items",
            unlocked=False,
            global_pct=40.0,
            max_progress=100,
            current_progress=10,
        )
        tracker.update_manual_achievement(aid, current_progress=50)
        ach = tracker.get_achievement(aid)
        assert ach.current_progress == 50


class TestGetAchievements:
    def test_get_achievements(self, tracker, sample_game_id, sample_achievements):
        """get_achievements returns all 5 achievements for the sample game."""
        achs = tracker.get_achievements(sample_game_id)
        assert len(achs) == 5

    def test_get_achievements_unlocked_only(self, tracker, sample_game_id, sample_achievements):
        """get_achievements with unlocked_only=True returns only the 3 unlocked achievements."""
        achs = tracker.get_achievements(sample_game_id, unlocked_only=True)
        assert len(achs) == 3
        assert all(a.unlocked for a in achs)


class TestRecentUnlocks:
    def test_get_recent_unlocks(self, tracker, sample_game_id, sample_achievements):
        """get_recent_unlocks returns only unlocked achievements with non-null dates."""
        recent = tracker.get_recent_unlocks(limit=10)
        assert len(recent) == 3
        # Most recent first
        assert recent[0]["achievement_name"] == "Uncommon Trophy"
        for r in recent:
            assert r["unlock_date"] is not None
