"""
Recommendation explanation generator.

Produces human-readable explanations for why a game was recommended,
drawing on the signals that drove the score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..models.game import Game
from ..models.user_profile import UserProfile


@dataclass
class ExplanationSignal:
    """A single explanation signal contributing to the recommendation."""
    source: str          # "content" | "collaborative" | "mood" | "temporal" | "wishlist" | "popularity"
    weight: float        # Contribution weight (0-1)
    description: str     # Human-readable reason


@dataclass
class Explanation:
    """Full explanation for a recommendation."""
    game_id: str
    game_name: str
    signals: List[ExplanationSignal] = field(default_factory=list)
    primary_reason: str = ""
    supporting_reasons: List[str] = field(default_factory=list)

    def format_short(self) -> str:
        return self.primary_reason

    def format_long(self) -> str:
        lines = [f"Recommended: {self.game_name}"]
        lines.append(f"  Why: {self.primary_reason}")
        for reason in self.supporting_reasons[:3]:
            lines.append(f"  Also: {reason}")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "game_id": self.game_id,
            "game_name": self.game_name,
            "primary_reason": self.primary_reason,
            "supporting_reasons": self.supporting_reasons,
            "signals": [
                {"source": s.source, "weight": round(s.weight, 3), "description": s.description}
                for s in self.signals
            ],
        }


class RecommendationExplainer:
    """
    Generates explanations from scoring signals for a recommendation.
    """

    def explain(
        self,
        candidate: Game,
        profile: UserProfile,
        played_games: List[Game],
        scores: Dict[str, Dict[str, float]],   # {"content": {id: score}, "collaborative": {}, ...}
        mood: Optional[str] = None,
        similar_played: Optional[List[Game]] = None,
    ) -> Explanation:
        """
        Build a full ``Explanation`` object for the candidate game.

        Parameters
        ----------
        candidate:
            The game being recommended.
        profile:
            User profile.
        played_games:
            Games the user has already played.
        scores:
            Dict of source -> {game_id: score} from each filter.
        mood:
            Current mood key (optional).
        similar_played:
            List of played games found to be similar to the candidate (optional).
        """
        explanation = Explanation(game_id=candidate.id, game_name=candidate.name)
        signals: List[ExplanationSignal] = []

        content_score = scores.get("content", {}).get(candidate.id, 0.0)
        collab_score = scores.get("collaborative", {}).get(candidate.id, 0.0)
        temporal_score = scores.get("temporal", {}).get(candidate.id, 0.0)
        mood_score = scores.get("mood", {}).get(candidate.id, 0.5)

        # ---- Content signal ----
        if content_score > 0.1:
            reason = self._explain_content(candidate, profile, played_games, similar_played)
            signals.append(ExplanationSignal("content", content_score, reason))

        # ---- Collaborative signal ----
        if collab_score > 0.1:
            signals.append(ExplanationSignal(
                "collaborative", collab_score,
                "Players with a similar taste to you have enjoyed this game"
            ))

        # ---- Mood signal ----
        if mood and mood_score > 0.5:
            from .mood_filter import MOOD_PROFILE
            mood_desc = MOOD_PROFILE.get(mood, ([], [], ""))[2]
            signals.append(ExplanationSignal(
                "mood", mood_score - 0.5,
                f"Matches your '{mood}' mood ({mood_desc})"
            ))

        # ---- Temporal signal ----
        if temporal_score > 0.3:
            signals.append(ExplanationSignal(
                "temporal", temporal_score,
                self._explain_temporal(temporal_score)
            ))

        # ---- Wishlist ----
        if candidate.id in profile.wishlist:
            signals.append(ExplanationSignal("wishlist", 0.8, "This game is on your wishlist"))

        # ---- Popularity / community score ----
        if candidate.community_score and candidate.community_score >= 80:
            signals.append(ExplanationSignal(
                "popularity", 0.3,
                f"Highly rated by the community ({candidate.community_score:.0f}/100)"
            ))

        # ---- Genre preference ----
        genre_reason = self._explain_genre_match(candidate, profile)
        if genre_reason:
            signals.append(ExplanationSignal("content", content_score, genre_reason))

        explanation.signals = sorted(signals, key=lambda s: s.weight, reverse=True)

        # Choose primary reason from highest-weight signal
        if explanation.signals:
            explanation.primary_reason = explanation.signals[0].description
            explanation.supporting_reasons = [
                s.description for s in explanation.signals[1:4]
            ]
        else:
            explanation.primary_reason = self._fallback_reason(candidate)

        return explanation

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _explain_content(
        self,
        candidate: Game,
        profile: UserProfile,
        played_games: List[Game],
        similar_played: Optional[List[Game]],
    ) -> str:
        # Best case: reference a specific played game that's similar
        if similar_played:
            best = similar_played[0]
            shared = set(candidate.genres) & set(best.genres)
            if shared:
                return (
                    f"Similar to '{best.name}' which you played — "
                    f"both are {', '.join(list(shared)[:2])}"
                )
            return f"Similar in style to '{best.name}' which you have played"

        # Fall back to explaining via top genre preference
        top_genres = profile.get_top_genres(3)
        matched = [g for g in candidate.genres if g in top_genres]
        if matched:
            return f"Matches your taste for {', '.join(matched[:2])} games"

        # Developer preference
        top_devs = profile.get_top_mechanics(3)
        matched_dev = [d for d in candidate.developers if d in top_devs]
        if matched_dev:
            return f"From {matched_dev[0]}, a developer you tend to enjoy"

        return "Matches the types of games in your library"

    def _explain_genre_match(self, candidate: Game, profile: UserProfile) -> Optional[str]:
        if not candidate.genres or not profile.genre_weights:
            return None
        top_weight = 0.0
        top_genre = None
        for genre in candidate.genres:
            w = profile.genre_weights.get(genre, 0.0)
            if w > top_weight:
                top_weight = w
                top_genre = genre
        if top_genre and top_weight > 0.3:
            pct = int(top_weight * 100)
            return f"You have a {pct}% affinity for {top_genre} games based on your history"
        return None

    def _explain_temporal(self, temporal_score: float) -> str:
        from .temporal_filter import _get_season, _get_time_slot
        from datetime import datetime
        now = datetime.now()
        season = _get_season(now)
        time_slot = _get_time_slot(now)
        day_type = "weekend" if now.weekday() >= 5 else "weekday"
        return (
            f"A good pick for {time_slot} gaming on a {day_type} "
            f"in {season} (temporal score {temporal_score:.0%})"
        )

    def _fallback_reason(self, candidate: Game) -> str:
        if candidate.genres:
            return f"A {candidate.genres[0]} game from your library backlog"
        return "Unplayed game in your library"

    def format_batch(self, explanations: List[Explanation]) -> str:
        """Format a list of explanations as a numbered display string."""
        lines = []
        for i, exp in enumerate(explanations, 1):
            lines.append(f"{i}. {exp.game_name}")
            lines.append(f"   → {exp.primary_reason}")
            for reason in exp.supporting_reasons[:2]:
                lines.append(f"   • {reason}")
            lines.append("")
        return "\n".join(lines)
