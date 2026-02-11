"""Duplicate detection engine with blocking and union-find grouping."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from typing import Callable

from ..models.game import Game
from .config import DetectionConfig
from .group import DuplicateGroup
from .normalizer import TitleNormalizer
from .scorer import DuplicateScorer, MatchScore, _NameResolver

class DuplicateDetector:
    """Main duplicate detection engine.

    Algorithm:
    1. Load games, apply filters
    2. Pre-compute normalised titles
    3. Build candidate pairs using blocking (first N chars of normalised title)
    4. Score each candidate pair
    5. Group duplicates using union-find
    6. Select master for each group by source priority + metadata completeness
    """

    def __init__(self, db: object, config: DetectionConfig | None = None):
        from ..db.database import GameDatabase
        self._db: GameDatabase = db  # type: ignore[assignment]
        self.config = config or DetectionConfig()
        self.config.validate()
        resolver: _NameResolver | None = None
        try:
            from .scorer import create_name_resolver
            resolver = create_name_resolver(self._db)
        except Exception:
            pass
        self.scorer = DuplicateScorer(self.config.weights, resolver)

    def detect(
        self, progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[DuplicateGroup]:
        games, norms = self._load_and_filter()
        if len(games) < 2:
            return []

        # Build blocks: prefix -> list of indices
        prefix_len = self.config.blocking_prefix_length
        blocks: dict[str, list[int]] = defaultdict(list)
        for i, n in enumerate(norms):
            key = n[:prefix_len] if len(n) >= prefix_len else n
            blocks[key].append(i)

        # Union-find state
        parent: dict[int, int] = {}

        def find(x: int) -> int:
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        # Score pairs block-by-block; store only composite float
        pair_scores: dict[tuple[int, int], float] = {}
        processed = 0

        for indices in blocks.values():
            for a_pos in range(len(indices)):
                for b_pos in range(a_pos + 1, len(indices)):
                    i, j = indices[a_pos], indices[b_pos]
                    key = (min(i, j), max(i, j))
                    if key in pair_scores:
                        continue  # already scored via another block
                    ms = self.scorer.score_pair(games[i], games[j], norms[i], norms[j])
                    if ms.composite_score >= self.config.threshold:
                        pair_scores[key] = ms.composite_score
                        union(i, j)
                    processed += 1
                    if progress_callback and processed % 500 == 0:
                        progress_callback(processed, -1)

        # Free blocks — no longer needed
        del blocks

        groups = self._group_duplicates(pair_scores, parent, games)
        return groups

    def check_similarity(self, game: Game) -> list[DuplicateGroup]:
        """Check a single game against the library."""
        all_games, all_norms = self._load_and_filter()
        norm_target = TitleNormalizer.normalize(game.name)

        matches: list[tuple[int, MatchScore]] = []
        for i, g in enumerate(all_games):
            if g.id == game.id:
                continue
            ms = self.scorer.score_pair(game, g, norm_target, all_norms[i])
            if ms.composite_score >= self.config.threshold:
                matches.append((i, ms))

        if not matches:
            return []

        members = []
        confidences: dict[uuid.UUID, float] = {}
        for idx, ms in matches:
            members.append(all_games[idx].id)
            confidences[all_games[idx].id] = ms.composite_score

        return [DuplicateGroup(
            group_id=0,
            master_game_id=game.id,
            member_game_ids=members,
            confidence_scores=confidences,
        )]

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _load_and_filter(self) -> tuple[list[Game], list[str]]:
        games, norms = self._db.get_games_for_detection()
        f = self.config.filters
        filtered_games: list[Game] = []
        filtered_norms: list[str] = []
        for i, g in enumerate(games):
            if not f.include_hidden and g.hidden:
                continue
            if not f.include_uninstalled and not g.is_installed:
                continue
            if f.include_sources and g.source_id not in f.include_sources:
                continue
            if f.exclude_sources and g.source_id in f.exclude_sources:
                continue
            if f.include_platforms and g.platform_ids:
                if not set(g.platform_ids) & f.include_platforms:
                    continue
            if f.exclude_platforms and g.platform_ids:
                if set(g.platform_ids) & f.exclude_platforms:
                    continue
            if f.name_pattern:
                if not re.search(f.name_pattern, g.name, re.IGNORECASE):
                    continue
            filtered_games.append(g)
            filtered_norms.append(norms[i])
        return filtered_games, filtered_norms

    def _group_duplicates(
        self,
        pair_scores: dict[tuple[int, int], float],
        parent: dict[int, int],
        games: list[Game],
    ) -> list[DuplicateGroup]:
        """Build DuplicateGroup objects from union-find state."""

        def find(x: int) -> int:
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        # Collect groups
        all_involved: set[int] = set()
        for i, j in pair_scores:
            all_involved.add(i)
            all_involved.add(j)

        group_members: dict[int, list[int]] = defaultdict(list)
        for idx in all_involved:
            group_members[find(idx)].append(idx)

        groups: list[DuplicateGroup] = []
        for gid, (root, members) in enumerate(group_members.items()):
            unique_members = sorted(set(members))
            if len(unique_members) < 2:
                continue
            if len(unique_members) > self.config.max_group_size:
                unique_members = unique_members[: self.config.max_group_size]

            master_idx = self._select_master(unique_members, games)
            other_ids = [games[i].id for i in unique_members if i != master_idx]

            confidences: dict[uuid.UUID, float] = {}
            for i in unique_members:
                if i == master_idx:
                    continue
                pair_key = (min(master_idx, i), max(master_idx, i))
                if pair_key in pair_scores:
                    confidences[games[i].id] = pair_scores[pair_key]
                else:
                    # Indirect match — compute directly
                    ms = self.scorer.score_pair(games[master_idx], games[i])
                    confidences[games[i].id] = ms.composite_score

            groups.append(DuplicateGroup(
                group_id=gid,
                master_game_id=games[master_idx].id,
                member_game_ids=other_ids,
                confidence_scores=confidences,
            ))

        return groups

    def _select_master(self, indices: list[int], games: list[Game]) -> int:
        """Select master by: source priority → metadata completeness → newest modified."""
        source_priority = {
            name.lower(): idx
            for idx, name in enumerate(self.config.source_priority)
        }

        def _source_rank(g: Game) -> int:
            src = self._db.get_source(g.source_id)
            if src:
                return source_priority.get(src.name.lower(), 999)
            return 999

        def _completeness(g: Game) -> int:
            score = 0
            if g.description:
                score += 1
            if g.cover_image:
                score += 1
            if g.background_image:
                score += 1
            if g.icon:
                score += 1
            if g.release_date:
                score += 1
            if g.developer_ids:
                score += 1
            if g.publisher_ids:
                score += 1
            if g.genre_ids:
                score += 1
            if g.critic_score is not None:
                score += 1
            if g.community_score is not None:
                score += 1
            return score

        def _sort_key(idx: int) -> tuple:
            g = games[idx]
            return (
                _source_rank(g),
                -_completeness(g),
                -(g.modified.timestamp() if g.modified else 0),
            )

        return min(indices, key=_sort_key)
