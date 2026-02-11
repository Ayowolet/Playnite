"""Merge preview generation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..models.game import Game
from .conflict import FieldConflict


@dataclass
class MergePreview:
    """Preview of what a merge operation will do, without executing."""

    games_to_add: list[Game] = field(default_factory=list)
    games_to_update: list[tuple[Game, Game, list[FieldConflict]]] = field(
        default_factory=list
    )
    games_to_skip: list[Game] = field(default_factory=list)
    total_conflicts: int = 0
    media_files_to_copy: int = 0

    def to_json(self) -> str:
        return json.dumps({
            "games_to_add": len(self.games_to_add),
            "games_to_update": len(self.games_to_update),
            "games_to_skip": len(self.games_to_skip),
            "total_conflicts": self.total_conflicts,
            "media_files_to_copy": self.media_files_to_copy,
            "add_details": [
                {"id": str(g.id), "name": g.name} for g in self.games_to_add
            ],
            "update_details": [
                {
                    "source_id": str(src.id),
                    "target_id": str(tgt.id),
                    "name": tgt.name,
                    "conflicts": len(conflicts),
                    "conflict_fields": [c.field_name for c in conflicts],
                }
                for src, tgt, conflicts in self.games_to_update
            ],
            "skip_details": [
                {"id": str(g.id), "name": g.name} for g in self.games_to_skip
            ],
        }, indent=2)

    def to_text(self) -> str:
        lines = [
            "Merge Preview",
            "=" * 40,
            f"Games to add:    {len(self.games_to_add)}",
            f"Games to update: {len(self.games_to_update)}",
            f"Games to skip:   {len(self.games_to_skip)}",
            f"Total conflicts: {self.total_conflicts}",
            f"Media to copy:   {self.media_files_to_copy}",
            "",
        ]

        if self.games_to_add:
            lines.append("New games to add:")
            for g in self.games_to_add[:20]:
                lines.append(f"  + {g.name}")
            if len(self.games_to_add) > 20:
                lines.append(f"  ... and {len(self.games_to_add) - 20} more")
            lines.append("")

        if self.games_to_update:
            lines.append("Games to update:")
            for src, tgt, conflicts in self.games_to_update[:20]:
                fields = ", ".join(c.field_name for c in conflicts)
                lines.append(f"  ~ {tgt.name} ({len(conflicts)} conflicts: {fields})")
            if len(self.games_to_update) > 20:
                lines.append(f"  ... and {len(self.games_to_update) - 20} more")
            lines.append("")

        return "\n".join(lines)
