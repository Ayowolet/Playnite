"""Resolution history for undo/audit of duplicate actions."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ResolutionRecord:
    """A single duplicate resolution action."""

    id: int
    timestamp: datetime
    action: str  # 'merge', 'hide', 'delete', 'set_master', 'manual_override'
    master_game_id: uuid.UUID
    duplicate_game_ids: list[uuid.UUID]
    details: dict


class ResolutionHistory:
    """Tracks all duplicate resolution actions in the database."""

    def __init__(self, db: object):
        from ..db.database import GameDatabase
        self._db: GameDatabase = db  # type: ignore[assignment]

    def record(
        self,
        action: str,
        master_id: uuid.UUID,
        dup_ids: list[uuid.UUID],
        details: dict | None = None,
    ) -> int:
        assert self._db.conn is not None
        now = datetime.now().isoformat()
        cursor = self._db.conn.execute(
            "INSERT INTO duplicate_history (timestamp, action, master_game_id, "
            "duplicate_game_ids, details) VALUES (?, ?, ?, ?, ?)",
            (
                now,
                action,
                str(master_id),
                json.dumps([str(d) for d in dup_ids]),
                json.dumps(details or {}),
            ),
        )
        self._db.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_history(self, limit: int = 100) -> list[ResolutionRecord]:
        assert self._db.conn is not None
        rows = self._db.conn.execute(
            "SELECT * FROM duplicate_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_last(self) -> ResolutionRecord | None:
        records = self.get_history(limit=1)
        return records[0] if records else None

    def undo_last(self) -> ResolutionRecord | None:
        """Undo the most recent resolution action.

        For 'hide' actions: un-hides the duplicates.
        For 'delete' actions: cannot restore (returns the record for logging).
        For 'merge' actions: cannot un-merge (returns the record for logging).
        """
        record = self.get_last()
        if record is None:
            return None

        if record.action == "hide":
            for gid in record.duplicate_game_ids:
                game = self._db.get_game(gid)
                if game:
                    game.hidden = False
                    self._db.update_game(game)

        # Remove the history record
        assert self._db.conn is not None
        self._db.conn.execute(
            "DELETE FROM duplicate_history WHERE id = ?", (record.id,)
        )
        self._db.conn.commit()
        return record

    @staticmethod
    def _row_to_record(row) -> ResolutionRecord:
        return ResolutionRecord(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            action=row["action"],
            master_game_id=uuid.UUID(row["master_game_id"]),
            duplicate_game_ids=[
                uuid.UUID(s) for s in json.loads(row["duplicate_game_ids"])
            ],
            details=json.loads(row["details"]) if row["details"] else {},
        )
