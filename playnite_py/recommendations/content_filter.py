"""
Content-based filtering using TF-IDF feature vectors and cosine similarity.

Algorithm
---------
1. Build a feature document for each game by joining its genre, theme,
   mechanic, feature, tag, developer, art_style, and series tokens.
2. Fit a TF-IDF vectoriser over the full game corpus.
3. Compute a "user preference vector" as the weighted average of the
   TF-IDF vectors of games the user has played, with weights derived
   from playtime + explicit ratings.
4. Rank unplayed candidate games by cosine similarity to the preference
   vector.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

from ..models.game import Game
from ..models.user_profile import UserProfile


class ContentBasedFilter:
    """
    Compute content similarity scores between candidate games and a user's
    inferred preference profile.
    """

    def __init__(
        self,
        min_df: int = 1,
        max_features: int = 5000,
        ngram_range: Tuple[int, int] = (1, 2),
    ) -> None:
        if not _SKLEARN_AVAILABLE:
            raise ImportError(
                "scikit-learn is required for content-based filtering. "
                "Install it with: pip install scikit-learn"
            )
        self._vectorizer = TfidfVectorizer(
            min_df=min_df,
            max_features=max_features,
            ngram_range=ngram_range,
            sublinear_tf=True,
        )
        self._game_matrix: Optional[np.ndarray] = None
        self._game_ids: List[str] = []
        self._fitted = False

    # ------------------------------------------------------------------ #
    # Fitting                                                              #
    # ------------------------------------------------------------------ #

    def fit(self, games: List[Game]) -> "ContentBasedFilter":
        """
        Fit the TF-IDF vectoriser on the full game corpus.
        Must be called before ``score_candidates``.
        """
        if not games:
            return self
        self._game_ids = [g.id for g in games]
        corpus = [g.feature_string() for g in games]
        self._game_matrix = self._vectorizer.fit_transform(corpus).toarray()
        self._fitted = True
        return self

    # ------------------------------------------------------------------ #
    # User preference vector                                               #
    # ------------------------------------------------------------------ #

    def _build_preference_vector(
        self, played_games: List[Game], profile: UserProfile
    ) -> Optional[np.ndarray]:
        """
        Compute a weighted average TF-IDF vector representing the user's taste.

        Weights combine:
        * normalised playtime (70 %)
        * explicit rating adjusted to [0,1] (30 %)
        """
        if not played_games or not self._fitted:
            return None

        total_playtime = sum(g.playtime_seconds for g in played_games) or 1.0
        vectors: List[np.ndarray] = []
        weights: List[float] = []

        for game in played_games:
            if game.id not in self._game_ids:
                continue
            idx = self._game_ids.index(game.id)
            vec = self._game_matrix[idx]  # type: ignore[index]

            pt_weight = game.playtime_seconds / total_playtime
            rating = profile.ratings.get(game.id)
            rating_factor = (rating / 10.0) if rating is not None else 0.5

            w = (pt_weight * 0.7) + (rating_factor * 0.3)
            vectors.append(vec)
            weights.append(max(w, 0.0))

        if not vectors:
            return None

        weights_arr = np.array(weights)
        weights_arr /= weights_arr.sum()
        preference_vec = np.average(np.stack(vectors), axis=0, weights=weights_arr)
        return preference_vec

    # ------------------------------------------------------------------ #
    # Scoring                                                              #
    # ------------------------------------------------------------------ #

    def score_candidates(
        self,
        candidates: List[Game],
        played_games: List[Game],
        profile: UserProfile,
    ) -> Dict[str, float]:
        """
        Return a dict mapping game_id -> content similarity score in [0, 1].

        Parameters
        ----------
        candidates:
            Games to score (typically unplayed/unowned games).
        played_games:
            Games the user has already played (used to build preference vector).
        profile:
            User profile containing ratings and weights.
        """
        if not self._fitted or not candidates:
            return {}

        pref_vec = self._build_preference_vector(played_games, profile)
        if pref_vec is None:
            # Cold start: return uniform small scores
            return {g.id: 0.1 for g in candidates}

        # Vectorise candidate games
        candidate_ids = [g.id for g in candidates]
        # Some candidates may not be in the fitted corpus; handle gracefully
        known_candidates = [g for g in candidates if g.id in self._game_ids]
        unknown_candidates = [g for g in candidates if g.id not in self._game_ids]

        scores: Dict[str, float] = {}

        if known_candidates:
            indices = [self._game_ids.index(g.id) for g in known_candidates]
            matrix_slice = self._game_matrix[indices]  # type: ignore[index]
            sims = cosine_similarity(
                pref_vec.reshape(1, -1), matrix_slice
            )[0]
            for game, sim in zip(known_candidates, sims):
                scores[game.id] = float(np.clip(sim, 0.0, 1.0))

        # Unknown candidates: vectorise on-the-fly
        if unknown_candidates:
            new_corpus = [g.feature_string() for g in unknown_candidates]
            try:
                new_vecs = self._vectorizer.transform(new_corpus).toarray()
                sims = cosine_similarity(pref_vec.reshape(1, -1), new_vecs)[0]
                for game, sim in zip(unknown_candidates, sims):
                    scores[game.id] = float(np.clip(sim, 0.0, 1.0))
            except Exception:
                for game in unknown_candidates:
                    scores[game.id] = 0.0

        return scores

    # ------------------------------------------------------------------ #
    # Attribute-level explanation helpers                                  #
    # ------------------------------------------------------------------ #

    def get_top_features(self, game: Game, top_n: int = 5) -> List[str]:
        """
        Return the TF-IDF top-N features for a specific game.
        Useful for explaining WHY the game matches the user's preferences.
        """
        if not self._fitted or game.id not in self._game_ids:
            return game.feature_tokens()[:top_n]
        idx = self._game_ids.index(game.id)
        feature_names = self._vectorizer.get_feature_names_out()
        vec = self._game_matrix[idx]  # type: ignore[index]
        top_indices = np.argsort(vec)[::-1][:top_n]
        return [feature_names[i] for i in top_indices if vec[i] > 0]

    def get_shared_features(
        self, game_a: Game, game_b: Game, top_n: int = 5
    ) -> List[str]:
        """
        Return features shared between two games (for explanation).
        """
        if not self._fitted:
            set_a = set(game_a.feature_tokens())
            set_b = set(game_b.feature_tokens())
            return list(set_a & set_b)[:top_n]

        def _top(game: Game) -> set:
            if game.id not in self._game_ids:
                return set()
            idx = self._game_ids.index(game.id)
            feature_names = self._vectorizer.get_feature_names_out()
            vec = self._game_matrix[idx]  # type: ignore[index]
            top_idx = np.argsort(vec)[::-1][:20]
            return {feature_names[i] for i in top_idx if vec[i] > 0}

        return list(_top(game_a) & _top(game_b))[:top_n]
