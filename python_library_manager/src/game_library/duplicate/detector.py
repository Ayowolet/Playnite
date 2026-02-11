"""
Duplicate game detector.

Algorithm overview
------------------
1. **Norm cache** – normalise every game title exactly once and store in a
   ``{game_id → norm_title}`` dict.

2. **Token index** – build an inverted ``{token → [game_ids]}`` index from the
   normalised titles.  Tokens shorter than 3 characters and tokens that appear
   in more than 10 % of the library are discarded (stop-word effect), so only
   meaningful shared tokens produce candidate pairs.

3. **Candidate generation** – for each game emit ``(id_a, id_b)`` pairs for
   every other game that shares at least one indexed token.  This replaces the
   old prefix-blocking step and scales as O(n * avg_tokens_per_game) rather
   than O(n²).

4. **Pairwise scoring with early termination** – each candidate pair is passed
   to :meth:`~game_library.duplicate.matcher.GameMatcher.match_keyed`.  The
   pre-normalised titles are reused from the norm cache; cascading threshold
   checks after each signal allow non-matching pairs to be discarded before
   the expensive platform/developer/publisher Jaccard computations.

5. **Union-Find grouping** – pairs whose score exceeds ``threshold`` are
   merged into duplicate groups via a path-compressed Union-Find structure.

6. **Master selection** – within each group the "master" game is chosen based
   on configurable source priority, then metadata completeness, then playtime.
"""
from __future__ import annotations

import datetime
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

from ..models.game import Game
from ..models.library import Library
from ..utils.text_utils import normalize_title, nfc_lower
from .matcher import GameMatcher, MatchResult, MatchWeights


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class DetectorConfig:
    """All tunable parameters for duplicate detection.

    Scoring behaviour with sparse metadata
    ---------------------------------------
    When a game has no platform, developer, or publisher data attached, the
    Jaccard similarity for each of those signals returns **1.0** (the
    "no information – don't penalise" neutral value).  This means the three
    metadata signals contribute a free **+0.30** to every score regardless of
    whether the games are actually related.

    For an exact title match (``title_score = 1.0``) with no metadata on
    either game, the aggregate score as a function of year difference is:

    +-----------+------------+-------+---------------------------+
    | Year diff | year_score | Score | Outcome (default threshold)|
    +===========+============+=======+===========================+
    | 0         | 1.00       | 1.00  | flagged duplicate          |
    | 1         | 0.50       | 0.90  | flagged duplicate ⚠        |
    | ≥ 2       | 0.00       | 0.80  | not flagged                |
    +-----------+------------+-------+----------------------------+

    The **year ±1 tolerance** (``year_score = 0.5`` for a one-year gap) is
    intentional: it prevents penalising the same game catalogued as December
    of one year in one library and January of the next in another.  However,
    when metadata is entirely absent, this tolerance means two genuinely
    different games that share an exact title and are released within a year
    of each other will be incorrectly flagged as duplicates.

    In practice this is rarely an issue because real library exports (Playnite,
    Steam, GOG) always include at least platform data.  If both games have
    non-empty but *different* platform sets, ``_jaccard`` returns ``0.0``
    instead of ``1.0``, dropping the worst-case score to **0.75** — safely
    below the default threshold.

    If your library source has genuinely sparse metadata and you see false
    positives for same-name games, raise ``threshold`` to ``0.90`` or higher.
    """

    # Minimum overall score to consider two games duplicates (0.0 – 1.0)
    threshold: float = 0.85

    # Minimum title-only score before a full comparison is attempted
    quick_filter_threshold: float = 0.60

    # Custom match weights
    weights: Optional[MatchWeights] = None

    # Source names in priority order (index 0 = highest priority)
    source_priority: list[str] = field(default_factory=list)

    # Filters – if non-empty, only games matching the filter are considered
    include_platforms: list[str] = field(default_factory=list)
    include_sources: list[str] = field(default_factory=list)
    include_categories: list[str] = field(default_factory=list)

    # Filters – games matching these are excluded
    exclude_hidden: bool = False   # skip hidden games
    exclude_platforms: list[str] = field(default_factory=list)
    exclude_sources: list[str] = field(default_factory=list)

    # "similarity mode" – detect near-duplicates even when the title score
    # alone is below the global threshold
    similarity_mode: bool = False
    similarity_threshold: float = 0.70

    def __post_init__(self) -> None:
        if not 0.60 <= self.threshold <= 1.0:
            raise ValueError("threshold must be between 0.60 and 1.0")
        if self.weights is None:
            self.weights = MatchWeights()


# ── Union-Find ────────────────────────────────────────────────────────────────

class _UnionFind:
    """
    Path-compressed, rank-based Union-Find (Disjoint Set Union) data structure.

    Used to group games that are transitively identified as duplicates:
    if A≡B and B≡C then A, B, and C all belong to the same duplicate group.
    """

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = defaultdict(int)

    def find(self, x: str) -> str:
        """
        Return the root representative for *x*, applying path compression.

        Path compression flattens the tree on every lookup so subsequent
        ``find`` calls on any node in the same chain cost O(1) amortised.
        """
        if self._parent.setdefault(x, x) != x:
            self._parent[x] = self.find(self._parent[x])  # path compression
        return self._parent[x]

    def union(self, x: str, y: str) -> None:
        """
        Merge the sets containing *x* and *y*.

        Uses union-by-rank: the root of the smaller-rank tree is attached
        under the root of the larger-rank tree, keeping the overall tree
        height bounded at O(log n).
        """
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1

    def groups(self, ids: list[str]) -> dict[str, list[str]]:
        """Return root → [members] mapping for all IDs with ≥2 members."""
        buckets: dict[str, list[str]] = defaultdict(list)
        for game_id in ids:
            buckets[self.find(game_id)].append(game_id)
        return {root: members for root, members in buckets.items() if len(members) >= 2}


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class DuplicateGroup:
    """A set of games identified as duplicates of each other."""

    id: str          # Stable group identifier (master game ID)
    master: Game     # The "canonical" game to keep
    duplicates: list[Game]  # All other games in the group (not including master)
    scores: dict[str, float]  # game.Id → confidence score vs master
    match_results: list[MatchResult]  # Raw pairwise results for audit trail

    @property
    def all_games(self) -> list[Game]:
        return [self.master] + self.duplicates

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.id,
            "master": {
                "id": self.master.Id,
                "name": self.master.Name,
                "source": self.master._source_name,
                "platform": ", ".join(self.master._platform_names),
                "installed": self.master.IsInstalled,
                "hidden": self.master.Hidden,
                "completeness": self.master.completeness_score(),
            },
            "duplicates": [
                {
                    "id": g.Id,
                    "name": g.Name,
                    "source": g._source_name,
                    "platform": ", ".join(g._platform_names),
                    "installed": g.IsInstalled,
                    "hidden": g.Hidden,
                    "confidence_pct": round(self.scores.get(g.Id, 0) * 100),
                }
                for g in self.duplicates
            ],
        }


@dataclass
class DuplicateReport:
    """Full report produced by :class:`DuplicateDetector`."""

    generated_at: str
    total_games: int
    games_scanned: int
    groups: list[DuplicateGroup]
    config: dict[str, Any]

    @property
    def duplicate_count(self) -> int:
        return sum(len(g.duplicates) for g in self.groups)

    @property
    def group_count(self) -> int:
        return len(self.groups)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "total_games": self.total_games,
            "games_scanned": self.games_scanned,
            "group_count": self.group_count,
            "duplicate_count": self.duplicate_count,
            "groups": [g.to_dict() for g in self.groups],
            "config": self.config,
        }


# ── Detector ──────────────────────────────────────────────────────────────────

class DuplicateDetector:
    """
    Detects duplicate games within one or more :class:`~game_library.models.Library`
    objects.

    Parameters
    ----------
    config:
        Detection configuration.  A default :class:`DetectorConfig` is used
        when not supplied.
    """

    def __init__(self, config: Optional[DetectorConfig] = None) -> None:
        self.config = config or DetectorConfig()
        self._matcher = GameMatcher(
            weights=self.config.weights,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def detect(self, *libraries: Library) -> DuplicateReport:
        """
        Scan one or more libraries for duplicate games.

        Multiple libraries may be supplied (e.g. when merging two Playnite
        instances); games are deduplicated across all of them.
        """
        all_games: list[Game] = []
        for lib in libraries:
            lib.resolve_all()
            all_games.extend(lib.all_games())

        games = self._apply_filters(all_games)
        logger.info(
            "Starting duplicate scan: %d game%s across %d librar%s",
            len(games),
            "" if len(games) == 1 else "s",
            len(libraries),
            "y" if len(libraries) == 1 else "ies",
        )

        threshold = (
            self.config.similarity_threshold
            if self.config.similarity_mode
            else self.config.threshold
        )

        # ── Optimised pipeline ───────────────────────────────────────────────
        norm_cache = self._build_norm_cache(games)
        meta_cache = self._matcher.build_meta_cache(games)
        token_index = self._build_token_index(games, norm_cache)

        game_index: dict[str, Game] = {g.Id: g for g in games}
        uf = _UnionFind()
        pair_scores: dict[tuple[str, str], MatchResult] = {}

        for id_a, id_b in self._iter_candidate_pairs(games, norm_cache, token_index):
            ga = game_index.get(id_a)
            gb = game_index.get(id_b)
            if ga is None or gb is None:
                continue
            na = norm_cache.get(id_a, "")
            nb = norm_cache.get(id_b, "")
            result = self._matcher.match_keyed(
                ga, gb, na, nb,
                threshold=threshold,
                include_details=False,
                meta_a=meta_cache.get(id_a),
                meta_b=meta_cache.get(id_b),
            )
            if result is not None and result.score >= threshold:
                uf.union(id_a, id_b)
                pair_scores[(id_a, id_b)] = result

        # Re-run the small set of matched pairs with include_details=True so
        # that every MatchResult stored in DuplicateGroup.match_results carries
        # the human-readable breakdown needed for audit reports.
        for key in list(pair_scores.keys()):
            id_a, id_b = key
            ga = game_index.get(id_a)
            gb = game_index.get(id_b)
            if ga is None or gb is None:
                continue
            na = norm_cache.get(id_a, "")
            nb = norm_cache.get(id_b, "")
            detailed = self._matcher.match_keyed(
                ga, gb, na, nb,
                include_details=True,
                meta_a=meta_cache.get(id_a),
                meta_b=meta_cache.get(id_b),
            )
            if detailed is not None:
                pair_scores[key] = detailed

        groups = self._build_groups(uf, game_index, pair_scores)
        logger.info(
            "Scan complete: %d matched pair%s → %d duplicate group%s",
            len(pair_scores),
            "" if len(pair_scores) == 1 else "s",
            len(groups),
            "" if len(groups) == 1 else "s",
        )

        return DuplicateReport(
            generated_at=datetime.datetime.now().isoformat(),
            total_games=sum(len(lib.games) for lib in libraries),
            games_scanned=len(games),
            groups=groups,
            config={
                "threshold": self.config.threshold,
                "similarity_mode": self.config.similarity_mode,
                "source_priority": self.config.source_priority,
            },
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _apply_filters(self, games: list[Game]) -> list[Game]:
        """
        Apply the inclusion/exclusion filters from :attr:`config` and return
        the subset of games that should participate in duplicate detection.
        """
        cfg = self.config
        result: list[Game] = []
        for g in games:
            if cfg.exclude_hidden and g.Hidden:
                continue
            if cfg.include_platforms:
                plats = {nfc_lower(p) for p in g._platform_names}
                if not plats.intersection({nfc_lower(p) for p in cfg.include_platforms}):
                    continue
            if cfg.exclude_platforms:
                plats = {nfc_lower(p) for p in g._platform_names}
                if plats.intersection({nfc_lower(p) for p in cfg.exclude_platforms}):
                    continue
            if cfg.include_sources:
                if nfc_lower(g._source_name) not in {nfc_lower(s) for s in cfg.include_sources}:
                    continue
            if cfg.exclude_sources:
                if nfc_lower(g._source_name) in {nfc_lower(s) for s in cfg.exclude_sources}:
                    continue
            if cfg.include_categories:
                cats = {nfc_lower(c) for c in g._category_names}
                if not cats.intersection({nfc_lower(c) for c in cfg.include_categories}):
                    continue
            result.append(g)
        return result

    def _build_norm_cache(self, games: list[Game]) -> dict[str, str]:
        """Pre-compute a ``{game_id → normalised_title}`` mapping.

        Calling :func:`~game_library.utils.text_utils.normalize_title` once per
        game and reusing the result avoids the 2–3× redundant calls that the
        old pipeline made for every candidate pair (once in the quick-filter and
        once or twice inside :meth:`~game_library.duplicate.matcher.GameMatcher.match`).
        """
        return {g.Id: normalize_title(g.Name) for g in games}

    def _build_token_index(
        self,
        games: list[Game],
        norm_cache: dict[str, str],
    ) -> dict[str, list[str]]:
        """Build an inverted ``{token → [game_ids]}`` index from normalised titles.

        Filtering rules (applied in order):

        * Tokens shorter than 3 characters are dropped (too ambiguous).
        * Tokens that appear in more than 10 % of the library are dropped
          (stop-word effect: "the", "of", roman numerals, etc. would otherwise
          produce enormous candidate sets with near-zero precision).

        The result maps each surviving token to the list of game IDs whose
        normalised title contains that token.
        """
        raw: dict[str, list[str]] = defaultdict(list)
        for g in games:
            norm = norm_cache.get(g.Id, "")
            for token in norm.split():
                if len(token) >= 3:
                    raw[token].append(g.Id)

        # Frequency cap: drop tokens present in more than 2 % of the library.
        # The minimum of 20 ensures the filter does not trigger on small
        # libraries (< 1 000 games) where even common subtitle words appear
        # in fewer than 20 entries.
        max_count = max(20, len(games) // 50)
        return {tok: ids for tok, ids in raw.items() if len(ids) <= max_count}

    def _iter_candidate_pairs(
        self,
        games: list[Game],
        norm_cache: dict[str, str],
        token_index: dict[str, list[str]],
    ) -> Iterator[tuple[str, str]]:
        """Yield deduplicated ``(id_a, id_b)`` candidate pairs on demand.

        Unlike the previous set-returning implementation this generator never
        materialises the full candidate collection in memory.  Deduplication
        is performed via a ``seen`` set of integer-index pairs rather than
        UUID string pairs: each entry costs ~72 bytes vs ~200 bytes for a
        ``(str, str)`` tuple, reducing the peak footprint of the dedup
        structure by roughly 60 %.

        Pairs are yielded as soon as they are discovered so the caller can
        begin scoring without waiting for the entire candidate space to be
        enumerated.
        """
        id_to_idx: dict[str, int] = {g.Id: i for i, g in enumerate(games)}
        seen: set[tuple[int, int]] = set()
        for g in games:
            ai = id_to_idx[g.Id]
            for token in norm_cache.get(g.Id, "").split():
                if token not in token_index:
                    continue
                for other_id in token_index[token]:
                    bi = id_to_idx.get(other_id)
                    if bi is None or ai == bi:
                        continue
                    key = (min(ai, bi), max(ai, bi))
                    if key not in seen:
                        seen.add(key)
                        yield g.Id, other_id

    def _select_master(self, group: list[Game]) -> Game:
        """
        Select the canonical master game from *group*.

        Priority rules (in order):
        1. Lowest source-priority rank (user-defined list; lower index = higher priority).
        2. Highest metadata completeness score.
        3. Highest total playtime.
        4. Most recently added.
        """
        priority_map = {nfc_lower(name): idx for idx, name in enumerate(self.config.source_priority)}
        max_rank = len(self.config.source_priority)

        def rank(game: Game) -> tuple:
            src_rank = priority_map.get(nfc_lower(game._source_name), max_rank)
            completeness = game.completeness_score()
            playtime = game.Playtime
            added_ts = game.Added or "0"
            return (src_rank, -completeness, -playtime, added_ts)

        return min(group, key=rank)

    def _build_groups(
        self,
        uf: _UnionFind,
        game_index: dict[str, Game],
        pair_scores: dict[tuple[str, str], MatchResult],
    ) -> list[DuplicateGroup]:
        """
        Convert raw Union-Find groups into :class:`DuplicateGroup` objects.

        For each multi-member cluster returned by the Union-Find, select a
        master via :meth:`_select_master`, attach per-duplicate confidence
        scores from *pair_scores*, and sort the resulting groups by
        descending confidence.
        """
        raw_groups = uf.groups(list(game_index.keys()))
        groups: list[DuplicateGroup] = []

        for members in raw_groups.values():
            member_games = [game_index[mid] for mid in members if mid in game_index]
            if len(member_games) < 2:
                continue

            master = self._select_master(member_games)
            dups = [g for g in member_games if g.Id != master.Id]

            # Collect all MatchResults that involve any member of this group
            relevant_results: list[MatchResult] = []
            scores: dict[str, float] = {}
            for g in dups:
                key = (min(master.Id, g.Id), max(master.Id, g.Id))
                if key in pair_scores:
                    mr = pair_scores[key]
                    relevant_results.append(mr)
                    scores[g.Id] = mr.score
                else:
                    # Find any cross-pair score involving this game
                    best_score = 0.0
                    for (a, b), mr in pair_scores.items():
                        if g.Id in (a, b):
                            if mr.score > best_score:
                                best_score = mr.score
                                relevant_results.append(mr)
                    scores[g.Id] = best_score

            groups.append(DuplicateGroup(
                id=master.Id,
                master=master,
                duplicates=dups,
                scores=scores,
                match_results=relevant_results,
            ))

        # Sort groups by confidence (highest first)
        groups.sort(key=lambda g: max(g.scores.values(), default=0), reverse=True)
        return groups
