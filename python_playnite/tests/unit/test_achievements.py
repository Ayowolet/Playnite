"""Unit tests for achievement tracking and calculations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from playnite.achievements.tracker import AchievementTracker
from playnite.database.models import Achievement, Game, UserAchievement


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Difficulty score calculation
# ---------------------------------------------------------------------------


class TestDifficultyScore:
    def test_difficulty_from_high_global_pct(self):
        score = AchievementTracker._calc_difficulty(80.0)
        assert score == pytest.approx(0.2, abs=1e-4)

    def test_difficulty_from_low_global_pct(self):
        score = AchievementTracker._calc_difficulty(5.0)
        assert score == pytest.approx(0.95, abs=1e-4)

    def test_difficulty_zero_pct(self):
        score = AchievementTracker._calc_difficulty(0.0)
        assert score == pytest.approx(1.0)

    def test_difficulty_100_pct(self):
        score = AchievementTracker._calc_difficulty(100.0)
        assert score == pytest.approx(0.0)

    def test_difficulty_none_returns_none(self):
        assert AchievementTracker._calc_difficulty(None) is None


# ---------------------------------------------------------------------------
# Rare achievement identification
# ---------------------------------------------------------------------------


class TestRareAchievement:
    def test_achievement_is_rare(self, tmp_db, tmp_config):
        tracker = AchievementTracker(tmp_config, tmp_db)
        with tmp_db.get_session() as session:
            game = Game(name="Test", platform="steam", platform_game_id="123")
            session.add(game)
            session.flush()
            ach = Achievement(
                game_id=game.id,
                achievement_id="ACH_RARE",
                name="Rare",
                global_percentage=5.0,
                difficulty_score=0.95,
                is_rare=True,
            )
            ua = UserAchievement(
                achievement_id=ach.id if False else 0,  # will be set after add
                platform_user_id="76561198000000001",
                is_unlocked=True,
                unlock_date=_utcnow(),
            )
            session.add(ach)
            session.flush()
            ua.achievement_id = ach.id
            session.add(ua)

        rare = tracker.get_rare_achievements()
        assert len(rare) == 1
        assert rare[0]["achievement"] == "Rare"
        assert rare[0]["global_pct"] == 5.0

    def test_common_achievement_not_rare(self, tmp_db, tmp_config):
        tracker = AchievementTracker(tmp_config, tmp_db)
        with tmp_db.get_session() as session:
            game = Game(name="Common Game", platform="steam", platform_game_id="456")
            session.add(game)
            session.flush()
            ach = Achievement(
                game_id=game.id,
                achievement_id="ACH_COMMON",
                name="Common",
                global_percentage=75.0,
                is_rare=False,
            )
            session.add(ach)
            session.flush()
            ua = UserAchievement(
                achievement_id=ach.id,
                platform_user_id="76561198000000001",
                is_unlocked=True,
            )
            session.add(ua)

        rare = tracker.get_rare_achievements()
        assert rare == []


# ---------------------------------------------------------------------------
# Global stats
# ---------------------------------------------------------------------------


class TestGlobalStats:
    def _populate(self, db):
        """Create 2 games with 3 achievements each (2 unlocked)."""
        with db.get_session() as session:
            for i, platform in enumerate(["steam", "xbox"]):
                game = Game(
                    name=f"Game {i}",
                    platform=platform,
                    platform_game_id=str(i),
                    total_achievements=3,
                )
                session.add(game)
                session.flush()
                for j in range(3):
                    ach = Achievement(
                        game_id=game.id,
                        achievement_id=f"ACH_{i}_{j}",
                        name=f"Ach {j}",
                        global_percentage=50.0 if j < 2 else 5.0,
                        is_rare=(j == 2),
                    )
                    session.add(ach)
                    session.flush()
                    if j < 2:
                        ua = UserAchievement(
                            achievement_id=ach.id,
                            platform_user_id=str(platform),
                            is_unlocked=True,
                            unlock_date=_utcnow(),
                        )
                        session.add(ua)

    def test_global_stats_totals(self, tmp_db, tmp_config):
        self._populate(tmp_db)
        tracker = AchievementTracker(tmp_config, tmp_db)
        stats = tracker.get_global_stats()
        assert stats["total_achievements"] == 6
        assert stats["unlocked"] == 4
        assert stats["locked"] == 2
        assert stats["completion_pct"] == pytest.approx(66.67, abs=0.1)

    def test_platform_breakdown(self, tmp_db, tmp_config):
        self._populate(tmp_db)
        tracker = AchievementTracker(tmp_config, tmp_db)
        stats = tracker.get_global_stats()
        assert "steam" in stats["platforms"]
        assert "xbox" in stats["platforms"]


# ---------------------------------------------------------------------------
# Unlock velocity
# ---------------------------------------------------------------------------


class TestUnlockVelocity:
    def test_velocity_empty_db(self, tmp_db, tmp_config):
        tracker = AchievementTracker(tmp_config, tmp_db)
        v = tracker.get_unlock_velocity(days=30)
        assert v["total"] == 0
        assert v["avg_per_day"] == 0

    def test_velocity_counts_recent_unlocks(self, tmp_db, tmp_config):
        # Insert an achievement unlocked 3 days ago
        now = _utcnow()
        with tmp_db.get_session() as session:
            game = Game(name="G", platform="steam", platform_game_id="9")
            session.add(game)
            session.flush()
            ach = Achievement(game_id=game.id, achievement_id="A1", name="A1")
            session.add(ach)
            session.flush()
            ua = UserAchievement(
                achievement_id=ach.id,
                platform_user_id="76561198000000001",
                is_unlocked=True,
                unlock_date=now - timedelta(days=3),
            )
            session.add(ua)

        tracker = AchievementTracker(tmp_config, tmp_db)
        v = tracker.get_unlock_velocity(days=30)
        assert v["total"] == 1

    def test_velocity_excludes_old_unlocks(self, tmp_db, tmp_config):
        now = _utcnow()
        with tmp_db.get_session() as session:
            game = Game(name="G2", platform="steam", platform_game_id="10")
            session.add(game)
            session.flush()
            ach = Achievement(game_id=game.id, achievement_id="A2", name="A2")
            session.add(ach)
            session.flush()
            ua = UserAchievement(
                achievement_id=ach.id,
                platform_user_id="76561198000000001",
                is_unlocked=True,
                unlock_date=now - timedelta(days=60),
            )
            session.add(ua)

        tracker = AchievementTracker(tmp_config, tmp_db)
        v = tracker.get_unlock_velocity(days=30)
        assert v["total"] == 0


# ---------------------------------------------------------------------------
# Game completion
# ---------------------------------------------------------------------------


class TestGameCompletion:
    def test_full_completion(self, tmp_db, tmp_config):
        with tmp_db.get_session() as session:
            game = Game(name="Completed", platform="steam", platform_game_id="99")
            session.add(game)
            session.flush()
            for i in range(5):
                ach = Achievement(game_id=game.id, achievement_id=f"A{i}", name=f"A{i}")
                session.add(ach)
                session.flush()
                session.add(
                    UserAchievement(
                        achievement_id=ach.id,
                        platform_user_id="76561198000000001",
                        is_unlocked=True,
                    )
                )

        tracker = AchievementTracker(tmp_config, tmp_db)
        completions = tracker.get_game_completions()
        assert len(completions) == 1
        c = completions[0]
        assert c.completion_pct == 100.0
        assert c.remaining == 0

    def test_partial_completion(self, tmp_db, tmp_config):
        with tmp_db.get_session() as session:
            game = Game(name="Partial", platform="steam", platform_game_id="100")
            session.add(game)
            session.flush()
            for i in range(4):
                ach = Achievement(game_id=game.id, achievement_id=f"P{i}", name=f"P{i}")
                session.add(ach)
                session.flush()
                if i < 1:
                    session.add(
                        UserAchievement(
                            achievement_id=ach.id,
                            platform_user_id="76561198000000001",
                            is_unlocked=True,
                        )
                    )

        tracker = AchievementTracker(tmp_config, tmp_db)
        completions = tracker.get_game_completions()
        assert len(completions) == 1
        assert completions[0].completion_pct == 25.0
        assert completions[0].remaining == 3
