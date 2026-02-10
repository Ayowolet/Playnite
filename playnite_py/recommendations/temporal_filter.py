"""
Temporal recommendation signals.

Boosts games whose typical play style fits:
- Current season (winter → long narrative games; summer → short/fun)
- Time of day (morning → casual; late night → horror/adventure)
- Day of week (weekday → shorter; weekend → long sessions)
- Recent play history (avoid suggesting same genre cluster repeatedly)
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from ..models.game import Game
from ..models.user_profile import UserProfile


# Genre/tag tokens associated with each season
_SEASON_PREFERENCES: Dict[str, Dict[str, float]] = {
    "winter": {
        "rpg": 0.3, "strategy": 0.2, "simulation": 0.2, "visual novel": 0.25,
        "narrative": 0.3, "turn-based": 0.15, "city builder": 0.2,
        "grand strategy": 0.25, "cozy": 0.4,
    },
    "spring": {
        "adventure": 0.25, "platformer": 0.2, "action": 0.15,
        "exploration": 0.3, "open world": 0.25, "indie": 0.15,
    },
    "summer": {
        "action": 0.25, "sports": 0.35, "racing": 0.3, "multiplayer": 0.3,
        "party game": 0.3, "casual": 0.2, "arcade": 0.2, "competitive": 0.25,
    },
    "autumn": {
        "horror": 0.4, "thriller": 0.3, "mystery": 0.3, "dark": 0.3,
        "atmospheric": 0.25, "gothic": 0.3, "survival": 0.25,
    },
}

# Preferences by time of day
_DAYTIME_PREFERENCES: Dict[str, Dict[str, float]] = {
    "morning": {
        "puzzle": 0.25, "casual": 0.3, "strategy": 0.2, "quick play": 0.3,
        "turn-based": 0.2, "management": 0.2,
    },
    "afternoon": {
        "action": 0.2, "adventure": 0.2, "rpg": 0.15, "platformer": 0.2,
        "sports": 0.25, "racing": 0.2,
    },
    "evening": {
        "action rpg": 0.2, "adventure": 0.25, "rpg": 0.25, "open world": 0.2,
        "story rich": 0.3, "narrative": 0.2, "co-op": 0.25,
    },
    "night": {
        "horror": 0.3, "atmospheric": 0.3, "mystery": 0.2, "thriller": 0.25,
        "dark": 0.25, "exploration": 0.2, "immersive sim": 0.2,
    },
}

# Weekend vs weekday modifiers (additive)
_WEEKEND_BONUS: Dict[str, float] = {
    "open world": 0.25, "rpg": 0.25, "grand strategy": 0.3,
    "simulation": 0.2, "mmo": 0.3, "multiplayer": 0.2,
}
_WEEKDAY_BONUS: Dict[str, float] = {
    "casual": 0.2, "puzzle": 0.2, "quick play": 0.3,
    "roguelike": 0.2, "arcade": 0.2, "sports": 0.15,
}


def _get_season(dt: datetime) -> str:
    month = dt.month
    if month in (12, 1, 2):
        return "winter"
    elif month in (3, 4, 5):
        return "spring"
    elif month in (6, 7, 8):
        return "summer"
    else:
        return "autumn"


def _get_time_slot(dt: datetime) -> str:
    hour = dt.hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 22:
        return "evening"
    else:
        return "night"


class TemporalFilter:
    """
    Apply time-aware scoring adjustments to candidate recommendations.
    """

    def __init__(self, now: Optional[datetime] = None) -> None:
        self.now = now or datetime.now()

    def _game_matches_prefs(self, game: Game, prefs: Dict[str, float]) -> float:
        """
        Return weighted sum of matches between game tokens and preference dict.
        """
        game_text = (
            " ".join(game.genres + game.themes + game.mechanics + game.tags + game.features)
        ).lower()
        total = 0.0
        for token, weight in prefs.items():
            if token.lower() in game_text:
                total += weight
        return total

    def get_temporal_scores(
        self, candidates: List[Game], profile: UserProfile
    ) -> Dict[str, float]:
        """
        Return a dict of game_id -> temporal score in [0, 1].
        """
        season = _get_season(self.now)
        time_slot = _get_time_slot(self.now)
        is_weekend = self.now.weekday() >= 5

        season_prefs = _SEASON_PREFERENCES[season]
        daytime_prefs = _DAYTIME_PREFERENCES[time_slot]
        day_prefs = _WEEKEND_BONUS if is_weekend else _WEEKDAY_BONUS

        # Recency penalty: discount genres recently played in last ~7 sessions
        recent_genres = self._get_recent_genres(profile, n_games=7)

        scores: Dict[str, float] = {}
        for game in candidates:
            s = 0.0
            s += self._game_matches_prefs(game, season_prefs) * 0.4
            s += self._game_matches_prefs(game, daytime_prefs) * 0.35
            s += self._game_matches_prefs(game, day_prefs) * 0.25

            # Recency penalty: if genre was recently played, slight discount
            for genre in game.genres:
                if genre.lower() in recent_genres:
                    s *= 0.85
                    break

            scores[game.id] = min(1.0, s)

        # Normalise to [0, 1]
        max_s = max(scores.values(), default=1.0)
        if max_s > 0:
            scores = {k: v / max_s for k, v in scores.items()}
        return scores

    def _get_recent_genres(self, profile: UserProfile, n_games: int = 7) -> set:
        """
        Returns a set of genre tokens the user played recently
        (based on genre_weights as a proxy when session data isn't available).
        """
        # Use top weighted genres as "recently interacted" proxy
        top = sorted(profile.genre_weights.items(), key=lambda x: x[1], reverse=True)[:n_games]
        return {k.lower() for k, _ in top}

    def get_context_summary(self) -> Dict[str, str]:
        return {
            "season": _get_season(self.now),
            "time_of_day": _get_time_slot(self.now),
            "day_type": "weekend" if self.now.weekday() >= 5 else "weekday",
        }
