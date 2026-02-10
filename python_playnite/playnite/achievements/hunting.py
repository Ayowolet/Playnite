"""Achievement hunting tools.

Helps players identify the most achievable games and achievements to
complete, with difficulty and time-estimate filtering.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from playnite.database.models import Game

if TYPE_CHECKING:
    from playnite.database.connection import DatabaseManager

log = logging.getLogger(__name__)

# Rough time estimate per difficulty band (minutes per achievement)
_TIME_ESTIMATES: dict[str, float] = {
    "common": 5.0,       # >50 %
    "uncommon": 15.0,    # 25–50 %
    "rare": 40.0,        # 10–25 %
    "very_rare": 90.0,   # 1–10 %
    "ultra_rare": 300.0, # <1 %
}


def _minutes_for(difficulty_score: float | None) -> float:
    """Estimate minutes needed based on difficulty score."""
    if difficulty_score is None:
        return 30.0
    pct = (1.0 - difficulty_score) * 100.0
    if pct >= 50:
        return _TIME_ESTIMATES["common"]
    if pct >= 25:
        return _TIME_ESTIMATES["uncommon"]
    if pct >= 10:
        return _TIME_ESTIMATES["rare"]
    if pct >= 1:
        return _TIME_ESTIMATES["very_rare"]
    return _TIME_ESTIMATES["ultra_rare"]


@dataclass
class HuntingTarget:
    game_id: int
    game_name: str
    platform: str
    total: int
    unlocked: int
    remaining: int
    completion_pct: float
    # Remaining achievements filtered to achievable ones
    achievable_count: int
    avg_remaining_difficulty: float
    estimated_minutes: float
    achievability_score: float  # Higher = easier to complete


class AchievementHunter:
    """Tools for finding completable games and achievement targets."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Core hunting query
    # ------------------------------------------------------------------

    def find_targets(
        self,
        max_difficulty: float = 0.7,
        max_remaining: int = 50,
        min_completion_pct: float = 0.0,
        max_completion_pct: float = 99.9,
        platform: str | None = None,
        limit: int = 20,
    ) -> list[HuntingTarget]:
        """Return games sorted by achievability for achievement hunting.

        :param max_difficulty: maximum average difficulty score (0–1) of remaining achievements.
        :param max_remaining: only show games with at most this many locked achievements.
        :param min_completion_pct: minimum current completion %.
        :param max_completion_pct: maximum current completion % (exclude 100%).
        :param platform: filter to a specific platform.
        :param limit: maximum results.
        """
        results: list[HuntingTarget] = []
        with self._db.get_session() as session:
            query = session.query(Game)
            if platform:
                query = query.filter(Game.platform == platform)
            games = query.all()

            for game in games:
                total = len(game.achievements)
                if total == 0:
                    continue

                unlocked_ids: set[int] = set()
                for ach in game.achievements:
                    for ua in ach.user_achievements:
                        if ua.is_unlocked:
                            unlocked_ids.add(ach.id)

                unlocked = len(unlocked_ids)
                remaining_achs = [a for a in game.achievements if a.id not in unlocked_ids]
                remaining = len(remaining_achs)
                completion_pct = round(unlocked / total * 100, 2)

                if not (min_completion_pct <= completion_pct <= max_completion_pct):
                    continue
                if remaining > max_remaining:
                    continue

                achievable = [
                    a for a in remaining_achs
                    if a.difficulty_score is None or a.difficulty_score <= max_difficulty
                ]
                if not achievable and remaining > 0:
                    continue

                diff_scores = [
                    a.difficulty_score
                    for a in achievable
                    if a.difficulty_score is not None
                ]
                avg_diff = sum(diff_scores) / len(diff_scores) if diff_scores else 0.5
                est_minutes = sum(_minutes_for(a.difficulty_score) for a in achievable)

                # Achievability: weight completion % and low difficulty
                achievability = (completion_pct / 100.0) * (1.0 - avg_diff) * len(achievable)

                if avg_diff > max_difficulty and achievable:
                    continue

                results.append(
                    HuntingTarget(
                        game_id=game.id,
                        game_name=game.name,
                        platform=game.platform,
                        total=total,
                        unlocked=unlocked,
                        remaining=remaining,
                        completion_pct=completion_pct,
                        achievable_count=len(achievable),
                        avg_remaining_difficulty=round(avg_diff, 3),
                        estimated_minutes=round(est_minutes, 1),
                        achievability_score=round(achievability, 3),
                    ),
                )

        results.sort(key=lambda t: t.achievability_score, reverse=True)
        return results[:limit]

    def get_remaining_achievements(
        self, game_id: int, max_difficulty: float | None = None,
    ) -> list[dict]:
        """Return locked achievements for a game, optionally filtered by difficulty."""
        with self._db.get_session() as session:
            game = session.get(Game, game_id)
            if game is None:
                return []

            results: list[dict] = []
            for ach in game.achievements:
                is_unlocked = any(ua.is_unlocked for ua in ach.user_achievements)
                if is_unlocked:
                    continue
                if max_difficulty is not None and ach.difficulty_score is not None:
                    if ach.difficulty_score > max_difficulty:
                        continue
                results.append(
                    {
                        "id": ach.id,
                        "name": ach.name,
                        "description": ach.description,
                        "global_pct": ach.global_percentage,
                        "difficulty_score": ach.difficulty_score,
                        "estimated_minutes": _minutes_for(ach.difficulty_score),
                        "hidden": ach.hidden,
                        "current_value": ach.current_value,
                        "max_value": ach.max_value,
                    },
                )
            results.sort(key=lambda a: (a["difficulty_score"] or 1.0))
            return results

    # ------------------------------------------------------------------
    # Challenge mode
    # ------------------------------------------------------------------

    def create_challenge(
        self,
        max_difficulty: float = 0.5,
        max_hours: float = 10.0,
        count: int = 5,
        platform: str | None = None,
    ) -> list[dict]:
        """Suggest a set of games as a personal achievement challenge.

        Returns games with achievable goals that fit within *max_hours* total.
        """
        targets = self.find_targets(
            max_difficulty=max_difficulty,
            max_remaining=100,
            min_completion_pct=10.0,
            max_completion_pct=99.9,
            platform=platform,
            limit=count * 3,
        )
        selected: list[dict] = []
        remaining_minutes = max_hours * 60.0
        for t in targets:
            if t.estimated_minutes <= remaining_minutes:
                selected.append(
                    {
                        "game": t.game_name,
                        "platform": t.platform,
                        "completion_pct": t.completion_pct,
                        "achievable_count": t.achievable_count,
                        "estimated_hours": round(t.estimated_minutes / 60, 1),
                        "avg_difficulty": t.avg_remaining_difficulty,
                    },
                )
                remaining_minutes -= t.estimated_minutes
                if len(selected) >= count:
                    break

        return selected
