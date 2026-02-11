"""Integration tests for concurrent database access during merge operations."""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest
from gamelibmanager.db.concurrency import DatabaseLockedError
from gamelibmanager.db.database import GameDatabase
from gamelibmanager.merger.config import MergeConfig
from gamelibmanager.merger.engine import LibraryMerger
from gamelibmanager.merger.strategy import MergeStrategyType
from tests.factories import make_game, make_lookup_tables


def _setup_library(db: GameDatabase, num_games: int = 5) -> None:
    """Populate a database with lookup tables and games."""
    make_lookup_tables(db)
    games = [make_game(name=f"Game {i}") for i in range(num_games)]
    db.add_games_batch(games)


class TestPreflightCheck:
    def test_preflight_detects_exclusive_lock(self, tmp_path):
        db_path = tmp_path / "locked.db"
        db = GameDatabase(str(db_path))
        db.open()

        # Second connection holds an exclusive lock.
        blocker = sqlite3.connect(str(db_path))
        blocker.execute("BEGIN EXCLUSIVE")
        try:
            with pytest.raises(DatabaseLockedError):
                db.check_write_access(timeout_ms=100)
        finally:
            blocker.rollback()
            blocker.close()
            db.close()

    def test_preflight_succeeds_with_wal_reader(self, tmp_path):
        db_path = tmp_path / "wal.db"
        db = GameDatabase(str(db_path))
        db.open()
        _setup_library(db)

        # Second connection reading in WAL mode should not block writes.
        reader = sqlite3.connect(str(db_path))
        reader.execute("PRAGMA journal_mode=WAL")
        reader.execute("SELECT * FROM games")
        try:
            # Pre-flight should succeed.
            db.check_write_access(timeout_ms=500)
        finally:
            reader.close()
            db.close()


class TestMergeConcurrency:
    def _make_source_target(self, tmp_path, source_count=3, target_count=2):
        """Create source and target databases with disjoint games."""
        src_path = tmp_path / "source.db"
        tgt_path = tmp_path / "target.db"

        src_db = GameDatabase(str(src_path))
        src_db.open()
        make_lookup_tables(src_db)
        src_games = [make_game(name=f"Source Game {i}") for i in range(source_count)]
        src_db.add_games_batch(src_games)

        tgt_db = GameDatabase(str(tgt_path))
        tgt_db.open()
        make_lookup_tables(tgt_db)
        tgt_games = [make_game(name=f"Target Game {i}") for i in range(target_count)]
        tgt_db.add_games_batch(tgt_games)

        return src_db, tgt_db, tgt_path

    def test_merge_succeeds_with_concurrent_reader(self, tmp_path):
        src_db, tgt_db, tgt_path = self._make_source_target(tmp_path)

        # Hold a read connection on the target DB.
        reader = sqlite3.connect(str(tgt_path))
        reader.execute("PRAGMA journal_mode=WAL")
        reader.execute("SELECT * FROM games")

        try:
            config = MergeConfig(
                strategy_type=MergeStrategyType.MERGE_ALL,
                source_library_path=str(tmp_path / "source.db"),
                target_library_path=str(tmp_path / "target.db"),
                backup_dir="",
            )
            merger = LibraryMerger(src_db, tgt_db, config)
            report = merger.execute()

            assert report.games_added == 3
            assert not report.errors
        finally:
            reader.close()
            src_db.close()
            tgt_db.close()

    def test_merge_reports_lock_error_with_exclusive_lock(self, tmp_path):
        src_db, tgt_db, tgt_path = self._make_source_target(tmp_path)

        # Hold exclusive lock on target so writes fail.
        blocker = sqlite3.connect(str(tgt_path))
        blocker.execute("BEGIN EXCLUSIVE")

        try:
            config = MergeConfig(
                strategy_type=MergeStrategyType.MERGE_ALL,
                source_library_path=str(tmp_path / "source.db"),
                target_library_path=str(tmp_path / "target.db"),
                backup_dir="",
            )
            merger = LibraryMerger(src_db, tgt_db, config)
            report = merger.execute()

            # The merge should report errors (lock prevented writes).
            assert report.errors or report.games_added == 0
        finally:
            blocker.rollback()
            blocker.close()
            src_db.close()
            tgt_db.close()

    def test_merge_survives_brief_lock(self, tmp_path):
        """A brief exclusive lock that is released before busy_timeout
        should let the merge succeed via SQLite busy_timeout."""
        src_db, tgt_db, tgt_path = self._make_source_target(tmp_path)

        lock_released = threading.Event()

        def hold_lock_briefly():
            conn = sqlite3.connect(str(tgt_path))
            conn.execute("BEGIN EXCLUSIVE")
            time.sleep(0.2)
            conn.rollback()
            conn.close()
            lock_released.set()

        t = threading.Thread(target=hold_lock_briefly)
        t.start()
        # Let the lock get established.
        time.sleep(0.05)

        try:
            config = MergeConfig(
                strategy_type=MergeStrategyType.MERGE_ALL,
                source_library_path=str(tmp_path / "source.db"),
                target_library_path=str(tmp_path / "target.db"),
                backup_dir="",
            )
            merger = LibraryMerger(src_db, tgt_db, config)
            report = merger.execute()

            # busy_timeout=30s should be long enough to wait out 0.2s lock.
            assert report.games_added == 3
            assert not report.errors
        finally:
            t.join(timeout=5)
            src_db.close()
            tgt_db.close()

    def test_backup_consistent_under_concurrent_write(self, tmp_path):
        """SQLite backup API produces a valid DB even when another
        thread is writing rapidly."""
        db_path = tmp_path / "busy.db"
        db = GameDatabase(str(db_path))
        db.open()
        _setup_library(db, num_games=5)

        stop_event = threading.Event()

        def writer():
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            i = 0
            while not stop_event.is_set():
                try:
                    conn.execute(
                        "INSERT INTO games (id, name) VALUES (?, ?)",
                        (str(i), f"Writer Game {i}"),
                    )
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # Lock contention is expected
                i += 1
                time.sleep(0.01)
            conn.close()

        t = threading.Thread(target=writer)
        t.start()
        time.sleep(0.05)

        dest = tmp_path / "backup.db"
        try:
            db.sqlite_backup(str(dest))
        finally:
            stop_event.set()
            t.join(timeout=5)
            db.close()

        # The backup should be a valid SQLite database.
        verify = sqlite3.connect(str(dest))
        integrity = verify.execute("PRAGMA integrity_check").fetchone()
        assert integrity[0] == "ok"
        count = verify.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        # At least the original 5 games should be present.
        assert count >= 5
        verify.close()
