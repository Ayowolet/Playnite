"""
Game-to-game fuzzy matching engine.

The :class:`GameMatcher` produces a :class:`MatchResult` for any pair of
games using a weighted combination of five signals:

1. **Title similarity** – multiple rapidfuzz scorers, best score wins.
2. **Release-year proximity** – exact match or ±1 year tolerance.
3. **Platform overlap** – Jaccard similarity of platform sets.
4. **Developer overlap** – Jaccard similarity of normalised developer names.
5. **Publisher overlap** – Jaccard similarity of normalised publisher names.

The final score is in the range [0, 1].  A score ≥ ``threshold`` is treated
as a duplicate by the detector.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from rapidfuzz import fuzz

from ..utils.text_utils import normalize_title, normalize_company_name, nfc_lower
from ..models.game import Game


# Maximum title score allowed when two normalised titles share the same base
# but differ only by a trailing sequential number (e.g. "doom" vs "doom 2",
# "fifa 22" vs "fifa 23").  token_set_ratio and partial_ratio would otherwise
# inflate the score high enough to cross the duplicate threshold for these
# genuinely different games.
_SEQUENTIAL_TITLE_CAP = 0.60

# Maximum title score when both normalised titles have tokens the other lacks
# (neither is a superset of the other) and those differing tokens are
# semantically distinct words, e.g. "Pokémon Red" vs "Pokémon Blue" or
# "Pokémon Scarlet" vs "Pokémon Violet".  The shared franchise base ("pokemon")
# gives token_set_ratio an inflated score because it treats the intersection
# tokens as a perfect match; capping prevents that shared base from carrying
# paired releases over the duplicate threshold even when all other metadata
# signals (year, platform, developer, publisher) are identical.
#
# With this cap the worst-case combined score (all non-title signals = 1.0)
# is  0.65 × 0.50 + 0.50 = 0.825, safely below the default threshold of 0.85.
_DISTINCT_SUBTITLE_CAP = 0.65

# Matches any string that ends with one or more digits (the trailing number may
# represent a sequel index or a release year).  Group 1 captures the base.
_TRAILING_NUM_RE = re.compile(r"^(.*?)\s*(\d+)$")


def _strip_trailing_number(s: str) -> tuple[str, bool]:
    """Return ``(base, had_trailing)`` after removing any trailing numeric token.

    For example::

        "doom 2"     → ("doom",  True)
        "fifa 22"    → ("fifa",  True)
        "doom"       → ("doom",  False)
        "halo 3 odst"→ ("halo 3 odst", False)  # ends in letters, no strip
    """
    m = _TRAILING_NUM_RE.match(s)
    if m and m.group(1).strip():
        return m.group(1).strip(), True
    return s, False


@dataclass(frozen=True, slots=True)
class GameMetaCache:
    """Pre-computed per-game metadata sets for batch scoring.

    Build once with :meth:`GameMatcher.build_meta_cache` before iterating over
    candidate pairs, then pass as *meta_a* / *meta_b* to
    :meth:`GameMatcher.match_keyed`.  Each game's platform, developer, and
    publisher sets are constructed exactly once rather than twice per candidate
    pair, eliminating O(N_candidates) redundant set builds and
    :func:`normalize_company_name` calls in the hot scan loop.
    """

    plat: frozenset[str]
    dev: frozenset[str]
    pub: frozenset[str]


@dataclass
class MatchWeights:
    """Configurable weights that must sum to 1.0."""

    title: float = 0.50
    year: float = 0.20
    platform: float = 0.15
    developer: float = 0.10
    publisher: float = 0.05

    def __post_init__(self) -> None:
        total = self.title + self.year + self.platform + self.developer + self.publisher
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"MatchWeights must sum to 1.0, got {total:.4f}")


@dataclass(slots=True)
class MatchResult:
    """Detailed breakdown of a pairwise game comparison."""

    game_a_id: str
    game_b_id: str

    # Component scores – all in [0, 1]
    title_score: float = 0.0
    year_score: float = 0.0
    platform_score: float = 0.0
    developer_score: float = 0.0
    publisher_score: float = 0.0

    # Final weighted score in [0, 1]
    score: float = 0.0

    # Human-readable breakdown for display / reporting.
    # ``None`` when :meth:`~GameMatcher.match_keyed` is called without
    # ``include_details=True``; avoids allocating a dict object per pair
    # in the hot scan loop.
    details: Optional[dict[str, str]] = None

    @property
    def confidence_pct(self) -> int:
        """Score as an integer percentage 0-100."""
        return round(self.score * 100)

    def is_duplicate(self, threshold: float) -> bool:
        """Return True if the aggregate score meets or exceeds *threshold*."""
        return self.score >= threshold


def _title_score(name_a: str, name_b: str) -> float:
    """
    Compute the best title similarity score across multiple fuzz algorithms.

    Uses ``token_sort_ratio`` as the primary signal (handles word-order
    differences), ``token_set_ratio`` as secondary (handles sub-title
    matches), and ``partial_ratio`` only when both strings are long enough
    to avoid short-string false positives.
    """
    if not name_a or not name_b:
        return 0.0

    na = normalize_title(name_a)
    nb = normalize_title(name_b)

    if not na or not nb:
        return 0.0

    # Exact match after normalisation → perfect score
    if na == nb:
        return 1.0

    tsr = fuzz.token_sort_ratio(na, nb) / 100.0
    tset = fuzz.token_set_ratio(na, nb) / 100.0
    best = max(tsr, tset)

    # Allow partial_ratio only when shorter string is ≥70% length of longer
    # (guards against "GTA V" matching "GTA San Andreas")
    len_ratio = min(len(na), len(nb)) / max(len(na), len(nb))
    if len_ratio >= 0.70:
        best = max(best, fuzz.partial_ratio(na, nb) / 100.0)

    # Sequential-series guard: "doom" vs "doom 2", "fifa 22" vs "fifa 23" etc.
    # token_set_ratio and partial_ratio inflate scores when one title is a pure
    # prefix of the other or both differ only in a trailing sequential number.
    # Cap the title score so these pairs stay below the duplicate threshold.
    base_a, had_a = _strip_trailing_number(na)
    base_b, had_b = _strip_trailing_number(nb)
    if (had_a or had_b) and base_a == base_b:
        best = min(best, _SEQUENTIAL_TITLE_CAP)

    # Distinct-subtitle guard: "Pokémon Red" vs "Pokémon Blue", "Pokémon
    # Scarlet" vs "Pokémon Violet", etc.  When both titles have tokens the
    # other lacks (neither is a token-superset of the other), the differing
    # words represent genuinely distinct entries in a series.  Cap so that the
    # shared base tokens alone cannot push the aggregate past the threshold.
    tok_a = set(na.split())
    tok_b = set(nb.split())
    if tok_a - tok_b and tok_b - tok_a:
        best = min(best, _DISTINCT_SUBTITLE_CAP)

    return best


def _title_score_keyed(na: str, nb: str) -> float:
    """Like :func:`_title_score` but operates on already-normalised strings.

    Skips the :func:`~game_library.utils.text_utils.normalize_title` call so
    callers that pre-compute the keys (e.g. :class:`DuplicateDetector`) avoid
    redundant work.
    """
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    tsr = fuzz.token_sort_ratio(na, nb) / 100.0
    tset = fuzz.token_set_ratio(na, nb) / 100.0
    best = max(tsr, tset)
    len_ratio = min(len(na), len(nb)) / max(len(na), len(nb))
    if len_ratio >= 0.70:
        best = max(best, fuzz.partial_ratio(na, nb) / 100.0)
    base_a, had_a = _strip_trailing_number(na)
    base_b, had_b = _strip_trailing_number(nb)
    if (had_a or had_b) and base_a == base_b:
        best = min(best, _SEQUENTIAL_TITLE_CAP)
    tok_a = set(na.split())
    tok_b = set(nb.split())
    if tok_a - tok_b and tok_b - tok_a:
        best = min(best, _DISTINCT_SUBTITLE_CAP)
    return best


def _year_score(year_a: Optional[int], year_b: Optional[int]) -> float:
    """1.0 for exact match, 0.5 for ±1 year, 0.0 otherwise.  Unknown → 0.5."""
    if year_a is None or year_b is None:
        return 0.5  # no information → neutral
    diff = abs(year_a - year_b)
    if diff == 0:
        return 1.0
    if diff == 1:
        return 0.5
    return 0.0


def _jaccard(set_a: set[str] | frozenset[str], set_b: set[str] | frozenset[str]) -> float:
    """Jaccard similarity; empty-vs-empty → 1.0 (no info, don't penalise)."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _name_set(ids: list[str], resolved: list[str]) -> set[str]:
    """Build a normalised name set from raw IDs and resolved name strings."""
    result: set[str] = set()
    for name in resolved:
        n = normalize_company_name(name)
        if n:
            result.add(n)
    if not result:
        # Fall back to raw IDs (still useful for exact GUID matching)
        result = set(ids)
    return result


class GameMatcher:
    """
    Computes a similarity :class:`MatchResult` between two :class:`Game` objects.

    Parameters
    ----------
    weights:
        Relative importance of each matching signal.
    year_tolerance:
        Maximum absolute year difference to count as a partial year match.
        Default 1; set to 0 for strict year matching.
    """

    def __init__(
        self,
        weights: Optional[MatchWeights] = None,
        year_tolerance: int = 1,
    ) -> None:
        self.weights = weights or MatchWeights()
        self.year_tolerance = year_tolerance

    def match(self, game_a: Game, game_b: Game) -> MatchResult:
        """Return a :class:`MatchResult` for the (*game_a*, *game_b*) pair."""
        w = self.weights

        # ── Title ────────────────────────────────────────────────────────────
        ts = _title_score(game_a.Name, game_b.Name)

        # ── Year ─────────────────────────────────────────────────────────────
        ys = _year_score(game_a.release_year, game_b.release_year)

        # ── Platforms ────────────────────────────────────────────────────────
        plat_a = set(game_a.PlatformIds) | {nfc_lower(p) for p in game_a._platform_names if p}
        plat_b = set(game_b.PlatformIds) | {nfc_lower(p) for p in game_b._platform_names if p}
        ps = _jaccard(plat_a, plat_b)

        # ── Developers ───────────────────────────────────────────────────────
        dev_a = _name_set(game_a.DeveloperIds, game_a._developer_names)
        dev_b = _name_set(game_b.DeveloperIds, game_b._developer_names)
        ds = _jaccard(dev_a, dev_b)

        # ── Publishers ───────────────────────────────────────────────────────
        pub_a = _name_set(game_a.PublisherIds, game_a._publisher_names)
        pub_b = _name_set(game_b.PublisherIds, game_b._publisher_names)
        pus = _jaccard(pub_a, pub_b)

        # ── Weighted aggregate ────────────────────────────────────────────────
        score = (
            ts * w.title
            + ys * w.year
            + ps * w.platform
            + ds * w.developer
            + pus * w.publisher
        )

        details = {
            "title_norm_a": normalize_title(game_a.Name),
            "title_norm_b": normalize_title(game_b.Name),
            "title_score": f"{ts:.2f}",
            "year_a": str(game_a.release_year or "?"),
            "year_b": str(game_b.release_year or "?"),
            "year_score": f"{ys:.2f}",
            "platform_score": f"{ps:.2f}",
            "developer_score": f"{ds:.2f}",
            "publisher_score": f"{pus:.2f}",
        }

        return MatchResult(
            game_a_id=game_a.Id,
            game_b_id=game_b.Id,
            title_score=ts,
            year_score=ys,
            platform_score=ps,
            developer_score=ds,
            publisher_score=pus,
            score=score,
            details=details,
        )

    def build_meta_cache(self, games: list[Game]) -> dict[str, "GameMetaCache"]:
        """Pre-compute per-game metadata sets for every game in *games*.

        Call once before iterating over candidate pairs, then pass the returned
        values to :meth:`match_keyed` via *meta_a* / *meta_b* to eliminate
        redundant set construction and
        :func:`~game_library.utils.text_utils.normalize_company_name` calls
        in the hot scoring loop.

        Complexity: O(n); each game is visited exactly once regardless of
        how many candidate pairs involve it.
        """
        result: dict[str, GameMetaCache] = {}
        for g in games:
            plat: frozenset[str] = frozenset(
                set(g.PlatformIds) | {nfc_lower(p) for p in g._platform_names if p}
            )
            dev: frozenset[str] = frozenset(_name_set(g.DeveloperIds, g._developer_names))
            pub: frozenset[str] = frozenset(_name_set(g.PublisherIds, g._publisher_names))
            result[g.Id] = GameMetaCache(plat=plat, dev=dev, pub=pub)
        return result

    def match_keyed(
        self,
        game_a: Game,
        game_b: Game,
        na: str,
        nb: str,
        threshold: float = 0.0,
        include_details: bool = False,
        meta_a: Optional["GameMetaCache"] = None,
        meta_b: Optional["GameMetaCache"] = None,
    ) -> Optional["MatchResult"]:
        """
        Like :meth:`match` but accepts pre-normalised title strings *na*/*nb*.

        Skips the :func:`~game_library.utils.text_utils.normalize_title` call
        so callers that pre-compute the normalisation cache avoid redundant work.

        When *threshold* > 0 the computation is short-circuited after each
        signal: if the maximum achievable score (current accumulated score plus
        the remaining weights at their maximum of 1.0) falls below *threshold*,
        ``None`` is returned immediately and no :class:`MatchResult` is
        allocated.  Signals are evaluated in descending weight order
        (title → year → platform → developer → publisher) to maximise the
        probability of an early exit.

        When *include_details* is ``False`` (the default) the ``details`` dict
        is not populated.  This avoids allocating nine f-strings per passing
        pair in the hot scan loop.  Pass ``True`` when the caller needs the
        human-readable breakdown (e.g. for audit reports or tests).
        """
        w = self.weights

        # ── Title ────────────────────────────────────────────────────────────
        ts = _title_score_keyed(na, nb)
        if threshold > 0.0:
            if ts * w.title + (w.year + w.platform + w.developer + w.publisher) < threshold:
                return None

        # ── Year ─────────────────────────────────────────────────────────────
        ys = _year_score(game_a.release_year, game_b.release_year)
        if threshold > 0.0:
            if ts * w.title + ys * w.year + (w.platform + w.developer + w.publisher) < threshold:
                return None

        # ── Platforms ────────────────────────────────────────────────────────
        if meta_a is not None and meta_b is not None:
            ps = _jaccard(meta_a.plat, meta_b.plat)
        else:
            ps = _jaccard(
                set(game_a.PlatformIds) | {nfc_lower(p) for p in game_a._platform_names if p},
                set(game_b.PlatformIds) | {nfc_lower(p) for p in game_b._platform_names if p},
            )
        if threshold > 0.0:
            if ts * w.title + ys * w.year + ps * w.platform + (w.developer + w.publisher) < threshold:
                return None

        # ── Developers ───────────────────────────────────────────────────────
        if meta_a is not None and meta_b is not None:
            ds = _jaccard(meta_a.dev, meta_b.dev)
        else:
            ds = _jaccard(
                _name_set(game_a.DeveloperIds, game_a._developer_names),
                _name_set(game_b.DeveloperIds, game_b._developer_names),
            )
        if threshold > 0.0:
            if ts * w.title + ys * w.year + ps * w.platform + ds * w.developer + w.publisher < threshold:
                return None

        # ── Publishers ───────────────────────────────────────────────────────
        if meta_a is not None and meta_b is not None:
            pus = _jaccard(meta_a.pub, meta_b.pub)
        else:
            pus = _jaccard(
                _name_set(game_a.PublisherIds, game_a._publisher_names),
                _name_set(game_b.PublisherIds, game_b._publisher_names),
            )

        score = (
            ts * w.title
            + ys * w.year
            + ps * w.platform
            + ds * w.developer
            + pus * w.publisher
        )

        details: Optional[dict[str, str]] = None
        if include_details:
            details = {
                "title_norm_a": na,
                "title_norm_b": nb,
                "title_score": f"{ts:.2f}",
                "year_a": str(game_a.release_year or "?"),
                "year_b": str(game_b.release_year or "?"),
                "year_score": f"{ys:.2f}",
                "platform_score": f"{ps:.2f}",
                "developer_score": f"{ds:.2f}",
                "publisher_score": f"{pus:.2f}",
            }

        return MatchResult(
            game_a_id=game_a.Id,
            game_b_id=game_b.Id,
            title_score=ts,
            year_score=ys,
            platform_score=ps,
            developer_score=ds,
            publisher_score=pus,
            score=score,
            details=details,
        )

    def quick_candidate(self, game_a: Game, game_b: Game, min_title_score: float = 0.6) -> bool:
        """
        Fast pre-filter: return True only if the normalised titles are
        *potentially* similar enough to warrant a full match computation.

        Uses a single cheap ``token_sort_ratio`` call rather than the full
        weighted calculation.
        """
        na = normalize_title(game_a.Name)
        nb = normalize_title(game_b.Name)
        if not na or not nb:
            return False
        return fuzz.token_sort_ratio(na, nb) / 100.0 >= min_title_score
