"""
Recommendation Engine — orchestrates all filtering signals into a ranked,
explained list of game recommendations.

Usage
-----
    from playnite_py.recommendations import RecommendationEngine
    from playnite_py.library import LibraryManager

    mgr = LibraryManager()
    engine = RecommendationEngine(mgr)
    recs = engine.generate(profile, n=10, mood="relaxed")
    for rec in recs:
        print(rec.game.name, "—", rec.explanation.primary_reason)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import AppConfig, RecommendationConfig
from ..library.manager import LibraryManager
from ..models.game import Game
from ..models.user_profile import RecommendationFeedback, UserProfile
from .collaborative import CollaborativeFilter
from .content_filter import ContentBasedFilter
from .explainer import Explanation, RecommendationExplainer
from .feedback import FeedbackEngine
from .mood_filter import MoodFilter
from .temporal_filter import TemporalFilter


@dataclass
class Recommendation:
    """A single game recommendation with score breakdown and explanation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    batch_id: str = ""
    game: Game = field(default_factory=Game)

    # Individual filter scores (all in [0, 1])
    content_score: float = 0.0
    collaborative_score: float = 0.0
    temporal_score: float = 0.0
    mood_score: float = 0.5
    final_score: float = 0.0

    explanation: Optional[Explanation] = None
    rank: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "game_id": self.game.id,
            "game_name": self.game.name,
            "content_score": round(self.content_score, 4),
            "collaborative_score": round(self.collaborative_score, 4),
            "temporal_score": round(self.temporal_score, 4),
            "mood_score": round(self.mood_score, 4),
            "final_score": round(self.final_score, 4),
            "rank": self.rank,
            "explanation": self.explanation.to_dict() if self.explanation else None,
            "game": self.game.to_dict(),
        }


class RecommendationEngine:
    """
    The main recommendation engine.  Combines content-based, collaborative,
    mood, and temporal signals into a ranked list of ``Recommendation`` objects.
    """

    def __init__(
        self,
        library: LibraryManager,
        config: Optional[AppConfig] = None,
    ) -> None:
        self.library = library
        self.config = config or AppConfig()
        self.rec_config: RecommendationConfig = self.config.recommendations

        self._content_filter = ContentBasedFilter()
        self._collab_filter = CollaborativeFilter()
        self._mood_filter = MoodFilter()
        self._explainer = RecommendationExplainer()
        self._feedback_engine = FeedbackEngine(self.rec_config)

        self._fitted = False

    # ------------------------------------------------------------------ #
    # Core public API                                                      #
    # ------------------------------------------------------------------ #

    def analyse_library(self, profile: UserProfile) -> UserProfile:
        """
        Analyse the library and update the user profile's preference weights.
        Should be called before ``generate`` when a user's library has changed.
        """
        profile = self.library.build_user_preference_weights(profile)
        self.library.save_profile(profile)
        return profile

    def fit(self, all_games: Optional[List[Game]] = None) -> "RecommendationEngine":
        """
        Fit the content and collaborative filters on the game corpus.
        Re-run after library changes or once per session.
        """
        if all_games is None:
            all_games = self.library.get_all_games()
        if not all_games:
            return self

        profiles = self.library.db.list_user_profiles()

        self._content_filter.fit(all_games)
        self._collab_filter.fit(all_games, profiles)
        self._fitted = True
        return self

    def generate(
        self,
        profile: UserProfile,
        n: int = 10,
        mood: Optional[str] = None,
        *,
        include_unowned: bool = False,
        genre_filter: Optional[str] = None,
        platform_filter: Optional[str] = None,
        session_type: Optional[str] = None,
        max_completion_hours: Optional[float] = None,
        min_completion_hours: Optional[float] = None,
        difficulty_filter: Optional[str] = None,
        multiplayer_filter: Optional[bool] = None,
        vr_only: bool = False,
        exclude_ids: Optional[List[str]] = None,
        save_to_db: bool = True,
    ) -> List[Recommendation]:
        """
        Generate a ranked list of up to ``n`` recommendations.

        Parameters
        ----------
        profile:
            The user to generate recommendations for.
        n:
            Maximum number of recommendations to return.
        mood:
            Optional mood key (see Mood enum).  Overrides profile's current mood.
        include_unowned:
            If True, also suggest games the user doesn't own yet (wishlist-style).
        genre_filter:
            Restrict candidates to a specific genre.
        platform_filter:
            Restrict candidates to a specific platform.
        session_type:
            "quick" restricts to games with typical_session_minutes < 60 (or unknown).
            "deep"  restricts to games with typical_session_minutes >= 180 (or unknown).
        exclude_ids:
            Additional game IDs to exclude from recommendations.
        save_to_db:
            Persist recommendation batch to database (default True).
        """
        if not self._fitted:
            self.fit()

        effective_mood = mood or profile.current_mood
        all_games = self.library.get_all_games()

        # --- Separate played and candidate games ---
        played_games = [g for g in all_games if g.is_played]
        candidates = self._build_candidate_list(
            all_games,
            profile,
            include_unowned=include_unowned,
            genre_filter=genre_filter,
            platform_filter=platform_filter,
            session_type=session_type,
            max_completion_hours=max_completion_hours,
            min_completion_hours=min_completion_hours,
            difficulty_filter=difficulty_filter,
            multiplayer_filter=multiplayer_filter,
            vr_only=vr_only,
            exclude_ids=exclude_ids,
        )

        if not candidates:
            return []

        # --- Compute scores from each signal ---
        content_scores = self._content_filter.score_candidates(
            candidates, played_games, profile
        )
        collab_scores = self._collab_filter.score_candidates(
            candidates, profile, all_games
        )
        temporal = TemporalFilter()
        temporal_scores = temporal.get_temporal_scores(candidates, profile)

        mood_scores: Dict[str, float] = {}
        if effective_mood:
            adjusted = self._mood_filter.apply_mood_scores(
                {g.id: 0.5 for g in candidates}, candidates, effective_mood
            )
            mood_scores = adjusted

        # --- Read dynamic weights (may have been adjusted by feedback) ---
        cw = self.rec_config.content_weight
        lw = self.rec_config.collaborative_weight
        tw = self.rec_config.temporal_weight
        pw = self.rec_config.popularity_weight

        # --- Build final scored list ---
        batch_id = str(uuid.uuid4())
        scored: List[Recommendation] = []

        for game in candidates:
            cs = content_scores.get(game.id, 0.0)
            ls = collab_scores.get(game.id, 0.0)
            ts = temporal_scores.get(game.id, 0.0)
            ms = mood_scores.get(game.id, 0.5)

            # Popularity component from community score
            pop = (game.community_score or 0) / 100.0

            # Wishlist bonus
            wishlist_bonus = 0.1 if game.id in profile.wishlist else 0.0

            # Mood multiplier: if mood is set, games that mismatch get penalised
            mood_mult = (ms / 0.5) if effective_mood else 1.0  # normalise around neutral

            final = (
                (cs * cw + ls * lw + ts * tw + pop * pw) * mood_mult + wishlist_bonus
            )
            final = min(1.0, max(0.0, final))

            if final < self.rec_config.min_score_threshold:
                continue

            scored.append(Recommendation(
                batch_id=batch_id,
                game=game,
                content_score=cs,
                collaborative_score=ls,
                temporal_score=ts,
                mood_score=ms,
                final_score=final,
            ))

        # --- Sort and take top N ---
        scored.sort(key=lambda r: r.final_score, reverse=True)
        top = scored[:n]

        # --- Find similar played games for each candidate (for explanations) ---
        played_map: Dict[str, Game] = {g.id: g for g in played_games}
        all_scores_by_source = {
            "content": content_scores,
            "collaborative": collab_scores,
            "temporal": temporal_scores,
            "mood": mood_scores,
        }

        for rank, rec in enumerate(top, 1):
            rec.rank = rank
            # Find top played games similar to this candidate
            similar_played = self._find_similar_played(
                rec.game, played_games, content_scores
            )
            rec.explanation = self._explainer.explain(
                candidate=rec.game,
                profile=profile,
                played_games=played_games,
                scores=all_scores_by_source,
                mood=effective_mood,
                similar_played=similar_played,
            )

        # --- Persist batch to database ---
        if save_to_db and top:
            self.library.db.save_recommendation_batch(
                rec_id=batch_id,
                user_id=profile.id,
                recommendations=[r.to_dict() for r in top],
                mood=effective_mood,
            )

        return top

    def generate_what_to_play_next(
        self, profile: UserProfile, n: int = 5
    ) -> List[Recommendation]:
        """
        Quick 'what to play next' list based purely on recent play history.
        Prefers games similar to the most recently played game.
        """
        played = sorted(
            self.library.get_played_games(),
            key=lambda g: g.last_played or datetime.min,
            reverse=True,
        )
        if not played:
            return self.generate(profile, n=n)

        last = played[0]
        if not self._fitted:
            self.fit()

        similar = self._collab_filter.find_similar_games(
            last, self.library.get_all_games(), top_n=n * 3
        )
        candidate_ids = {g.id for g, _ in similar}
        # Remove already-played games
        played_ids = {g.id for g in played}
        candidates = [
            g for g, _ in similar
            if g.id not in played_ids and g.id != last.id
        ][:n * 2]

        if not candidates:
            return self.generate(profile, n=n)

        return self.generate(
            profile, n=n, exclude_ids=list(played_ids - {last.id})
        )

    # ------------------------------------------------------------------ #
    # Feedback                                                             #
    # ------------------------------------------------------------------ #

    def record_feedback(
        self,
        profile: UserProfile,
        recommendation: Recommendation,
        action: str,
        notes: Optional[str] = None,
    ) -> RecommendationFeedback:
        """
        Record user feedback on a recommendation and update profile weights.
        """
        fb = self._feedback_engine.record_feedback(
            user_id=profile.id,
            recommendation_id=recommendation.batch_id,
            game=recommendation.game,
            action=action,
            content_score=recommendation.content_score,
            collaborative_score=recommendation.collaborative_score,
            final_score=recommendation.final_score,
            notes=notes,
        )
        self.library.db.save_feedback(fb)

        # Periodic weight update
        all_feedback = self.library.db.get_feedback(profile.id)
        game_map = {g.id: g for g in self.library.get_all_games()}
        updated_profile = self._feedback_engine.update_profile_from_feedback(
            profile, all_feedback, game_map
        )
        self.library.save_profile(updated_profile)
        return fb

    # ------------------------------------------------------------------ #
    # History / export                                                     #
    # ------------------------------------------------------------------ #

    def get_history(self, profile: UserProfile, limit: int = 10) -> List[Dict[str, Any]]:
        return self.library.db.get_recommendation_history(profile.id, limit=limit)

    def export_history(self, profile: UserProfile, output_path: Optional[Path] = None) -> Path:
        """
        Export full recommendation history with reasoning to a JSON file.
        """
        history = self.library.db.get_recommendation_history(profile.id, limit=500)
        if output_path is None:
            self.config.ensure_dirs()
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            output_path = self.config.history_dir / f"recommendations_{ts}.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        export_data = {
            "user_id": profile.id,
            "username": profile.username,
            "exported_at": datetime.utcnow().isoformat(),
            "total_batches": len(history),
            "history": history,
        }
        output_path.write_text(json.dumps(export_data, indent=2, default=str), encoding="utf-8")
        return output_path

    def get_accuracy_stats(self, profile: UserProfile) -> Dict[str, Any]:
        feedback = self.library.db.get_feedback(profile.id)
        return self._feedback_engine.get_feedback_stats(feedback)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _build_candidate_list(
        self,
        all_games: List[Game],
        profile: UserProfile,
        *,
        include_unowned: bool,
        genre_filter: Optional[str],
        platform_filter: Optional[str],
        session_type: Optional[str] = None,
        max_completion_hours: Optional[float] = None,
        min_completion_hours: Optional[float] = None,
        difficulty_filter: Optional[str] = None,
        multiplayer_filter: Optional[bool] = None,
        vr_only: bool = False,
        exclude_ids: Optional[List[str]],
    ) -> List[Game]:
        exclude = set(exclude_ids or [])

        candidates = []
        for game in all_games:
            if game.id in exclude:
                continue
            if game.hidden:
                continue
            if self.rec_config.exclude_played and game.is_played:
                continue
            if not include_unowned and not game.is_owned:
                continue

            if genre_filter:
                if not any(genre_filter.lower() in g.lower() for g in game.genres):
                    continue
            if platform_filter:
                if not any(platform_filter.lower() in p.lower() for p in game.platforms):
                    continue

            # Session-length filter: only exclude games that explicitly don't match;
            # games with no typical_session_minutes set always pass through.
            if session_type == "quick":
                if game.typical_session_minutes is not None and game.typical_session_minutes >= 60:
                    continue
            elif session_type == "deep":
                if game.typical_session_minutes is not None and game.typical_session_minutes < 180:
                    continue

            # Completion-hours range (lenient: games with no completion_hours pass through)
            if max_completion_hours is not None:
                if game.completion_hours is not None and game.completion_hours > max_completion_hours:
                    continue
            if min_completion_hours is not None:
                if game.completion_hours is not None and game.completion_hours < min_completion_hours:
                    continue

            # Difficulty (lenient: games with no difficulty set pass through)
            if difficulty_filter:
                if game.difficulty is not None and difficulty_filter.lower() != game.difficulty.lower():
                    continue

            # Multiplayer (strict: games must match the requested flag value)
            if multiplayer_filter is not None:
                if game.multiplayer_support != multiplayer_filter:
                    continue

            # VR only (strict: only vr_compatible=True games pass)
            if vr_only and not game.vr_compatible:
                continue

            candidates.append(game)

        return candidates

    def _find_similar_played(
        self,
        candidate: Game,
        played_games: List[Game],
        content_scores: Dict[str, float],
    ) -> List[Game]:
        """
        Find played games that share the most attributes with the candidate.
        Used for explanation generation.
        """
        shared_scores = []
        for pg in played_games:
            shared = len(
                set(candidate.genres) & set(pg.genres)
                | set(candidate.themes) & set(pg.themes)
                | set(candidate.mechanics) & set(pg.mechanics)
            )
            if shared > 0:
                shared_scores.append((pg, shared))
        shared_scores.sort(key=lambda x: x[1], reverse=True)
        return [g for g, _ in shared_scores[:3]]
