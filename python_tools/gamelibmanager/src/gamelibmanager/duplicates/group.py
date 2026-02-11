"""Duplicate group data structure."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class DuplicateGroup:
    """A group of games identified as duplicates.

    ``master_game_id`` is the game chosen as the canonical entry.
    ``member_game_ids`` lists all *other* games in the group.
    """

    group_id: int
    master_game_id: uuid.UUID
    member_game_ids: list[uuid.UUID] = field(default_factory=list)
    confidence_scores: dict[uuid.UUID, float] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.member_game_ids) + 1  # +1 for master

    @property
    def all_game_ids(self) -> list[uuid.UUID]:
        return [self.master_game_id] + list(self.member_game_ids)
