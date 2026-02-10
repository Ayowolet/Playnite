"""
Mood-based recommendation filter.

Maps user moods to genre/tag/mechanic preferences and applies a scoring
boost or penalty to candidate games based on how well they match.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from ..models.game import Game
from ..models.user_profile import Mood


# Mapping: Mood -> (positive_tokens, negative_tokens, description)
MOOD_PROFILE: Dict[str, Tuple[List[str], List[str], str]] = {
    Mood.RELAXED.value: (
        ["puzzle", "casual", "walking simulator", "visual novel", "simulation",
         "farming", "cozy", "exploration", "adventure", "point-and-click",
         "turn-based", "city builder", "life sim"],
        ["horror", "action", "shooter", "fighting", "battle royale", "intense"],
        "relaxing, low-pressure games with gentle pacing",
    ),
    Mood.EXCITED.value: (
        ["action", "shooter", "fighting", "racing", "platformer", "hack and slash",
         "beat 'em up", "arcade", "adrenaline", "fast-paced", "action-rpg"],
        ["turn-based", "slow", "management", "visual novel", "walking simulator"],
        "fast-paced, high-energy games",
    ),
    Mood.CREATIVE.value: (
        ["sandbox", "building", "crafting", "city builder", "design", "mod support",
         "procedural generation", "open-ended", "simulation", "strategy",
         "base building", "factory"],
        ["linear", "on-rails"],
        "games with creative freedom and open-ended play",
    ),
    Mood.COMPETITIVE.value: (
        ["multiplayer", "competitive", "pvp", "esports", "sports", "fighting",
         "strategy", "real-time strategy", "tactical", "card game", "chess"],
        ["single-player only", "narrative only", "walking simulator"],
        "competitive games where skill and ranking matter",
    ),
    Mood.NOSTALGIC.value: (
        ["retro", "pixel art", "classic", "remake", "remaster", "old-school",
         "platformer", "rpg", "arcade", "8-bit", "16-bit", "turn-based rpg"],
        ["realistic graphics", "modern"],
        "retro and classic games that evoke nostalgia",
    ),
    Mood.ADVENTUROUS.value: (
        ["open world", "exploration", "rpg", "action rpg", "adventure", "metroidvania",
         "fantasy", "sci-fi", "epic", "narrative", "story rich", "quest"],
        ["casual", "sports", "puzzle only"],
        "expansive games to get lost in",
    ),
    Mood.CASUAL.value: (
        ["casual", "party game", "mini-games", "easy", "family friendly", "mobile-style",
         "quick play", "short session", "puzzle", "arcade"],
        ["hardcore", "difficult", "grinding", "complex mechanics"],
        "light, easy-to-pick-up games for casual sessions",
    ),
    Mood.FOCUSED.value: (
        ["strategy", "simulation", "management", "4x", "grand strategy", "puzzle",
         "rts", "tower defense", "tactics", "economy", "turn-based strategy"],
        ["action", "party", "casual", "mindless"],
        "deep, mentally engaging games requiring concentration",
    ),
    Mood.SOCIAL.value: (
        ["co-op", "multiplayer", "party game", "local co-op", "online co-op",
         "couch co-op", "mmo", "massively multiplayer"],
        ["single-player only", "no multiplayer"],
        "games best enjoyed with others",
    ),
    Mood.SPOOKY.value: (
        ["horror", "survival horror", "dark", "thriller", "mystery", "psychological",
         "gothic", "lovecraftian", "atmospheric", "tense", "suspense"],
        ["cute", "family friendly", "cozy", "casual"],
        "dark, tense, or horror games for a spooky mood",
    ),
    Mood.CHALLENGING.value: (
        [
            "difficult", "hardcore", "souls-like", "challenging", "roguelite",
            "precision platformer", "permadeath", "bullet hell", "unforgiving",
            "skill-based", "high difficulty", "punishing", "hard",
        ],
        ["casual", "easy", "family friendly", "walking simulator", "relaxed", "cozy"],
        "punishing games that demand skill and perseverance",
    ),
}


class MoodFilter:
    """
    Adjusts recommendation scores based on current user mood.
    """

    BOOST = 0.3      # Score multiplier for strong positive match
    PENALTY = 0.6    # Score multiplier for strong negative match

    def get_mood_description(self, mood: str) -> str:
        profile = MOOD_PROFILE.get(mood)
        if profile:
            return profile[2]
        return "custom mood"

    def get_mood_tokens(self, mood: str) -> Tuple[List[str], List[str]]:
        """Return (positive_tokens, negative_tokens) for a mood."""
        profile = MOOD_PROFILE.get(mood)
        if profile:
            return profile[0], profile[1]
        return [], []

    def _game_token_set(self, game: Game) -> Set[str]:
        return {t.lower() for t in game.feature_tokens()}

    def score_game_for_mood(self, game: Game, mood: str) -> float:
        """
        Return a mood-compatibility score in [0, 1].
        1.0 = perfect match, 0.5 = neutral, 0.0 = strong mismatch.
        """
        positive, negative = self.get_mood_tokens(mood)
        if not positive and not negative:
            return 0.5

        game_tokens = self._game_token_set(game)
        # Also check direct genre/mechanic/tag fields for partial matches
        game_text = " ".join(
            game.genres + game.mechanics + game.tags + game.themes + game.features
        ).lower()

        pos_matches = sum(
            1 for p in positive if p.lower() in game_tokens or p.lower() in game_text
        )
        neg_matches = sum(
            1 for n in negative if n.lower() in game_tokens or n.lower() in game_text
        )

        pos_ratio = pos_matches / max(len(positive), 1)
        neg_ratio = neg_matches / max(len(negative), 1)

        score = 0.5 + (pos_ratio * 0.5) - (neg_ratio * 0.5)
        return float(max(0.0, min(1.0, score)))

    def apply_mood_scores(
        self,
        base_scores: Dict[str, float],
        candidates: List[Game],
        mood: Optional[str],
    ) -> Dict[str, float]:
        """
        Apply mood adjustment on top of existing base scores.
        Returns a new dict with adjusted scores.
        """
        if not mood:
            return base_scores

        game_map = {g.id: g for g in candidates}
        adjusted: Dict[str, float] = {}

        for game_id, base_score in base_scores.items():
            game = game_map.get(game_id)
            if game is None:
                adjusted[game_id] = base_score
                continue
            mood_score = self.score_game_for_mood(game, mood)
            # Blend: if mood_score > 0.5 boost, if < 0.5 penalise
            if mood_score >= 0.5:
                factor = 1.0 + (mood_score - 0.5) * self.BOOST * 2
            else:
                factor = 1.0 - (0.5 - mood_score) * (1.0 - self.PENALTY) * 2
            adjusted[game_id] = min(1.0, base_score * factor)

        return adjusted

    def filter_strict_mood(
        self, candidates: List[Game], mood: str, min_score: float = 0.4
    ) -> List[Game]:
        """
        Hard-filter: only keep games that score above min_score for the mood.
        """
        return [g for g in candidates if self.score_game_for_mood(g, mood) >= min_score]

    def list_moods(self) -> List[Dict[str, str]]:
        return [
            {"mood": mood, "description": data[2]}
            for mood, data in MOOD_PROFILE.items()
        ]
