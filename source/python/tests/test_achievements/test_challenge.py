"""Tests for achievement challenge mode module."""

import pytest

from gamelibrary.database import Database
from gamelibrary.achievements.tracker import AchievementTracker
from gamelibrary.achievements.challenge import ChallengeMode


@pytest.fixture
def challenge_setup(tmp_path):
    """Set up challenge mode test environment with seeded data."""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    tracker = AchievementTracker(db)
    challenge = ChallengeMode(db)

    # Register platform and add a game with mixed achievements
    tracker.register_platform("TestManual", "manual", {"platform_label": "Test"})
    gid = tracker.add_manual_game("TestManual", "Challenge Game")

    # Add 10 achievements: 7 unlocked, 3 remaining
    for i in range(7):
        tracker.add_manual_achievement(
            gid, name=f"Unlocked {i+1}", unlocked=True,
            unlock_time=f"2025-01-0{i+1}T00:00:00",
            global_pct=60.0 + i * 5,  # easy: 60-90%
        )
    for i in range(3):
        tracker.add_manual_achievement(
            gid, name=f"Locked {i+1}", unlocked=False,
            global_pct=30.0 + i * 10,  # medium: 30-50%
        )

    return db, tracker, challenge, gid


class TestSuggestChallenges:
    def test_suggest_easy(self, challenge_setup):
        db, tracker, challenge, gid = challenge_setup
        results = challenge.suggest_challenges(difficulty="easy")
        assert isinstance(results, list)
        for r in results:
            assert "game_name" in r
            assert "remaining" in r
            assert "estimated_hours" in r

    def test_suggest_medium(self, challenge_setup):
        db, tracker, challenge, gid = challenge_setup
        results = challenge.suggest_challenges(difficulty="medium")
        assert isinstance(results, list)
        for r in results:
            assert r["difficulty"] == "medium"

    def test_suggest_hard(self, challenge_setup):
        db, tracker, challenge, gid = challenge_setup
        results = challenge.suggest_challenges(difficulty="hard")
        assert isinstance(results, list)

    def test_suggest_limit(self, challenge_setup):
        db, tracker, challenge, gid = challenge_setup
        results = challenge.suggest_challenges(limit=1)
        assert len(results) <= 1

    def test_suggest_empty_db(self, tmp_path):
        db = Database(tmp_path / "empty.db")
        challenge = ChallengeMode(db)
        results = challenge.suggest_challenges()
        assert results == []

    def test_challenge_has_description(self, challenge_setup):
        db, tracker, challenge, gid = challenge_setup
        results = challenge.suggest_challenges(difficulty="medium")
        for r in results:
            assert "challenge_description" in r
            assert len(r["challenge_description"]) > 0


class TestGetDailyChallenge:
    def test_daily_challenge_returns_achievement(self, challenge_setup):
        db, tracker, challenge, gid = challenge_setup
        result = challenge.get_daily_challenge()
        if result:  # May be None if no qualifying achievements
            assert "achievement_id" in result
            assert "name" in result
            assert "game_name" in result
            assert "global_completion_pct" in result

    def test_daily_challenge_empty_db(self, tmp_path):
        db = Database(tmp_path / "empty.db")
        challenge = ChallengeMode(db)
        result = challenge.get_daily_challenge()
        assert result is None

    def test_daily_challenge_only_unlocked_returns_none(self, tmp_path):
        """If all achievements are unlocked, daily challenge should be None."""
        db = Database(tmp_path / "all_unlocked.db")
        tracker = AchievementTracker(db)
        challenge = ChallengeMode(db)
        tracker.register_platform("Test", "manual", {"platform_label": "Test"})
        gid = tracker.add_manual_game("Test", "All Done Game")
        tracker.add_manual_achievement(gid, name="Done", unlocked=True, global_pct=50.0)
        result = challenge.get_daily_challenge()
        assert result is None

    def test_daily_challenge_returns_dict_or_none(self, challenge_setup):
        db, tracker, challenge, gid = challenge_setup
        result = challenge.get_daily_challenge()
        assert result is None or isinstance(result, dict)


class TestEstimateTime:
    def test_estimate_time_easy(self):
        hours = ChallengeMode._estimate_time(3, 80.0)
        assert hours > 0
        assert hours < 10

    def test_estimate_time_hard(self):
        hours = ChallengeMode._estimate_time(10, 5.0)
        assert hours > 0

    def test_estimate_time_zero_remaining(self):
        hours = ChallengeMode._estimate_time(0, 50.0)
        assert hours == 0.0

    def test_harder_takes_longer(self):
        easy = ChallengeMode._estimate_time(5, 80.0)
        hard = ChallengeMode._estimate_time(5, 5.0)
        assert hard > easy


class TestGenerateDescription:
    def test_almost_there(self):
        desc = ChallengeMode._generate_description("Test Game", 2, "easy")
        assert "2" in desc
        assert "Test Game" in desc

    def test_easy_description(self):
        desc = ChallengeMode._generate_description("Test Game", 5, "easy")
        assert "accessible" in desc.lower() or "5" in desc

    def test_hard_description(self):
        desc = ChallengeMode._generate_description("Test Game", 10, "hard")
        assert "challenging" in desc.lower() or "10" in desc

    def test_medium_description(self):
        desc = ChallengeMode._generate_description("Test Game", 8, "medium")
        assert "Test Game" in desc
