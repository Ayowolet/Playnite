"""Achievement statistics and analytics."""

from __future__ import annotations


from ..database import Database
from ..models import (
    GameCompletionStats,
    OverallStats,
    DifficultyTier,
    AchievementMilestone,
)


class AchievementStats:
    """Achievement statistics calculator."""

    def __init__(self, db: Database):
        self.db = db

    def get_game_stats(self, game_id: int) -> GameCompletionStats:
        """Get completion statistics for a single game."""
        row = self.db.execute(
            """SELECT g.id, g.name as game_name, p.name as platform_name,
                      g.total_achievements,
                      COALESCE(SUM(au.unlocked), 0) as unlocked_count,
                      COUNT(a.id) as total_count,
                      COALESCE(AVG(a.difficulty_score), 0) as avg_difficulty,
                      MAX(au.unlock_date) as latest_unlock
               FROM games g
               JOIN platforms p ON g.platform_id = p.id
               LEFT JOIN achievements a ON a.game_id = g.id
               LEFT JOIN achievement_unlocks au ON au.achievement_id = a.id
               WHERE g.id = ?
               GROUP BY g.id""",
            (game_id,),
        )
        if not row:
            return GameCompletionStats(game_id=game_id)
        r = row[0]
        total = r["total_count"] or 0
        unlocked = r["unlocked_count"] or 0

        rare_rows = self.db.execute(
            """SELECT COUNT(*) as total,
                      COALESCE(SUM(CASE WHEN au.unlocked = 1 THEN 1 ELSE 0 END), 0) as unlocked
               FROM achievements a
               LEFT JOIN achievement_unlocks au ON au.achievement_id = a.id
               WHERE a.game_id = ? AND a.global_completion_pct < 10.0""",
            (game_id,),
        )
        rare_total = rare_rows[0]["total"] if rare_rows else 0
        rare_unlocked = rare_rows[0]["unlocked"] if rare_rows else 0

        return GameCompletionStats(
            game_id=game_id,
            game_name=r["game_name"],
            platform_name=r["platform_name"],
            total_achievements=total,
            unlocked_count=unlocked,
            locked_count=total - unlocked,
            completion_pct=round((unlocked / total * 100) if total > 0 else 0.0, 2),
            rare_unlocked=rare_unlocked,
            rare_total=rare_total,
            avg_difficulty=round(r["avg_difficulty"] or 0, 2),
            latest_unlock=r["latest_unlock"],
        )

    def get_overall_stats(self) -> OverallStats:
        """Get overall achievement statistics across all platforms."""
        totals = self.db.execute(
            """SELECT
                (SELECT COUNT(DISTINCT g.id) FROM games g) as total_games,
                (SELECT COUNT(*) FROM achievements) as total_achievements,
                (SELECT COUNT(*) FROM achievement_unlocks WHERE unlocked = 1) as total_unlocked,
                (SELECT COUNT(*) FROM platforms WHERE enabled = 1) as total_platforms"""
        )
        t = totals[0]
        total_ach = t["total_achievements"] or 0
        total_unlocked = t["total_unlocked"] or 0

        rare_counts = self.db.execute(
            """SELECT
                COALESCE(SUM(CASE WHEN a.global_completion_pct < 10.0 THEN 1 ELSE 0 END), 0) as rare_unlocked,
                COALESCE(SUM(CASE WHEN a.global_completion_pct < 2.0 THEN 1 ELSE 0 END), 0) as ultra_rare_unlocked
               FROM achievements a
               JOIN achievement_unlocks au ON au.achievement_id = a.id
               WHERE au.unlocked = 1"""
        )
        rc = rare_counts[0]

        perfect = self.db.execute(
            """SELECT COUNT(*) as count FROM games g
               WHERE g.total_achievements > 0
               AND g.total_achievements = (
                   SELECT COUNT(*) FROM achievements a
                   JOIN achievement_unlocks au ON au.achievement_id = a.id
                   WHERE a.game_id = g.id AND au.unlocked = 1
               )"""
        )

        game_completions = self.db.execute(
            """SELECT g.id, g.total_achievements,
                      COALESCE(SUM(au.unlocked), 0) as unlocked
               FROM games g
               LEFT JOIN achievements a ON a.game_id = g.id
               LEFT JOIN achievement_unlocks au ON au.achievement_id = a.id
               GROUP BY g.id
               HAVING g.total_achievements > 0"""
        )
        avg_completion = 0.0
        if game_completions:
            pcts = [
                (r["unlocked"] / r["total_achievements"] * 100)
                for r in game_completions if r["total_achievements"] > 0
            ]
            avg_completion = round(sum(pcts) / len(pcts), 2) if pcts else 0.0

        velocity = self.get_unlock_velocity()

        return OverallStats(
            total_games=t["total_games"] or 0,
            total_achievements=total_ach,
            total_unlocked=total_unlocked,
            overall_completion_pct=round((total_unlocked / total_ach * 100) if total_ach > 0 else 0, 2),
            rare_unlocked=rc["rare_unlocked"] or 0,
            ultra_rare_unlocked=rc["ultra_rare_unlocked"] or 0,
            perfect_games=perfect[0]["count"] if perfect else 0,
            avg_game_completion=avg_completion,
            total_platforms=t["total_platforms"] or 0,
            unlock_velocity=velocity,
        )

    def get_unlock_velocity(self, days: int = 30) -> dict:
        """Calculate achievement unlock rate over time periods."""
        periods = {
            "last_7_days": 7,
            "last_30_days": 30,
            "last_90_days": 90,
            "last_365_days": 365,
        }
        result = {}
        for label, d in periods.items():
            if d > days and label != "last_30_days":
                continue
            rows = self.db.execute(
                """SELECT COUNT(*) as count FROM achievement_unlocks
                   WHERE unlocked = 1
                   AND unlock_date >= datetime('now', ?)""",
                (f"-{d} days",),
            )
            count = rows[0]["count"] if rows else 0
            result[label] = {
                "count": count,
                "per_day": round(count / d, 2) if d > 0 else 0,
            }
        return result

    def get_unlock_timeline(self, days: int = 365) -> list[dict]:
        """Get daily unlock counts for timeline visualization."""
        rows = self.db.execute(
            """SELECT date(unlock_date) as day, COUNT(*) as count
               FROM achievement_unlocks
               WHERE unlocked = 1
               AND unlock_date >= datetime('now', ?)
               GROUP BY date(unlock_date)
               ORDER BY day""",
            (f"-{days} days",),
        )
        return [{"date": r["day"], "count": r["count"]} for r in rows]

    def get_difficulty_distribution(self) -> dict:
        """Get distribution of achievements by difficulty tier."""
        rows = self.db.execute(
            """SELECT a.global_completion_pct, au.unlocked
               FROM achievements a
               LEFT JOIN achievement_unlocks au ON au.achievement_id = a.id"""
        )
        dist = {tier.value: {"total": 0, "unlocked": 0} for tier in DifficultyTier}
        for r in rows:
            tier = DifficultyTier.from_global_pct(r["global_completion_pct"] or 0)
            dist[tier.value]["total"] += 1
            if r["unlocked"]:
                dist[tier.value]["unlocked"] += 1
        return dist

    def get_platform_stats(self) -> list[dict]:
        """Get statistics broken down by platform."""
        rows = self.db.execute(
            """SELECT p.id, p.name,
                      COUNT(DISTINCT g.id) as games,
                      COUNT(a.id) as total_achievements,
                      COALESCE(SUM(au.unlocked), 0) as unlocked
               FROM platforms p
               LEFT JOIN games g ON g.platform_id = p.id
               LEFT JOIN achievements a ON a.game_id = g.id
               LEFT JOIN achievement_unlocks au ON au.achievement_id = a.id
               WHERE p.enabled = 1
               GROUP BY p.id"""
        )
        return [
            {
                "platform_id": r["id"],
                "platform_name": r["name"],
                "games": r["games"],
                "total_achievements": r["total_achievements"],
                "unlocked": r["unlocked"],
                "completion_pct": round(
                    (r["unlocked"] / r["total_achievements"] * 100)
                    if r["total_achievements"] > 0 else 0, 2
                ),
            }
            for r in rows
        ]

    def generate_milestone_report(self) -> list[AchievementMilestone]:
        """Get all achievement milestones."""
        rows = self.db.execute(
            "SELECT * FROM achievement_milestones ORDER BY reached_at DESC"
        )
        return [AchievementMilestone.from_row(r) for r in rows]

    def check_milestones(self):
        """Check and record any new milestones."""
        stats = self.get_overall_stats()
        milestones_to_check = [
            (100, "total_100"),
            (500, "total_500"),
            (1000, "total_1000"),
            (5000, "total_5000"),
        ]
        for threshold, mtype in milestones_to_check:
            if stats.total_unlocked >= threshold:
                existing = self.db.execute(
                    "SELECT id FROM achievement_milestones WHERE milestone_type = ?",
                    (mtype,),
                )
                if not existing:
                    self.db.execute_insert(
                        "INSERT INTO achievement_milestones (milestone_type, milestone_value, details) VALUES (?, ?, ?)",
                        (mtype, str(threshold), f'{{"total_unlocked": {stats.total_unlocked}}}'),
                    )

        if stats.perfect_games > 0:
            existing = self.db.execute(
                "SELECT milestone_value FROM achievement_milestones WHERE milestone_type = 'perfect_games'",
            )
            recorded = int(existing[0]["milestone_value"]) if existing else 0
            if stats.perfect_games > recorded:
                if existing:
                    self.db.execute(
                        "UPDATE achievement_milestones SET milestone_value = ?, reached_at = datetime('now') WHERE milestone_type = 'perfect_games'",
                        (str(stats.perfect_games),),
                    )
                else:
                    self.db.execute_insert(
                        "INSERT INTO achievement_milestones (milestone_type, milestone_value) VALUES (?, ?)",
                        ("perfect_games", str(stats.perfect_games)),
                    )
