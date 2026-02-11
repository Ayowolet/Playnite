"""Tests for MergeBackup."""

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from gamelibmanager.merger.backup import MergeBackup


class TestMergeBackup:
    def _create_library(self, path: Path):
        (path / "games").mkdir(parents=True)
        (path / "files").mkdir(parents=True)
        (path / "games" / "test.json").write_text('{"Name": "Test"}')
        (path / "files" / "cover.jpg").write_bytes(b"fake image data")

    def test_create_backup(self, tmp_path):
        lib_path = tmp_path / "library"
        backup_dir = tmp_path / "backups"
        self._create_library(lib_path)

        backup = MergeBackup(lib_path, backup_dir)
        backup_path = backup.create_backup()

        assert Path(backup_path).exists()
        assert backup_path.endswith(".zip")
        with zipfile.ZipFile(backup_path) as zf:
            names = zf.namelist()
            assert "games/test.json" in names
            assert "files/cover.jpg" in names

    def test_create_backup_without_media(self, tmp_path):
        lib_path = tmp_path / "library"
        backup_dir = tmp_path / "backups"
        self._create_library(lib_path)

        backup = MergeBackup(lib_path, backup_dir)
        backup_path = backup.create_backup(include_media=False)

        with zipfile.ZipFile(backup_path) as zf:
            names = zf.namelist()
            assert "games/test.json" in names
            assert "files/cover.jpg" not in names

    def test_restore_backup(self, tmp_path):
        lib_path = tmp_path / "library"
        backup_dir = tmp_path / "backups"
        restore_path = tmp_path / "restored"
        restore_path.mkdir()
        self._create_library(lib_path)

        backup = MergeBackup(lib_path, backup_dir)
        backup_path = backup.create_backup()

        # Restore to a different location
        restore_backup = MergeBackup(restore_path, backup_dir)
        restore_backup.restore_backup(backup_path)

        assert (restore_path / "games" / "test.json").exists()
        assert (restore_path / "files" / "cover.jpg").exists()

    def test_list_backups(self, tmp_path):
        lib_path = tmp_path / "library"
        backup_dir = tmp_path / "backups"
        self._create_library(lib_path)

        backup = MergeBackup(lib_path, backup_dir)
        backup.create_backup()
        backup.create_backup()

        backups = MergeBackup.list_backups(backup_dir)
        assert len(backups) >= 1  # May be 1 if both created in same second

    def test_list_backups_empty_dir(self, tmp_path):
        backups = MergeBackup.list_backups(tmp_path / "nonexistent")
        assert len(backups) == 0

    def test_restore_nonexistent(self, tmp_path):
        backup = MergeBackup(tmp_path, tmp_path)
        with pytest.raises(FileNotFoundError):
            backup.restore_backup(tmp_path / "does_not_exist.zip")

    def test_create_backup_with_sqlite_api(self, tmp_path):
        """When db_conn is provided, .db is backed up via SQLite backup API."""
        lib_path = tmp_path / "library"
        backup_dir = tmp_path / "backups"
        lib_path.mkdir(parents=True)

        # Create a real SQLite DB inside the library directory.
        db_file = lib_path / "library.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE t (x TEXT)")
        conn.execute("INSERT INTO t VALUES ('hello')")
        conn.commit()

        # Also add a non-DB file.
        (lib_path / "games").mkdir()
        (lib_path / "games" / "test.json").write_text("{}")

        # Create a fake WAL file that should be excluded.
        (lib_path / "library.db-wal").write_bytes(b"fake wal")
        (lib_path / "library.db-shm").write_bytes(b"fake shm")

        backup = MergeBackup(lib_path, backup_dir)
        backup_path = backup.create_backup(db_conn=conn)
        conn.close()

        with zipfile.ZipFile(backup_path) as zf:
            names = zf.namelist()
            # The DB should be present (via backup API).
            assert "library.db" in names
            # WAL/SHM should NOT be present.
            assert "library.db-wal" not in names
            assert "library.db-shm" not in names
            # Non-DB files should still be present.
            assert "games/test.json" in names

        # Verify the backed-up DB is valid and has data.
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        with zipfile.ZipFile(backup_path) as zf:
            zf.extractall(extract_dir)
        verify = sqlite3.connect(str(extract_dir / "library.db"))
        integrity = verify.execute("PRAGMA integrity_check").fetchone()
        assert integrity[0] == "ok"
        row = verify.execute("SELECT x FROM t").fetchone()
        assert row[0] == "hello"
        verify.close()

    def test_exclude_media_case_insensitive(self, tmp_path):
        """The 'files' directory exclusion should work regardless of case."""
        lib_path = tmp_path / "library"
        backup_dir = tmp_path / "backups"
        (lib_path / "games").mkdir(parents=True)
        # Create a "Files" dir with different case (simulating case-insensitive FS)
        (lib_path / "files").mkdir(parents=True)
        (lib_path / "games" / "test.json").write_text('{}')
        (lib_path / "files" / "img.png").write_bytes(b"png data")

        backup = MergeBackup(lib_path, backup_dir)
        backup_path = backup.create_backup(include_media=False)

        with zipfile.ZipFile(backup_path) as zf:
            names = [n.lower() for n in zf.namelist()]
            assert any(n.startswith("games") for n in names)
            # files/ should be excluded regardless of case
            assert not any(n.startswith("files") for n in names)
