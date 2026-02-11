"""Weighted multi-signal confidence scoring for duplicate detection."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from ..models.game import Game
from .config import ScoringWeights
from .normalizer import TitleNormalizer

_EMPTY_UUID = uuid.UUID(int=0)


@dataclass(slots=True)
class MatchScore:
    """Detailed breakdown of a duplicate match score."""

    title_score: float = 0.0
    year_score: float | None = None
    developer_score: float | None = None
    publisher_score: float | None = None
    platform_score: float | None = None
    gameid_score: float | None = None
    composite_score: float = 0.0
    is_exact_provider_match: bool = False


class DuplicateScorer:
    """Computes confidence scores for potential duplicate pairs.

    Uses rapidfuzz for fuzzy string matching and a weighted
    multi-signal approach.  When a signal is not applicable (missing
    data on both sides), its weight is redistributed proportionally.
    """

    def __init__(
        self,
        weights: ScoringWeights | None = None,
        name_resolver: _NameResolver | None = None,
    ):
        self.weights = weights or ScoringWeights()
        self._resolver = name_resolver

    def score_pair(
        self,
        game_a: Game,
        game_b: Game,
        norm_a: str | None = None,
        norm_b: str | None = None,
    ) -> MatchScore:
        if norm_a is None:
            norm_a = TitleNormalizer.normalize(game_a.name)
        if norm_b is None:
            norm_b = TitleNormalizer.normalize(game_b.name)

        ms = MatchScore()

        # --- Title ---
        ms.title_score = self._score_title(norm_a, norm_b)

        # --- Year ---
        ms.year_score = self._score_year(game_a.release_year, game_b.release_year)

        # --- Developer ---
        ms.developer_score = self._score_id_list(game_a.developer_ids, game_b.developer_ids)

        # --- Publisher ---
        ms.publisher_score = self._score_id_list(game_a.publisher_ids, game_b.publisher_ids)

        # --- Platform ---
        ms.platform_score = self._score_platform_overlap(game_a.platform_ids, game_b.platform_ids)

        # --- GameId (exact provider match) ---
        ms.gameid_score = self._score_gameid(game_a, game_b)
        if ms.gameid_score == 1.0:
            ms.is_exact_provider_match = True
            ms.composite_score = 1.0
            return ms

        # --- Composite ---
        ms.composite_score = self._compute_composite_fast(
            ms.title_score, ms.year_score, ms.developer_score,
            ms.publisher_score, ms.platform_score, ms.gameid_score,
        )
        return ms

    # ------------------------------------------------------------------ #
    # Individual scorers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _score_title(norm_a: str, norm_b: str) -> float:
        if not norm_a or not norm_b:
            return 0.0
        return fuzz.token_sort_ratio(norm_a, norm_b) / 100.0

    @staticmethod
    def _score_year(a: int | None, b: int | None) -> float | None:
        if a is None or b is None:
            return None
        if a == b:
            return 1.0
        if abs(a - b) == 1:
            return 0.5
        return 0.0

    def _score_id_list(
        self,
        ids_a: list[uuid.UUID] | None,
        ids_b: list[uuid.UUID] | None,
    ) -> float | None:
        if not ids_a or not ids_b:
            return None
        names_a = self._resolve_ids(ids_a)
        names_b = self._resolve_ids(ids_b)
        if not names_a or not names_b:
            return None
        best = 0.0
        for na in names_a:
            for nb in names_b:
                ratio = fuzz.ratio(na.lower(), nb.lower()) / 100.0
                if ratio > best:
                    best = ratio
        return best

    @staticmethod
    def _score_platform_overlap(
        ids_a: list[uuid.UUID] | None,
        ids_b: list[uuid.UUID] | None,
    ) -> float | None:
        if not ids_a or not ids_b:
            return None
        set_a = set(ids_a)
        set_b = set(ids_b)
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        if union == 0:
            return None
        return intersection / union

    @staticmethod
    def _score_gameid(game_a: Game, game_b: Game) -> float | None:
        if game_a.plugin_id == _EMPTY_UUID or game_b.plugin_id == _EMPTY_UUID:
            return None
        if (
            game_a.plugin_id == game_b.plugin_id
            and game_a.game_id
            and game_b.game_id
            and game_a.game_id == game_b.game_id
        ):
            return 1.0
        return 0.0

    def _compute_composite(self, scores: dict[str, float | None]) -> float:
        weight_map = {
            "title": self.weights.title,
            "year": self.weights.year,
            "developer": self.weights.developer,
            "publisher": self.weights.publisher,
            "platform": self.weights.platform,
            "gameid": self.weights.gameid,
        }
        total_weight = 0.0
        weighted_sum = 0.0
        for key, score in scores.items():
            if score is not None:
                w = weight_map[key]
                weighted_sum += w * score
                total_weight += w
        if total_weight == 0:
            return 0.0
        return weighted_sum / total_weight

    def _compute_composite_fast(
        self,
        title: float,
        year: float | None,
        developer: float | None,
        publisher: float | None,
        platform: float | None,
        gameid: float | None,
    ) -> float:
        """Compute composite score without allocating a temporary dict."""
        w = self.weights
        total_weight = 0.0
        weighted_sum = 0.0
        # title is always present (never None)
        weighted_sum += w.title * title
        total_weight += w.title
        if year is not None:
            weighted_sum += w.year * year
            total_weight += w.year
        if developer is not None:
            weighted_sum += w.developer * developer
            total_weight += w.developer
        if publisher is not None:
            weighted_sum += w.publisher * publisher
            total_weight += w.publisher
        if platform is not None:
            weighted_sum += w.platform * platform
            total_weight += w.platform
        if gameid is not None:
            weighted_sum += w.gameid * gameid
            total_weight += w.gameid
        if total_weight == 0:
            return 0.0
        return weighted_sum / total_weight

    def _resolve_ids(self, ids: list[uuid.UUID]) -> list[str]:
        if self._resolver is None:
            return []
        return [n for uid in ids for n in [self._resolver.resolve(uid)] if n]


class _NameResolver:
    """Resolves entity UUIDs to names via a database."""

    def __init__(self, db: object):
        from ..db.database import GameDatabase
        self._db: GameDatabase = db  # type: ignore[assignment]
        self._cache: dict[uuid.UUID, str | None] = {}

    def resolve(self, uid: uuid.UUID) -> str | None:
        if uid in self._cache:
            return self._cache[uid]
        from ..models.lookup_tables import Company
        obj = self._db.get_lookup(Company, uid)
        name = obj.name if obj else None
        self._cache[uid] = name
        return name


def create_name_resolver(db: object) -> _NameResolver:
    """Create a name resolver backed by a GameDatabase."""
    return _NameResolver(db)
