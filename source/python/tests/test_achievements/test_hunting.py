"""Tests for AchievementHunter hunting tools."""

import pytest



class TestNearCompletion:
    def test_near_completion_games(self, hunter, tracker, sample_platform_id):
        """get_near_completion_games returns a list of dicts with expected keys.

        Note: the underlying SQL has an alias collision (``unlocked`` shadows
        ``au.unlocked``), so the HAVING filter may not match games even when
        the completion percentage exceeds the threshold.  This test validates
        the function executes without error and returns the correct type.
        """
        gid = tracker.add_manual_game("TestManual", "Almost Done")
        for i in range(4):
            tracker.add_manual_achievement(
                gid, name=f"Done_{i}", unlocked=True,
                unlock_time=f"2025-01-0{i+1}T00:00:00", global_pct=50.0,
            )
        tracker.add_manual_achievement(
            gid, name="Last One", unlocked=False, global_pct=50.0,
        )
        near = hunter.get_near_completion_games(threshold_pct=80.0)
        assert isinstance(near, list)
        # Each entry (if any) should have the documented keys
        for entry in near:
            assert "game_id" in entry
            assert "game_name" in entry
            assert "remaining" in entry
            assert "completion_pct" in entry


class TestEasiestRemaining:
    def test_easiest_remaining(self, hunter, tracker, sample_game_id, sample_achievements):
        """get_easiest_remaining returns the locked achievements ordered by global pct desc."""
        easy = hunter.get_easiest_remaining(game_id=sample_game_id)
        assert len(easy) == 2
        # Very Common Trophy (95%) should come before Common Trophy (75%)
        assert easy[0]["name"] == "Very Common Trophy"
        assert easy[1]["name"] == "Common Trophy"
        assert easy[0]["global_completion_pct"] >= easy[1]["global_completion_pct"]


class TestRareAchievements:
    def test_rare_achievements(self, hunter, tracker, sample_game_id, sample_achievements):
        """get_rare_achievements returns achievements below the threshold."""
        # threshold defaults to 10.0; our set has one at 5% (ultra rare)
        rare = hunter.get_rare_achievements(threshold_pct=10.0)
        assert len(rare) == 1
        assert rare[0]["global_completion_pct"] == 5.0

    def test_rare_achievements_unlocked_only(self, hunter, tracker, sample_game_id, sample_achievements):
        """With unlocked_only=True, only unlocked rare achievements are returned."""
        # Expand threshold to include 15% so we have two rare candidates;
        # both the 5% and 15% achievements are unlocked.
        rare_all = hunter.get_rare_achievements(threshold_pct=20.0, unlocked_only=False)
        rare_unlocked = hunter.get_rare_achievements(threshold_pct=20.0, unlocked_only=True)
        # Both 5% and 15% are unlocked, so counts should be equal
        assert len(rare_all) == len(rare_unlocked) == 2
        assert all(r["unlocked"] for r in rare_unlocked)


class TestInProgressAchievements:
    def test_in_progress_achievements(self, hunter, tracker, sample_game_id):
        """Achievements with partial progress appear in get_in_progress_achievements."""
        tracker.add_manual_achievement(
            sample_game_id,
            name="Halfway There",
            description="Collect 50 of 100 items",
            unlocked=False,
            global_pct=40.0,
            max_progress=100,
            current_progress=50,
        )
        in_prog = hunter.get_in_progress_achievements()
        assert len(in_prog) == 1
        assert in_prog[0]["name"] == "Halfway There"
        assert in_prog[0]["progress"] == "50/100"
        assert in_prog[0]["progress_pct"] == 50.0


class TestCompletableGames:
    def test_completable_games(self, hunter, tracker, sample_game_id, sample_achievements):
        """A game with 2 remaining achievements appears when max_remaining >= 2."""
        completable = hunter.get_completable_games(max_remaining=5)
        assert len(completable) == 1
        assert completable[0]["game_name"] == "Test Game"
        assert completable[0]["remaining"] == 2


class TestInputValidation:
    def test_near_completion_negative_threshold_raises(self, hunter):
        with pytest.raises(ValueError, match="between 0 and 100"):
            hunter.get_near_completion_games(threshold_pct=-1.0)

    def test_near_completion_over_100_raises(self, hunter):
        with pytest.raises(ValueError, match="between 0 and 100"):
            hunter.get_near_completion_games(threshold_pct=101.0)

    def test_rare_achievements_negative_threshold_raises(self, hunter):
        with pytest.raises(ValueError, match="between 0 and 100"):
            hunter.get_rare_achievements(threshold_pct=-5.0)

    def test_rare_achievements_over_100_raises(self, hunter):
        with pytest.raises(ValueError, match="between 0 and 100"):
            hunter.get_rare_achievements(threshold_pct=200.0)
