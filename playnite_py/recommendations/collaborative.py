"""
Collaborative filtering via Truncated SVD (matrix factorisation).

For single-user scenarios (no peer-user data) we synthesise virtual users
from game attribute clusters so the SVD decomposition still provides
meaningful latent game representations that complement content-based scores.

With multiple real user profiles stored in the database the filter
automatically uses actual peer data.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from sklearn.decomposition import TruncatedSVD
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.preprocessing import normalize
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

from ..models.game import Game
from ..models.user_profile import UserProfile


class CollaborativeFilter:
    """
    Latent-factor collaborative filter.

    Usage
    -----
    1. Call ``fit(all_games, user_profiles)``
    2. Call ``score_candidates(candidates, profile)``
    """

    N_COMPONENTS = 50   # SVD latent dimensions
    MIN_USERS = 3       # Minimum real users before activating collaborative signal

    def __init__(self, n_components: int = N_COMPONENTS) -> None:
        if not _SKLEARN_AVAILABLE:
            raise ImportError(
                "scikit-learn is required for collaborative filtering. "
                "Install it with: pip install scikit-learn"
            )
        self.n_components = n_components
        self._svd: Optional[TruncatedSVD] = None
        self._game_factors: Optional[np.ndarray] = None   # (n_games, k)
        self._user_factors: Optional[np.ndarray] = None   # (n_users, k)
        self._game_ids: List[str] = []
        self._user_ids: List[str] = []
        self._fitted = False

    # ------------------------------------------------------------------ #
    # Matrix construction                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _interaction_weight(game: Game, user: UserProfile) -> float:
        """
        Build a scalar interaction weight from playtime + explicit rating.
        Returns 0 if the user hasn't interacted with the game.
        """
        played = game.playtime_seconds > 0 or game.play_count > 0
        if not played and game.id not in user.ratings:
            return 0.0
        rating = user.ratings.get(game.id)
        if rating is not None:
            # Rating 0-10 → 0.1-1.0
            rating_score = max(0.1, rating / 10.0)
        else:
            rating_score = 0.5
        # Playtime signal: log-scale to avoid extreme outliers
        pt_score = min(1.0, np.log1p(game.playtime_seconds / 3600) / 6.0)
        return max(rating_score, pt_score)

    def _build_matrix(
        self, all_games: List[Game], real_users: List[UserProfile]
    ) -> Tuple[np.ndarray, List[str], List[str]]:
        """
        Build the user–item interaction matrix.  Pads with synthetic users
        if real-user count is below MIN_USERS.
        """
        game_ids = [g.id for g in all_games]
        game_map = {g.id: i for i, g in enumerate(all_games)}
        n_games = len(all_games)

        rows: List[List[float]] = []
        user_ids: List[str] = []

        # Real users
        for user in real_users:
            row = np.zeros(n_games)
            for game in all_games:
                w = self._interaction_weight(game, user)
                if w > 0:
                    row[game_map[game.id]] = w
            rows.append(row.tolist())
            user_ids.append(user.id)

        # Synthetic users derived from genre clusters to help SVD
        if len(real_users) < self.MIN_USERS:
            rows.extend(self._make_synthetic_users(all_games, n_synthetic=max(5, self.MIN_USERS)))
            user_ids.extend([f"_synth_{i}" for i in range(len(rows) - len(real_users))])

        return np.array(rows, dtype=np.float32), game_ids, user_ids

    @staticmethod
    def _make_synthetic_users(games: List[Game], n_synthetic: int = 5) -> List[List[float]]:
        """
        Create virtual user profiles based on genre clusters.
        Each synthetic user "likes" all games of a particular genre cluster.
        """
        # Collect all genres present in corpus
        all_genres: Dict[str, List[int]] = {}
        for i, g in enumerate(games):
            for genre in g.genres:
                all_genres.setdefault(genre, []).append(i)

        top_genres = sorted(all_genres.keys(), key=lambda gn: len(all_genres[gn]), reverse=True)
        synth_rows: List[List[float]] = []

        for genre in top_genres[:n_synthetic]:
            row = [0.0] * len(games)
            for idx in all_genres[genre]:
                row[idx] = 0.8
            synth_rows.append(row)

        # Pad with random if not enough genres
        while len(synth_rows) < n_synthetic:
            row = [0.0] * len(games)
            chosen = np.random.choice(len(games), size=min(10, len(games)), replace=False)
            for idx in chosen:
                row[idx] = float(np.random.uniform(0.5, 1.0))
            synth_rows.append(row)

        return synth_rows[:n_synthetic]

    # ------------------------------------------------------------------ #
    # Fit                                                                  #
    # ------------------------------------------------------------------ #

    def fit(
        self, all_games: List[Game], user_profiles: List[UserProfile]
    ) -> "CollaborativeFilter":
        if not all_games:
            return self

        matrix, game_ids, user_ids = self._build_matrix(all_games, user_profiles)
        self._game_ids = game_ids
        self._user_ids = user_ids

        n_components = min(self.n_components, matrix.shape[0] - 1, matrix.shape[1] - 1)
        if n_components < 1:
            return self

        self._svd = TruncatedSVD(n_components=n_components, random_state=42)
        # Fit on transposed matrix to get game factors in reduced space
        user_factors = self._svd.fit_transform(matrix)
        self._user_factors = normalize(user_factors)

        # Game factors from V^T
        game_factors = self._svd.components_.T  # shape: (n_games, k)
        self._game_factors = normalize(game_factors)

        self._fitted = True
        return self

    # ------------------------------------------------------------------ #
    # Scoring                                                              #
    # ------------------------------------------------------------------ #

    def _get_user_factor(self, profile: UserProfile, all_games: List[Game]) -> Optional[np.ndarray]:
        """
        Compute or lookup the latent factor vector for the given user.
        """
        if self._user_factors is None or self._svd is None:
            return None

        if profile.id in self._user_ids:
            idx = self._user_ids.index(profile.id)
            return self._user_factors[idx]

        # Unseen user: project their interaction row into latent space
        n_games = len(self._game_ids)
        row = np.zeros((1, n_games), dtype=np.float32)
        for game in all_games:
            if game.id in self._game_ids:
                w = self._interaction_weight(game, profile)
                if w > 0:
                    col = self._game_ids.index(game.id)
                    row[0, col] = w

        projected = self._svd.transform(row)
        return normalize(projected)[0]

    def score_candidates(
        self,
        candidates: List[Game],
        profile: UserProfile,
        all_games: List[Game],
    ) -> Dict[str, float]:
        """
        Return dict of game_id -> collaborative score in [0, 1].
        """
        if not self._fitted or not candidates or self._game_factors is None:
            return {}

        user_vec = self._get_user_factor(profile, all_games)
        if user_vec is None:
            return {}

        scores: Dict[str, float] = {}
        for game in candidates:
            if game.id not in self._game_ids:
                scores[game.id] = 0.0
                continue
            idx = self._game_ids.index(game.id)
            game_vec = self._game_factors[idx]
            sim = float(cosine_similarity(
                user_vec.reshape(1, -1), game_vec.reshape(1, -1)
            )[0][0])
            scores[game.id] = float(np.clip(sim, 0.0, 1.0))

        return scores

    def find_similar_games(self, game: Game, all_games: List[Game], top_n: int = 10) -> List[Tuple[Game, float]]:
        """Return top_n games most similar to `game` in latent space."""
        if not self._fitted or self._game_factors is None or game.id not in self._game_ids:
            return []
        idx = self._game_ids.index(game.id)
        query_vec = self._game_factors[idx].reshape(1, -1)
        sims = cosine_similarity(query_vec, self._game_factors)[0]
        top_idx = np.argsort(sims)[::-1][1 : top_n + 1]
        game_id_map = {g.id: g for g in all_games}
        results = []
        for i in top_idx:
            gid = self._game_ids[i]
            if gid in game_id_map:
                results.append((game_id_map[gid], float(sims[i])))
        return results
