"""Fuzzy and exact search for the game library."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

try:
    from rapidfuzz import fuzz as _fuzz

    _RAPIDFUZZ = True
except ImportError:
    _fuzz = None  # type: ignore[assignment]
    _RAPIDFUZZ = False


@dataclass
class SearchResult:
    """A game together with its match score and the field that matched."""

    game: object  # Game instance
    score: float
    matched_field: str


class SearchEngine:
    """Searches games by query string using fuzzy or substring matching."""

    DEFAULT_THRESHOLD = 60
    DEFAULT_FIELDS: Tuple[str, ...] = ("name", "developer", "publisher")

    def search(
        self,
        games: List,
        query: str,
        fields: Tuple[str, ...] = DEFAULT_FIELDS,
        threshold: int = DEFAULT_THRESHOLD,
        fuzzy: bool = True,
        include_tags: bool = True,
    ) -> List[SearchResult]:
        """Return games matching *query*, sorted by score descending."""
        if not query.strip():
            return [SearchResult(g, 100.0, "") for g in games]

        q = query.lower().strip()
        results: List[SearchResult] = []

        for game in games:
            best_score = 0.0
            best_field = ""

            for field in fields:
                value = getattr(game, field, None)
                if not value:
                    continue
                score = self._score(q, str(value).lower(), fuzzy)
                if score > best_score:
                    best_score = score
                    best_field = field

            if include_tags:
                for tag in game.tags:
                    score = self._score(q, tag.name.lower(), fuzzy)
                    if score > best_score:
                        best_score = score
                        best_field = f"tag:{tag.name}"

            if best_score >= threshold:
                results.append(SearchResult(game, best_score, best_field))

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _score(self, query: str, value: str, fuzzy: bool) -> float:
        if fuzzy and _RAPIDFUZZ and _fuzz is not None:
            return float(_fuzz.partial_ratio(query, value))
        return 100.0 if query in value else 0.0
