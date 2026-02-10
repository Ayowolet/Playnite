"""Achievement hunting tools - find completable games and easy achievements."""

from __future__ import annotations

from ..database import Database


class AchievementHunter:
    """Tools for identifying completable achievements and games."""

    def __init__(self, db: Database):
        self.db = db

    def get_near_completion_games(self, threshold_pct: float = 80.0) -> list[dict]:
        """Find games where user is close to 100% completion."""
        if not (0.0 <= threshold_pct <= 100.0):
            raise ValueError(f"threshold_pct must be between 0 and 100, got {threshold_pct}")
        rows = self.db.execute(
            """SELECT g.id, g.name as game_name, p.name as platform_name,
                      g.total_achievements,
                      COALESCE(SUM(au.unlocked), 0) as unlocked,
                      COUNT(a.id) as total_count
               FROM games g
               JOIN platforms p ON g.platform_id = p.id
               JOIN achievements a ON a.game_id = g.id
               LEFT JOIN achievement_unlocks au ON au.achievement_id = a.id
               GROUP BY g.id
               HAVING total_count > 0
               AND (CAST(unlocked AS REAL) / total_count * 100) >= ?
               AND unlocked < total_count
               ORDER BY (CAST(unlocked AS REAL) / total_count) DESC""",
            (threshold_pct,),
        )
        return [
            {
                "game_id": r["id"],
                "game_name": r["game_name"],
                "platform": r["platform_name"],
                "unlocked": r["unlocked"],
                "total": r["total_count"],
                "completion_pct": round(r["unlocked"] / r["total_count"] * 100, 2),
                "remaining": r["total_count"] - r["unlocked"],
            }
            for r in rows
        ]

    def get_easiest_remaining(self, game_id: int | None = None, limit: int = 20) -> list[dict]:
        """Find easiest locked achievements (highest global completion %)."""
        query = """
            SELECT a.id, a.name, a.description, a.global_completion_pct,
                   a.difficulty_score, a.max_progress,
                   COALESCE(au.current_progress, 0) as current_progress,
                   g.name as game_name, p.name as platform_name
            FROM achievements a
            LEFT JOIN achievement_unlocks au ON au.achievement_id = a.id
            JOIN games g ON a.game_id = g.id
            JOIN platforms p ON g.platform_id = p.id
            WHERE (au.unlocked IS NULL OR au.unlocked = 0)
        """
        params: list = []
        if game_id:
            query += " AND a.game_id = ?"
            params.append(game_id)
        query += " ORDER BY a.global_completion_pct DESC LIMIT ?"
        params.append(limit)

        rows = self.db.execute(query, tuple(params))
        return [
            {
                "achievement_id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "game_name": r["game_name"],
                "platform": r["platform_name"],
                "global_completion_pct": r["global_completion_pct"],
                "difficulty_score": r["difficulty_score"],
                "progress": f"{r['current_progress']}/{r['max_progress']}" if r["max_progress"] > 0 else "N/A",
            }
            for r in rows
        ]

    def get_rare_achievements(self, threshold_pct: float = 10.0, unlocked_only: bool = False) -> list[dict]:
        """Find rare achievements (low global completion %)."""
        if not (0.0 <= threshold_pct <= 100.0):
            raise ValueError(f"threshold_pct must be between 0 and 100, got {threshold_pct}")
        query = """
            SELECT a.id, a.name, a.description, a.global_completion_pct,
                   a.difficulty_score, g.name as game_name, p.name as platform_name,
                   COALESCE(au.unlocked, 0) as unlocked, au.unlock_date
            FROM achievements a
            LEFT JOIN achievement_unlocks au ON au.achievement_id = a.id
            JOIN games g ON a.game_id = g.id
            JOIN platforms p ON g.platform_id = p.id
            WHERE a.global_completion_pct < ? AND a.global_completion_pct > 0
        """
        params: list = [threshold_pct]
        if unlocked_only:
            query += " AND au.unlocked = 1"
        query += " ORDER BY a.global_completion_pct ASC"
        rows = self.db.execute(query, tuple(params))
        return [
            {
                "achievement_id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "game_name": r["game_name"],
                "platform": r["platform_name"],
                "global_completion_pct": r["global_completion_pct"],
                "difficulty_score": r["difficulty_score"],
                "unlocked": bool(r["unlocked"]),
                "unlock_date": r["unlock_date"],
            }
            for r in rows
        ]

    def get_in_progress_achievements(self) -> list[dict]:
        """Find achievements with partial progress (multi-stage/incremental)."""
        rows = self.db.execute(
            """SELECT a.id, a.name, a.description, a.max_progress,
                      au.current_progress, a.global_completion_pct,
                      g.name as game_name, p.name as platform_name
               FROM achievements a
               JOIN achievement_unlocks au ON au.achievement_id = a.id
               JOIN games g ON a.game_id = g.id
               JOIN platforms p ON g.platform_id = p.id
               WHERE a.max_progress > 0
               AND au.current_progress > 0
               AND (au.unlocked IS NULL OR au.unlocked = 0)
               ORDER BY (CAST(au.current_progress AS REAL) / a.max_progress) DESC"""
        )
        return [
            {
                "achievement_id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "game_name": r["game_name"],
                "platform": r["platform_name"],
                "progress": f"{r['current_progress']}/{r['max_progress']}",
                "progress_pct": round(r["current_progress"] / r["max_progress"] * 100, 2),
                "global_completion_pct": r["global_completion_pct"],
            }
            for r in rows
        ]

    def get_completable_games(self, max_remaining: int = 10) -> list[dict]:
        """Find games that are achievable to complete (few achievements remaining)."""
        rows = self.db.execute(
            """SELECT g.id, g.name as game_name, p.name as platform_name,
                      COUNT(a.id) as total,
                      COALESCE(SUM(au.unlocked), 0) as unlocked,
                      COUNT(a.id) - COALESCE(SUM(au.unlocked), 0) as remaining,
                      AVG(CASE WHEN au.unlocked = 0 OR au.unlocked IS NULL
                          THEN a.global_completion_pct ELSE NULL END) as avg_remaining_pct
               FROM games g
               JOIN platforms p ON g.platform_id = p.id
               JOIN achievements a ON a.game_id = g.id
               LEFT JOIN achievement_unlocks au ON au.achievement_id = a.id
               GROUP BY g.id
               HAVING remaining > 0 AND remaining <= ?
               ORDER BY remaining ASC, avg_remaining_pct DESC""",
            (max_remaining,),
        )
        return [
            {
                "game_id": r["id"],
                "game_name": r["game_name"],
                "platform": r["platform_name"],
                "total": r["total"],
                "unlocked": r["unlocked"],
                "remaining": r["remaining"],
                "avg_remaining_difficulty": round(100 - (r["avg_remaining_pct"] or 0), 2),
            }
            for r in rows
        ]
