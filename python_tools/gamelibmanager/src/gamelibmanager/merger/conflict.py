"""Conflict detection for library merging."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from ..models.game import Game


@dataclass
class FieldConflict:
    """A single field-level conflict between source and target games."""

    field_name: str
    source_value: Any
    target_value: Any
    resolved_value: Any | None = None
    resolution_source: str = ""  # "source", "target", "merged", "user"


@dataclass
class ConflictRecord:
    """All conflicts for a single game pair."""

    source_game_id: uuid.UUID
    target_game_id: uuid.UUID
    game_name: str
    conflicts: list[FieldConflict] = field(default_factory=list)
    resolution_strategy: str = ""


class ConflictDetector:
    """Detects field-level conflicts between matching game pairs."""

    COMPARABLE_FIELDS = [
        "name", "description", "notes", "genre_ids", "developer_ids",
        "publisher_ids", "platform_ids", "category_ids", "tag_ids",
        "feature_ids", "series_ids", "age_rating_ids", "region_ids",
        "source_id", "release_date", "user_score", "critic_score",
        "community_score", "icon", "cover_image", "background_image",
        "links", "version", "completion_status_id",
    ]

    def detect_conflicts(self, source: Game, target: Game) -> list[FieldConflict]:
        conflicts: list[FieldConflict] = []
        for field_name in self.COMPARABLE_FIELDS:
            src_val = getattr(source, field_name, None)
            tgt_val = getattr(target, field_name, None)
            if self._values_differ(field_name, src_val, tgt_val):
                conflicts.append(FieldConflict(
                    field_name=field_name,
                    source_value=src_val,
                    target_value=tgt_val,
                ))
        return conflicts

    @staticmethod
    def _values_differ(field_name: str, val_a: Any, val_b: Any) -> bool:
        # Both None/empty → no conflict
        if val_a is None and val_b is None:
            return False
        if val_a == "" and val_b == "":
            return False
        if val_a is None and val_b == "":
            return False
        if val_a == "" and val_b is None:
            return False

        # One is None/empty, other is not → conflict
        if (val_a is None or val_a == "") and val_b:
            return True
        if val_a and (val_b is None or val_b == ""):
            return True

        # List comparison (order-independent)
        if isinstance(val_a, list) and isinstance(val_b, list):
            return set(str(x) for x in val_a) != set(str(x) for x in val_b)

        return val_a != val_b
