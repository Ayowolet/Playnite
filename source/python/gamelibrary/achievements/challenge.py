"""Achievement challenge mode - suggests games with achievable goals."""

from __future__ import annotations

from ..database import Database


class ChallengeMode:
    """Suggests achievement challenges based on difficulty and estimated effort."""

    def __init__(self, db: Database):
        self.db = db

    def suggest_challenges(self, difficulty: str = "medium", limit: int = 5) -> list[dict]:
        """Suggest games with achievable goals based on difficulty preference.

        difficulty: easy, medium, hard
        """
        if difficulty == "easy":
            min_pct, max_pct = 50.0, 100.0
            max_remaining = 5
        elif difficulty == "hard":
            min_pct, max_pct = 0.0, 25.0
            max_remaining = 50
        else:
            min_pct, max_pct = 25.0, 50.0
            max_remaining = 15

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
               AND (avg_remaining_pct >= ? AND avg_remaining_pct <= ?)
               ORDER BY remaining ASC
               LIMIT ?""",
            (max_remaining, min_pct, max_pct, limit),
        )
        challenges = []
        for r in rows:
            remaining = r["remaining"]
            avg_pct = r["avg_remaining_pct"] or 50.0
            est_hours = self._estimate_time(remaining, avg_pct)
            challenges.append({
                "game_id": r["id"],
                "game_name": r["game_name"],
                "platform": r["platform_name"],
                "current_progress": f"{r['unlocked']}/{r['total']}",
                "remaining": remaining,
                "difficulty": difficulty,
                "avg_remaining_completion_pct": round(avg_pct, 2),
                "estimated_hours": est_hours,
                "challenge_description": self._generate_description(
                    r["game_name"], remaining, difficulty
                ),
            })
        return challenges

    def get_daily_challenge(self) -> dict | None:
        """Suggest a single achievement to pursue today."""
        rows = self.db.execute(
            """SELECT a.id, a.name, a.description, a.global_completion_pct,
                      g.name as game_name, p.name as platform_name,
                      a.max_progress, COALESCE(au.current_progress, 0) as current_progress
               FROM achievements a
               LEFT JOIN achievement_unlocks au ON au.achievement_id = a.id
               JOIN games g ON a.game_id = g.id
               JOIN platforms p ON g.platform_id = p.id
               WHERE (au.unlocked IS NULL OR au.unlocked = 0)
               AND a.global_completion_pct >= 20.0
               ORDER BY RANDOM() LIMIT 1"""
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "achievement_id": r["id"],
            "name": r["name"],
            "description": r["description"],
            "game_name": r["game_name"],
            "platform": r["platform_name"],
            "global_completion_pct": r["global_completion_pct"],
            "progress": f"{r['current_progress']}/{r['max_progress']}" if r["max_progress"] > 0 else "Not started",
        }

    @staticmethod
    def _estimate_time(remaining: int, avg_global_pct: float) -> float:
        """Rough time estimate in hours based on remaining count and difficulty."""
        base_time = 0.5
        difficulty_multiplier = max(0.5, (100 - avg_global_pct) / 20)
        return round(remaining * base_time * difficulty_multiplier, 1)

    @staticmethod
    def _generate_description(game_name: str, remaining: int, difficulty: str) -> str:
        if remaining <= 3:
            return f"Almost there! Just {remaining} achievement(s) left in {game_name}."
        elif difficulty == "easy":
            return f"Complete {remaining} accessible achievements in {game_name}."
        elif difficulty == "hard":
            return f"Take on {remaining} challenging achievements in {game_name}."
        else:
            return f"Work through {remaining} remaining achievements in {game_name}."
