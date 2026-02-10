"""Unit tests for achievement statistics calculations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from playnite.achievements.stats import AchievementStats
from playnite.database.models import Achievement, Game, UserAchievement


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _populate_db(db, *, games=2, achs_per_game=5, unlocked_per_game=3):
    """Insert test data and return list of game_ids."""
    game_ids = []
    with db.get_session() as session:
        for i in range(games):
            platform = "steam" if i % 2 == 0 else "xbox"
            game = Game(
                name=f"Game {i}",
                platform=platform,
                platform_game_id=str(i + 100),
                total_achievements=achs_per_game,
            )
            session.add(game)
            session.flush()
            game_ids.append(game.id)
            for j in range(achs_per_game):
                pct = 80.0 if j < 3 else 5.0
                ach = Achievement(
                    game_id=game.id,
                    achievement_id=f"ACH_{i}_{j}",
                    name=f"Ach {i}-{j}",
                    global_percentage=pct,
                    difficulty_score=1.0 - pct / 100.0,
                    is_rare=(pct < 10.0),
                )
                session.add(ach)
                session.flush()
                if j < unlocked_per_game:
                    ua = UserAchievement(
                        achievement_id=ach.id,
                        platform_user_id=platform,
                        is_unlocked=True,
                        unlock_date=_utcnow() - timedelta(days=j),
                    )
                    session.add(ua)
    return game_ids


class TestGameCompletion:
    def test_completion_single_game(self, tmp_db, tmp_config):
        game_ids = _populate_db(tmp_db, games=1, achs_per_game=4, unlocked_per_game=2)
        stats = AchievementStats(tmp_db)
        result = stats.game_completion(game_ids[0], user_id="steam")
        assert result["total"] == 4
        assert result["unlocked"] == 2
        assert result["completion_pct"] == 50.0
        assert not result["is_completed"]

    def test_full_completion(self, tmp_db, tmp_config):
        game_ids = _populate_db(tmp_db, games=1, achs_per_game=3, unlocked_per_game=3)
        stats = AchievementStats(tmp_db)
        result = stats.game_completion(game_ids[0], user_id="steam")
        assert result["is_completed"]
        assert result["completion_pct"] == 100.0

    def test_no_unlocks(self, tmp_db, tmp_config):
        game_ids = _populate_db(tmp_db, games=1, achs_per_game=3, unlocked_per_game=0)
        stats = AchievementStats(tmp_db)
        result = stats.game_completion(game_ids[0], user_id="steam")
        assert result["completion_pct"] == 0.0
        assert result["remaining"] == 3


class TestPlatformStats:
    def test_platform_breakdown(self, tmp_db, tmp_config):
        _populate_db(tmp_db, games=4, achs_per_game=5, unlocked_per_game=3)
        stats = AchievementStats(tmp_db)
        breakdown = stats.platform_stats()
        assert "steam" in breakdown
        assert "xbox" in breakdown
        # Two games per platform
        assert breakdown["steam"]["games"] == 2
        assert breakdown["xbox"]["games"] == 2

    def test_completion_pct_calculated(self, tmp_db, tmp_config):
        _populate_db(tmp_db, games=2, achs_per_game=10, unlocked_per_game=5)
        stats = AchievementStats(tmp_db)
        breakdown = stats.platform_stats()
        for platform_data in breakdown.values():
            assert "completion_pct" in platform_data
            assert 0.0 <= platform_data["completion_pct"] <= 100.0


class TestMilestones:
    def test_global_milestone_tracking(self, tmp_db, tmp_config):
        # Unlock 15 achievements total (10 milestone should be reached)
        _populate_db(tmp_db, games=3, achs_per_game=5, unlocked_per_game=5)
        stats = AchievementStats(tmp_db)
        report = stats.milestone_report()
        assert report["total_unlocked"] == 15
        assert 10 in report["milestones_reached"]
        assert report["next_global_milestone"] == 25

    def test_no_milestones_for_empty_db(self, tmp_db, tmp_config):
        stats = AchievementStats(tmp_db)
        report = stats.milestone_report()
        assert report["total_unlocked"] == 0
        assert report["milestones_reached"] == []


class TestRarityDistribution:
    def test_distribution_buckets(self, tmp_db, tmp_config):
        with tmp_db.get_session() as session:
            game = Game(name="G", platform="steam", platform_game_id="rarity_test")
            session.add(game)
            session.flush()
            percentages = [80.0, 40.0, 15.0, 5.0, 0.5]
            for i, pct in enumerate(percentages):
                ach = Achievement(
                    game_id=game.id,
                    achievement_id=f"R{i}",
                    name=f"R{i}",
                    global_percentage=pct,
                    is_rare=(pct < 10.0),
                )
                session.add(ach)

        stats = AchievementStats(tmp_db)
        dist = stats.rarity_distribution()
        assert dist["common"] == 1      # 80%
        assert dist["uncommon"] == 1    # 40%
        assert dist["rare"] == 1        # 15%
        assert dist["very_rare"] == 1   # 5%
        assert dist["ultra_rare"] == 1  # 0.5%


class TestVelocity:
    def test_velocity_trend_up(self, tmp_db, tmp_config):
        """More unlocks in recent period than previous period."""
        now = _utcnow()
        with tmp_db.get_session() as session:
            game = Game(name="VG", platform="steam", platform_game_id="vel1")
            session.add(game)
            session.flush()
            # Recent: 5 unlocks
            for i in range(5):
                ach = Achievement(game_id=game.id, achievement_id=f"V{i}", name=f"V{i}")
                session.add(ach)
                session.flush()
                ua = UserAchievement(
                    achievement_id=ach.id,
                    platform_user_id="steam",
                    is_unlocked=True,
                    unlock_date=now - timedelta(days=i + 1),
                )
                session.add(ua)
            # Old: 1 unlock
            ach_old = Achievement(game_id=game.id, achievement_id="VOLD", name="VOLD")
            session.add(ach_old)
            session.flush()
            session.add(
                UserAchievement(
                    achievement_id=ach_old.id,
                    platform_user_id="steam",
                    is_unlocked=True,
                    unlock_date=now - timedelta(days=45),
                )
            )

        stats = AchievementStats(tmp_db)
        v = stats.unlock_velocity(days=30)
        assert v["total"] == 5
        assert v["trend"] == "up"

    def test_velocity_flat(self, tmp_db, tmp_config):
        stats = AchievementStats(tmp_db)
        v = stats.unlock_velocity(days=30)
        assert v["trend"] == "flat"


class TestTimeline:
    def test_timeline_groups_by_month(self, tmp_db, tmp_config):
        now = _utcnow()
        with tmp_db.get_session() as session:
            game = Game(name="TG", platform="steam", platform_game_id="tl1")
            session.add(game)
            session.flush()
            dates = [
                now.replace(month=1, day=5),
                now.replace(month=1, day=15),
                now.replace(month=2, day=3),
            ]
            for i, d in enumerate(dates):
                ach = Achievement(game_id=game.id, achievement_id=f"TL{i}", name=f"TL{i}")
                session.add(ach)
                session.flush()
                session.add(
                    UserAchievement(
                        achievement_id=ach.id,
                        platform_user_id="steam",
                        is_unlocked=True,
                        unlock_date=d,
                    )
                )

        stats = AchievementStats(tmp_db)
        tl = stats.timeline()
        months = [entry["month"] for entry in tl]
        assert len(months) >= 2
        # January entries grouped together
        jan_entries = [e for e in tl if e["month"].endswith("-01")]
        assert len(jan_entries) == 1
        assert jan_entries[0]["count"] == 2
