"""
Duplicate resolver: applies user decisions to a library.

Supported operations
--------------------
- ``hide_duplicates``   – mark non-master games as hidden.
- ``delete_duplicates`` – remove non-master games from the library.
- ``merge_into_master`` – copy missing metadata from duplicates onto master.
- ``set_master``        – override which game is the canonical master.
- ``ignore_group``      – record a group as intentionally kept (undo / audit).

All operations are logged in a ``ResolutionRecord`` list so they can be
replayed, undone, or exported for audit purposes.
"""
from __future__ import annotations

import datetime
import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ..models.game import Game
from ..models.library import Library
from .detector import DuplicateGroup


class ResolutionAction(str, Enum):
    HIDE_DUPLICATES = "hide_duplicates"
    DELETE_DUPLICATES = "delete_duplicates"
    MERGE_INTO_MASTER = "merge_into_master"
    SET_MASTER = "set_master"
    IGNORE_GROUP = "ignore_group"
    UNDO = "undo"


@dataclass
class ResolutionRecord:
    """Audit entry for a single resolution operation."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    action: ResolutionAction = ResolutionAction.IGNORE_GROUP
    group_id: str = ""
    master_id: str = ""
    affected_ids: list[str] = field(default_factory=list)
    notes: str = ""
    # Snapshot of affected games for undo
    snapshot: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "action": self.action.value,
            "group_id": self.group_id,
            "master_id": self.master_id,
            "affected_ids": self.affected_ids,
            "notes": self.notes,
        }


class DuplicateResolver:
    """
    Applies resolution decisions to a :class:`~game_library.models.Library`.

    All mutations are recorded in ``history`` for undo / audit.
    """

    def __init__(self, library: Library) -> None:
        self.library = library
        self.history: list[ResolutionRecord] = []

    # ── Bulk operations ───────────────────────────────────────────────────────

    def hide_duplicates(
        self, group: DuplicateGroup, notes: str = ""
    ) -> ResolutionRecord:
        """Mark all non-master games in *group* as hidden."""
        snapshot = [g.to_dict() for g in group.duplicates]
        affected: list[str] = []
        for dup in group.duplicates:
            game = self.library.get_game(dup.Id)
            if game:
                game.Hidden = True
                affected.append(game.Id)
        rec = ResolutionRecord(
            action=ResolutionAction.HIDE_DUPLICATES,
            group_id=group.id,
            master_id=group.master.Id,
            affected_ids=affected,
            notes=notes,
            snapshot=snapshot,
        )
        self.history.append(rec)
        return rec

    def delete_duplicates(
        self, group: DuplicateGroup, notes: str = ""
    ) -> ResolutionRecord:
        """Remove all non-master games in *group* from the library."""
        snapshot = [g.to_dict() for g in group.duplicates]
        affected: list[str] = []
        for dup in group.duplicates:
            removed = self.library.remove_game(dup.Id)
            if removed:
                affected.append(dup.Id)
        rec = ResolutionRecord(
            action=ResolutionAction.DELETE_DUPLICATES,
            group_id=group.id,
            master_id=group.master.Id,
            affected_ids=affected,
            notes=notes,
            snapshot=snapshot,
        )
        self.history.append(rec)
        return rec

    def merge_into_master(
        self,
        group: DuplicateGroup,
        fields_to_merge: Optional[list[str]] = None,
        notes: str = "",
    ) -> ResolutionRecord:
        """
        Copy missing metadata from duplicate games onto the master.

        Only fields that are empty / zero on the master are filled in.
        Playtime is summed across all group members.

        Parameters
        ----------
        fields_to_merge:
            If supplied, only these field names are considered.  Otherwise all
            fields with a sensible merge semantic are processed.
        """
        master = self.library.get_game(group.master.Id) or group.master
        snapshot = [master.to_dict()]
        affected = [master.Id]

        # Default mergeable fields
        MERGEABLE_SCALAR = [
            "Description", "Notes", "Version",
            "CoverImage", "BackgroundImage", "Icon",
            "CriticScore", "CommunityScore",
        ]
        MERGEABLE_LISTS = [
            "GenreIds", "TagIds", "CategoryIds",
            "SeriesIds", "AgeRatingIds", "RegionIds",
        ]

        if fields_to_merge is not None:
            MERGEABLE_SCALAR = [f for f in MERGEABLE_SCALAR if f in fields_to_merge]
            MERGEABLE_LISTS = [f for f in MERGEABLE_LISTS if f in fields_to_merge]

        for dup in group.duplicates:
            dup_game = self.library.get_game(dup.Id) or dup
            # Scalar fields
            for fname in MERGEABLE_SCALAR:
                if not getattr(master, fname, None):
                    val = getattr(dup_game, fname, None)
                    if val:
                        setattr(master, fname, val)
            # List fields – union
            for fname in MERGEABLE_LISTS:
                master_list: list = getattr(master, fname, [])
                dup_list: list = getattr(dup_game, fname, [])
                for item in dup_list:
                    if item not in master_list:
                        master_list.append(item)
                setattr(master, fname, master_list)
            # Playtime – sum
            master.Playtime = (master.Playtime or 0) + (dup_game.Playtime or 0)
            # PlayCount – max (most reliable)
            master.PlayCount = max(master.PlayCount or 0, dup_game.PlayCount or 0)
            # ReleaseDate – fill in if missing
            if not master.ReleaseDate and dup_game.ReleaseDate:
                master.ReleaseDate = dup_game.ReleaseDate
            affected.append(dup_game.Id)

        self.library.add_game(master)

        rec = ResolutionRecord(
            action=ResolutionAction.MERGE_INTO_MASTER,
            group_id=group.id,
            master_id=master.Id,
            affected_ids=affected,
            notes=notes,
            snapshot=snapshot,
        )
        self.history.append(rec)
        return rec

    def set_master(
        self, group: DuplicateGroup, new_master_id: str, notes: str = ""
    ) -> DuplicateGroup:
        """
        Override master selection.  Returns an updated group.
        """
        all_games = {g.Id: g for g in group.all_games}
        if new_master_id not in all_games:
            raise ValueError(f"Game {new_master_id!r} is not a member of group {group.id!r}")

        new_master = all_games[new_master_id]
        new_dups = [g for gid, g in all_games.items() if gid != new_master_id]
        new_scores = {g.Id: group.scores.get(g.Id, 0.0) for g in new_dups}

        rec = ResolutionRecord(
            action=ResolutionAction.SET_MASTER,
            group_id=group.id,
            master_id=new_master_id,
            affected_ids=list(all_games.keys()),
            notes=notes,
            snapshot=[g.to_dict() for g in all_games.values()],
        )
        self.history.append(rec)
        return DuplicateGroup(
            id=new_master_id,
            master=new_master,
            duplicates=new_dups,
            scores=new_scores,
            match_results=group.match_results,
        )

    def ignore_group(self, group: DuplicateGroup, notes: str = "") -> ResolutionRecord:
        """Record that a group was reviewed and intentionally kept as-is."""
        rec = ResolutionRecord(
            action=ResolutionAction.IGNORE_GROUP,
            group_id=group.id,
            master_id=group.master.Id,
            affected_ids=[g.Id for g in group.all_games],
            notes=notes,
        )
        self.history.append(rec)
        return rec

    def bulk_resolve(
        self,
        groups: list[DuplicateGroup],
        action: ResolutionAction,
        notes: str = "",
    ) -> list[ResolutionRecord]:
        """Apply *action* to all *groups* in one call."""
        records: list[ResolutionRecord] = []
        for group in groups:
            if action == ResolutionAction.HIDE_DUPLICATES:
                records.append(self.hide_duplicates(group, notes))
            elif action == ResolutionAction.DELETE_DUPLICATES:
                records.append(self.delete_duplicates(group, notes))
            elif action == ResolutionAction.MERGE_INTO_MASTER:
                records.append(self.merge_into_master(group, notes=notes))
            elif action == ResolutionAction.IGNORE_GROUP:
                records.append(self.ignore_group(group, notes))
        return records

    # ── Undo ─────────────────────────────────────────────────────────────────

    def undo_last(self) -> Optional[ResolutionRecord]:
        """
        Undo the most recent resolution action.

        For HIDE_DUPLICATES: un-hides the affected games.
        For DELETE_DUPLICATES: restores the games from the snapshot.
        For MERGE_INTO_MASTER: restores the master to its pre-merge state.
        """
        if not self.history:
            return None

        last = self.history[-1]
        if last.action == ResolutionAction.HIDE_DUPLICATES:
            for game_dict in last.snapshot:
                game = Game.from_dict(game_dict)
                existing = self.library.get_game(game.Id)
                if existing:
                    existing.Hidden = game.Hidden
        elif last.action == ResolutionAction.DELETE_DUPLICATES:
            for game_dict in last.snapshot:
                game = Game.from_dict(game_dict)
                self.library.add_game(game)
        elif last.action == ResolutionAction.MERGE_INTO_MASTER:
            for game_dict in last.snapshot:
                game = Game.from_dict(game_dict)
                self.library.add_game(game)

        undo_record = ResolutionRecord(
            action=ResolutionAction.UNDO,
            group_id=last.group_id,
            master_id=last.master_id,
            notes=f"Undo of {last.action.value} ({last.id})",
        )
        self.history.pop()
        self.history.append(undo_record)
        return undo_record

    # ── History persistence ───────────────────────────────────────────────────

    def save_history(self, path: str | Path) -> None:
        """Save resolution history to a JSON file."""
        Path(path).write_text(
            json.dumps([r.to_dict() for r in self.history], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_history(self, path: str | Path) -> None:
        """Load resolution history from a previously saved JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for entry in data:
            rec = ResolutionRecord(
                id=entry.get("id", str(uuid.uuid4())),
                timestamp=entry.get("timestamp", ""),
                action=ResolutionAction(entry.get("action", "ignore_group")),
                group_id=entry.get("group_id", ""),
                master_id=entry.get("master_id", ""),
                affected_ids=entry.get("affected_ids", []),
                notes=entry.get("notes", ""),
            )
            self.history.append(rec)
