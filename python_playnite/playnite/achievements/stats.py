"""Achievement statistics calculations."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func

from playnite.database.models import Achievement, Game, UserAchievement

if TYPE_CHECKING:
    from playnite.database.connection import DatabaseManager


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AchievementStats:
    """All statistics derived from the achievements database."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Per-game statistics
    # ------------------------------------------------------------------

    def game_completion(self, game_id: int, user_id: str = "steam") -> dict:
        """Return completion stats for a single game."""
        with self._db.get_session() as session:
            game = session.get(Game, game_id)
            if game is None:
                return {}
            total = len(game.achievements)
            unlocked_rows = [
                ua
                for ach in game.achievements
                for ua in ach.user_achievements
                if ua.platform_user_id == user_id and ua.is_unlocked
            ]
            unlocked = len(unlocked_rows)
            difficulties = [
                a.difficulty_score
                for a in game.achievements
                if a.difficulty_score is not None
            ]
            avg_diff = sum(difficulties) / len(difficulties) if difficulties else None
            return {
                "game_id": game_id,
                "name": game.name,
                "platform": game.platform,
                "total": total,
                "unlocked": unlocked,
                "remaining": total - unlocked,
                "completion_pct": round(unlocked / total * 100, 2) if total else 0.0,
                "avg_difficulty": round(avg_diff, 3) if avg_diff is not None else None,
                "is_completed": unlocked == total and total > 0,
            }

    # ------------------------------------------------------------------
    # Per-platform statistics
    # ------------------------------------------------------------------

    def platform_stats(self) -> dict[str, dict]:
        """Return stats grouped by platform."""
        by_platform: dict[str, dict] = defaultdict(
            lambda: {
                "games": 0,
                "total_achievements": 0,
                "unlocked": 0,
                "rare_unlocked": 0,
                "completed_games": 0,
            },
        )
        with self._db.get_session() as session:
            games = session.query(Game).all()
            for game in games:
                p = game.platform
                by_platform[p]["games"] += 1
                total = len(game.achievements)
                by_platform[p]["total_achievements"] += total
                for ach in game.achievements:
                    for ua in ach.user_achievements:
                        if ua.is_unlocked:
                            by_platform[p]["unlocked"] += 1
                            if ach.is_rare:
                                by_platform[p]["rare_unlocked"] += 1
                # Check game completion
                game_unlocked = sum(
                    1
                    for ach in game.achievements
                    for ua in ach.user_achievements
                    if ua.is_unlocked
                )
                if total > 0 and game_unlocked == total:
                    by_platform[p]["completed_games"] += 1

        result = {}
        for platform, data in by_platform.items():
            total = data["total_achievements"]
            data["completion_pct"] = (
                round(data["unlocked"] / total * 100, 2) if total else 0.0
            )
            result[platform] = dict(data)
        return result

    # ------------------------------------------------------------------
    # Milestone detection
    # ------------------------------------------------------------------

    MILESTONE_TOTALS = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
    MILESTONE_COMPLETION = [10, 25, 50, 75, 100]  # % per game

    def milestone_report(self) -> dict:
        """Generate a milestone progress report."""
        game_milestones: list[dict] = []
        with self._db.get_session() as session:
            total_unlocked = (
                session.query(func.count(UserAchievement.id))
                .filter(UserAchievement.is_unlocked == True)  # noqa: E712
                .scalar()
                or 0
            )
            total_games = session.query(func.count(Game.id)).scalar() or 0
            games = session.query(Game).all()

            # Per-game completion milestones — must be computed inside session
            for game in games:
                total = len(game.achievements)
                if total == 0:
                    continue
                unlocked = sum(
                    1
                    for ach in game.achievements
                    for ua in ach.user_achievements
                    if ua.is_unlocked
                )
                pct = round(unlocked / total * 100, 1)
                reached_pct = [m for m in self.MILESTONE_COMPLETION if pct >= m]
                next_pct = next(
                    (m for m in self.MILESTONE_COMPLETION if pct < m), None,
                )
                if reached_pct or next_pct:
                    game_milestones.append(
                        {
                            "game": game.name,
                            "platform": game.platform,
                            "completion_pct": pct,
                            "milestones_reached": reached_pct,
                            "next_milestone": next_pct,
                            "remaining_for_next": (
                                max(0, round((next_pct / 100) * total - unlocked))
                                if next_pct
                                else 0
                            ),
                        },
                    )

        # Global milestones computed after session closes (uses only scalar values)
        reached = [m for m in self.MILESTONE_TOTALS if total_unlocked >= m]
        next_milestone = next(
            (m for m in self.MILESTONE_TOTALS if total_unlocked < m), None,
        )

        return {
            "total_unlocked": total_unlocked,
            "milestones_reached": reached,
            "next_global_milestone": next_milestone,
            "remaining_for_next": max(0, (next_milestone or 0) - total_unlocked)
            if next_milestone
            else 0,
            "total_games": total_games,
            "game_milestones": game_milestones,
        }

    # ------------------------------------------------------------------
    # Rarity analysis
    # ------------------------------------------------------------------

    def rarity_distribution(self) -> dict:
        """Distribute all achievements into rarity buckets."""
        buckets = {
            "common": (50.0, 100.0),
            "uncommon": (25.0, 50.0),
            "rare": (10.0, 25.0),
            "very_rare": (1.0, 10.0),
            "ultra_rare": (0.0, 1.0),
        }
        with self._db.get_session() as session:
            achievements = session.query(Achievement).all()

        counts: dict[str, int] = dict.fromkeys(buckets, 0)
        counts["unknown"] = 0
        for ach in achievements:
            if ach.global_percentage is None:
                counts["unknown"] += 1
                continue
            for label, (lo, hi) in buckets.items():
                if lo <= ach.global_percentage <= hi:
                    counts[label] += 1
                    break
        return counts

    # ------------------------------------------------------------------
    # Velocity helpers
    # ------------------------------------------------------------------

    def unlock_velocity(self, days: int = 30) -> dict:
        since = _utcnow() - timedelta(days=days)
        with self._db.get_session() as session:
            rows = (
                session.query(
                    func.date(UserAchievement.unlock_date).label("day"),
                    func.count().label("cnt"),
                )
                .filter(
                    UserAchievement.is_unlocked == True,  # noqa: E712
                    UserAchievement.unlock_date >= since,
                )
                .group_by("day")
                .order_by("day")
                .all()
            )
        daily: dict[str, int] = {str(r.day): r.cnt for r in rows}
        total = sum(daily.values())
        prev_start = since - timedelta(days=days)
        with self._db.get_session() as session:
            prev_total = (
                session.query(func.count(UserAchievement.id))
                .filter(
                    UserAchievement.is_unlocked == True,  # noqa: E712
                    UserAchievement.unlock_date >= prev_start,
                    UserAchievement.unlock_date < since,
                )
                .scalar()
                or 0
            )
        trend = "up" if total > prev_total else ("down" if total < prev_total else "flat")
        return {
            "period_days": days,
            "total": total,
            "avg_per_day": round(total / days, 2) if days else 0,
            "daily": daily,
            "previous_period_total": prev_total,
            "trend": trend,
        }

    # ------------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------------

    def timeline(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict]:
        """Return all unlocks in a date range, grouped by month."""
        monthly: dict[str, int] = defaultdict(int)
        with self._db.get_session() as session:
            query = session.query(UserAchievement).filter(
                UserAchievement.is_unlocked == True,  # noqa: E712
                UserAchievement.unlock_date.isnot(None),
            )
            if start_date:
                query = query.filter(UserAchievement.unlock_date >= start_date)
            if end_date:
                query = query.filter(UserAchievement.unlock_date <= end_date)
            rows = query.all()

        for ua in rows:
            if ua.unlock_date:
                key = ua.unlock_date.strftime("%Y-%m")
                monthly[key] += 1

        return [
            {"month": k, "count": v}
            for k, v in sorted(monthly.items())
        ]
