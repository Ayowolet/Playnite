"""Incremental merge support: only process changed games since last merge."""

from __future__ import annotations

import json
import os
from datetime import datetime

from ..models.game import Game


class IncrementalMerger:
    """Supports incremental merge by tracking last merge timestamp."""

    def __init__(self, db: object):
        from ..db.database import GameDatabase
        self._db: GameDatabase = db  # type: ignore[assignment]

    def get_last_merge_time(self, source_library: str) -> datetime | None:
        """Read last merge timestamp from merge_history table."""
        assert self._db.conn is not None
        # Fetch all merge history rows and compare paths case-insensitively
        # so that e.g. "C:\\Lib" matches "c:\\lib" on Windows.
        rows = self._db.conn.execute(
            "SELECT timestamp, source_library FROM merge_history "
            "ORDER BY id DESC",
        ).fetchall()
        norm = os.path.normcase(source_library)
        for row in rows:
            if os.path.normcase(row["source_library"]) == norm:
                return datetime.fromisoformat(row["timestamp"])
        return None

    def get_changed_games(
        self, source_db: object, since: datetime,
    ) -> list[Game]:
        """Return games from source_db modified since the given timestamp."""
        from ..db.database import GameDatabase
        sdb: GameDatabase = source_db  # type: ignore[assignment]
        all_games = sdb.get_all_games()
        return [
            g for g in all_games
            if g.modified and g.modified > since
        ]
