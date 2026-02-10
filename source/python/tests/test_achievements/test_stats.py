"""Tests for AchievementStats."""


from gamelibrary.models import DifficultyTier


class TestGameStats:
    def test_get_game_stats(self, stats, tracker, sample_game_id, sample_achievements):
        """get_game_stats returns correct completion counts for the sample game."""
        gs = stats.get_game_stats(sample_game_id)
        assert gs.game_name == "Test Game"
        assert gs.total_achievements == 5
        assert gs.unlocked_count == 3
        assert gs.locked_count == 2
        assert gs.completion_pct == 60.0

    def test_get_game_stats_empty(self, stats, tracker, sample_game_id):
        """get_game_stats for a game with no achievements returns zero counts."""
        # sample_game_id exists but has no achievements yet (no sample_achievements fixture)
        gs = stats.get_game_stats(sample_game_id)
        assert gs.total_achievements == 0
        assert gs.unlocked_count == 0
        assert gs.completion_pct == 0.0


class TestOverallStats:
    def test_get_overall_stats(self, stats, tracker, sample_game_id, sample_achievements):
        """get_overall_stats counts totals across all games."""
        overall = stats.get_overall_stats()
        assert overall.total_games == 1
        assert overall.total_achievements == 5
        assert overall.total_unlocked == 3
        assert overall.overall_completion_pct == 60.0

    def test_get_overall_stats_counts_correctly(
        self, stats, tracker, sample_platform_id, sample_game_id, sample_achievements
    ):
        """Adding a second game updates totals accurately."""
        gid2 = tracker.add_manual_game("TestManual", "Second Game")
        tracker.add_manual_achievement(gid2, name="A1", unlocked=True, unlock_time="2025-01-01T00:00:00", global_pct=50.0)
        tracker.add_manual_achievement(gid2, name="A2", unlocked=False, global_pct=50.0)

        overall = stats.get_overall_stats()
        assert overall.total_games == 2
        assert overall.total_achievements == 7
        assert overall.total_unlocked == 4


class TestVelocityAndTimeline:
    def test_get_unlock_velocity(self, stats, tracker, sample_game_id, sample_achievements):
        """get_unlock_velocity returns a dict with at least the last_30_days key."""
        velocity = stats.get_unlock_velocity()
        assert "last_30_days" in velocity
        assert "count" in velocity["last_30_days"]
        assert "per_day" in velocity["last_30_days"]

    def test_get_unlock_timeline(self, stats, tracker, sample_game_id, sample_achievements):
        """get_unlock_timeline returns a list (may be empty if unlock dates are old)."""
        timeline = stats.get_unlock_timeline(days=365)
        assert isinstance(timeline, list)


class TestDifficultyDistribution:
    def test_get_difficulty_distribution(self, stats, tracker, sample_game_id, sample_achievements):
        """get_difficulty_distribution returns counts for every DifficultyTier."""
        dist = stats.get_difficulty_distribution()
        assert set(dist.keys()) == {tier.value for tier in DifficultyTier}
        # We have one achievement at 5% (very_rare), one at 15% (rare),
        # one at 45% (uncommon), one at 75% (common), one at 95% (common)
        assert dist["very_rare"]["total"] == 1
        assert dist["rare"]["total"] == 1
        assert dist["uncommon"]["total"] == 1
        assert dist["common"]["total"] == 2


class TestPlatformStats:
    def test_get_platform_stats(self, stats, tracker, sample_platform_id, sample_game_id, sample_achievements):
        """get_platform_stats includes the test platform with correct totals."""
        pstats = stats.get_platform_stats()
        assert len(pstats) >= 1
        entry = next(p for p in pstats if p["platform_name"] == "TestManual")
        assert entry["total_achievements"] == 5
        assert entry["unlocked"] == 3


class TestMilestones:
    def test_check_milestones(self, stats, tmp_db, tracker, sample_game_id):
        """check_milestones records a milestone once the threshold is hit."""
        # Add enough unlocked achievements to cross the 100 milestone
        for i in range(100):
            tracker.add_manual_achievement(
                sample_game_id,
                name=f"Ach_{i}",
                unlocked=True,
                unlock_time=f"2025-01-01T00:{i % 60:02d}:00",
                global_pct=50.0,
            )
        stats.check_milestones()
        rows = tmp_db.execute(
            "SELECT * FROM achievement_milestones WHERE milestone_type = 'total_100'"
        )
        assert len(rows) == 1

    def test_milestone_report(self, stats, tmp_db):
        """generate_milestone_report returns an empty list when no milestones exist."""
        report = stats.generate_milestone_report()
        assert isinstance(report, list)
        assert len(report) == 0
