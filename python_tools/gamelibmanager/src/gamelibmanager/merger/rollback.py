"""Rollback manager for merge operations."""

from __future__ import annotations

from pathlib import Path
from ..db.concurrency import retry_on_lock
from .backup import MergeBackup


class RollbackManager:
    """Manages transaction rollback for merge operations.

    Uses SQLite savepoints for database changes and ZIP backup for file changes.
    """

    def __init__(self, db: object, backup_dir: str | Path, library_path: str | Path):
        from ..db.database import GameDatabase
        self._db: GameDatabase = db  # type: ignore[assignment]
        self._backup = MergeBackup(library_path, backup_dir)
        self._backup_path: str | None = None
        self._in_transaction = False

    @property
    def backup_path(self) -> str | None:
        return self._backup_path

    @retry_on_lock("begin merge transaction")
    def begin_merge(self, include_media: bool = True) -> str:
        """Create backup and begin transaction. Returns backup path."""
        assert self._db.conn is not None
        self._backup_path = self._backup.create_backup(
            include_media=include_media,
            db_conn=self._db.conn,
        )
        self._db.conn.execute("BEGIN")
        self._in_transaction = True
        return self._backup_path

    def savepoint(self, name: str) -> None:
        assert self._db.conn is not None
        self._db.conn.execute(f"SAVEPOINT {name}")

    def release(self, name: str) -> None:
        assert self._db.conn is not None
        self._db.conn.execute(f"RELEASE SAVEPOINT {name}")

    def rollback_step(self, name: str) -> None:
        """Rollback to a named savepoint (partial undo)."""
        assert self._db.conn is not None
        self._db.conn.execute(f"ROLLBACK TO SAVEPOINT {name}")

    def rollback_all(self) -> None:
        """Full rollback: ROLLBACK transaction + restore file backup.

        Not retried — rollback failures must surface immediately.
        """
        if self._in_transaction:
            assert self._db.conn is not None
            self._db.conn.rollback()
            self._in_transaction = False
        if self._backup_path:
            self._backup.restore_backup(self._backup_path)

    @retry_on_lock("commit merge transaction")
    def commit(self) -> None:
        """Commit the merge transaction."""
        if self._in_transaction:
            assert self._db.conn is not None
            self._db.conn.commit()
            self._in_transaction = False
