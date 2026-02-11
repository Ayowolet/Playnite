"""
Conflict detection and resolution for library merges.

A *conflict* exists when two matched games have different values for the same
field and neither value is empty.  :class:`ConflictResolver` applies a
:class:`~game_library.merger.strategies.MergeStrategy` to resolve each one
and returns a new merged :class:`~game_library.models.Game`.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# Game fields that store file-system paths.  Compared case-insensitively with
# normalised separators so that paths from different Windows Playnite libraries
# (which may differ in case or use / vs \) do not produce spurious conflicts.
_PATH_FIELDS = frozenset({"CoverImage", "BackgroundImage", "Icon"})

from ..models.game import Game
from .strategies import MergeField, MergeStrategy, apply_strategy, _is_empty


class ConflictType(str, Enum):
    """Classifies the nature of a field-level conflict between two games."""

    SCALAR_MISMATCH = "scalar_mismatch"    # Different non-empty scalar values
    LIST_MISMATCH = "list_mismatch"        # Different non-empty lists
    MISSING_IN_MASTER = "missing_in_master"
    MISSING_IN_SOURCE = "missing_in_source"


@dataclass
class Conflict:
    """Represents a single field-level conflict between two matched games."""

    field: str
    conflict_type: ConflictType
    master_value: Any
    source_value: Any
    resolved_value: Any = None
    strategy_used: Optional[MergeStrategy] = None

    def to_dict(self) -> dict[str, Any]:
        def _fmt(v: Any) -> Any:
            if isinstance(v, list):
                return v[:5]  # truncate for display
            if hasattr(v, "to_dict"):
                return v.to_dict()
            return v

        return {
            "field": self.field,
            "type": self.conflict_type.value,
            "master": _fmt(self.master_value),
            "source": _fmt(self.source_value),
            "resolved": _fmt(self.resolved_value),
            "strategy": self.strategy_used.value if self.strategy_used else None,
        }


# Fields that are compared for conflicts; order determines display order.
_COMPARABLE_FIELDS: list[str] = [
    "Name", "SortingName", "Description", "Notes", "Version",
    "ReleaseDate",
    "PlatformIds", "DeveloperIds", "PublisherIds",
    "GenreIds", "CategoryIds", "TagIds", "SeriesIds",
    "AgeRatingIds", "RegionIds",
    "CoverImage", "BackgroundImage", "Icon",
    "UserScore", "CriticScore", "CommunityScore",
    "Playtime", "PlayCount", "LastActivity",
    "Links", "IsInstalled", "Favorite",
]

_LIST_FIELDS = frozenset({
    "PlatformIds", "DeveloperIds", "PublisherIds",
    "GenreIds", "CategoryIds", "TagIds", "SeriesIds",
    "AgeRatingIds", "RegionIds", "Links",
})


def _get_field(game: Game, fname: str) -> Any:
    """Return the value of *fname* from *game*, normalising empties."""
    val = getattr(game, fname, None)
    if isinstance(val, list):
        return list(val)
    if hasattr(val, "to_dict"):
        return val  # ReleaseDate, Link etc.
    return val


def _path_key(s: str) -> str:
    """Return a normalised, case-folded form of path string *s*.

    Unifies directory separators (``\\`` → ``/``) and applies ``casefold()``
    so that paths on case-insensitive file-systems (Windows, macOS HFS+)
    compare as equal regardless of the casing used by each library.
    """
    return s.replace("\\", "/").rstrip("/").casefold()


def _values_equal(a: Any, b: Any, field: str = "") -> bool:
    """
    Return True if *a* and *b* are semantically equal for conflict purposes.

    Lists are compared order-insensitively by string representation.
    Objects with a ``to_dict`` method (e.g. :class:`~game_library.models.game.ReleaseDate`)
    are compared by their dict representation.
    String fields in :data:`_PATH_FIELDS` are compared via :func:`_path_key`
    (case-insensitive, separator-normalised) so that paths from different
    Windows Playnite libraries do not produce spurious conflicts.
    All other string fields are compared after NFC normalisation.
    """
    if isinstance(a, list) and isinstance(b, list):
        return sorted(str(x) for x in a) == sorted(str(x) for x in b)
    if hasattr(a, "to_dict") and hasattr(b, "to_dict"):
        return a.to_dict() == b.to_dict()
    if isinstance(a, str) and isinstance(b, str):
        if field in _PATH_FIELDS:
            return _path_key(a) == _path_key(b)
        return unicodedata.normalize("NFC", a) == unicodedata.normalize("NFC", b)
    return a == b


class ConflictResolver:
    """
    Identifies conflicts between *master* and *source* games and applies the
    configured strategy to produce a merged result.
    """

    def __init__(self, strategy: MergeStrategy = MergeStrategy.MERGE_PREFER_MASTER) -> None:
        self.strategy = strategy
        # Per-field strategy overrides (optional)
        self.field_overrides: dict[str, MergeStrategy] = {}

    def detect_conflicts(self, master: Game, source: Game) -> list[Conflict]:
        """Return all field-level conflicts between *master* and *source*."""
        conflicts: list[Conflict] = []
        for fname in _COMPARABLE_FIELDS:
            mv = _get_field(master, fname)
            sv = _get_field(source, fname)

            mv_empty = _is_empty(mv)
            sv_empty = _is_empty(sv)

            if mv_empty and sv_empty:
                continue
            if mv_empty:
                conflicts.append(Conflict(
                    field=fname,
                    conflict_type=ConflictType.MISSING_IN_MASTER,
                    master_value=mv,
                    source_value=sv,
                ))
            elif sv_empty:
                conflicts.append(Conflict(
                    field=fname,
                    conflict_type=ConflictType.MISSING_IN_SOURCE,
                    master_value=mv,
                    source_value=sv,
                ))
            elif not _values_equal(mv, sv, fname):
                ctype = ConflictType.LIST_MISMATCH if fname in _LIST_FIELDS else ConflictType.SCALAR_MISMATCH
                conflicts.append(Conflict(
                    field=fname,
                    conflict_type=ctype,
                    master_value=mv,
                    source_value=sv,
                ))
        return conflicts

    def resolve(self, master: Game, source: Game) -> tuple[Game, list[Conflict]]:
        """
        Apply the merge strategy to produce a new merged game.

        Returns the merged game (a modified copy of *master*) and the list of
        conflicts that were encountered and resolved.
        """
        import copy
        merged = copy.deepcopy(master)
        conflicts = self.detect_conflicts(master, source)

        for conflict in conflicts:
            fname = conflict.field
            strategy = self.field_overrides.get(fname, self.strategy)
            resolved = apply_strategy(fname, conflict.master_value, conflict.source_value, strategy)
            conflict.resolved_value = resolved
            conflict.strategy_used = strategy
            if hasattr(merged, fname):
                setattr(merged, fname, resolved)

        return merged, conflicts
