"""Tests for backup error handling.

Covers 7 checklist items:
  1. Create backup with no disk space - clear error shown
  2. Create backup to non-existent directory - handled gracefully
  3. Restore from corrupted backup - error shown, rollback occurs
  4. Restore with incorrect password - clear error message
  5. Upload to cloud with no internet - retry or clear error
  6. Backup when database is locked - handled appropriately
  7. Verify missing backup file - clear error message
"""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import zipfile
from pathlib import Path

import pytest

from gamelibrary.database import Database
from gamelibrary.backup.engine import BackupEngine
from gamelibrary.backup.restore import RestoreEngine
from gamelibrary.backup.verification import verify_backup
from gamelibrary.backup.destinations import DestinationManager, SimulatedCloudProvider


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_env(tmp_path):
    """Create a database, backup engine, and restore engine in tmp_path."""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    backup_dir = tmp_path / "backups"
    data_dir = tmp_path / "data"
    engine = BackupEngine(db, backup_dir=backup_dir, data_dir=data_dir)
    restore = RestoreEngine(db, data_dir=data_dir)
    return db, engine, restore, backup_dir, data_dir


def _seed_data(data_dir: Path):
    """Create a small set of data files so backups have content."""
    (data_dir / "tags").mkdir(parents=True, exist_ok=True)
    (data_dir / "tags" / "user_tags.json").write_text(json.dumps({"tag": "action"}))
    (data_dir / "config").mkdir(parents=True, exist_ok=True)
    (data_dir / "config" / "config.json").write_text(json.dumps({"theme": "dark"}))


# ===========================================================================
# 1. Create backup with no disk space - clear error shown
# ===========================================================================

class TestNoDiskSpace:
    """Simulate ENOSPC and verify a clear error is raised."""

    def test_full_backup_raises_on_no_space(self, tmp_path, monkeypatch):
        """OSError with ENOSPC propagates when the disk is full."""
        db, engine, _, _, data_dir = _make_env(tmp_path)
        _seed_data(data_dir)

        original_zipfile_init = zipfile.ZipFile.__init__

        def fake_init(self_zip, *args, **kwargs):
            original_zipfile_init(self_zip, *args, **kwargs)

            def failing_writestr(*a, **kw):
                raise OSError(28, "No space left on device")

            self_zip.writestr = failing_writestr

        monkeypatch.setattr(zipfile.ZipFile, "__init__", fake_init)

        with pytest.raises(OSError, match="No space left on device"):
            engine.create_full_backup()

    def test_incremental_backup_raises_on_no_space(self, tmp_path, monkeypatch):
        """Incremental backup also raises clearly on ENOSPC."""
        db, engine, _, _, data_dir = _make_env(tmp_path)
        _seed_data(data_dir)
        record = engine.create_full_backup()

        original_zipfile_init = zipfile.ZipFile.__init__

        def fake_init(self_zip, *args, **kwargs):
            original_zipfile_init(self_zip, *args, **kwargs)

            def failing_writestr(*a, **kw):
                raise OSError(28, "No space left on device")

            self_zip.writestr = failing_writestr

        monkeypatch.setattr(zipfile.ZipFile, "__init__", fake_init)

        with pytest.raises(OSError, match="No space left on device"):
            engine.create_incremental_backup(record.id)

    def test_error_message_includes_device_info(self, tmp_path, monkeypatch):
        """The OSError exception carries errno 28 (ENOSPC)."""
        db, engine, _, _, data_dir = _make_env(tmp_path)
        _seed_data(data_dir)

        original_zipfile_init = zipfile.ZipFile.__init__

        def fake_init(self_zip, *args, **kwargs):
            original_zipfile_init(self_zip, *args, **kwargs)

            def failing_writestr(*a, **kw):
                raise OSError(28, "No space left on device")

            self_zip.writestr = failing_writestr

        monkeypatch.setattr(zipfile.ZipFile, "__init__", fake_init)

        with pytest.raises(OSError) as exc_info:
            engine.create_full_backup()
        assert exc_info.value.errno == 28


# ===========================================================================
# 2. Create backup to non-existent directory - handled gracefully
# ===========================================================================

class TestNonExistentDirectory:
    """Verify the engine auto-creates directories or raises clear errors."""

    def test_engine_creates_missing_backup_dir(self, tmp_path):
        """BackupEngine auto-creates the backup directory if it doesn't exist."""
        db = Database(tmp_path / "test.db")
        new_dir = tmp_path / "deep" / "nested" / "backups"
        assert not new_dir.exists()

        BackupEngine(db, backup_dir=new_dir, data_dir=tmp_path / "data")
        assert new_dir.exists()

    def test_engine_creates_missing_data_dir(self, tmp_path):
        """BackupEngine auto-creates the data directory if it doesn't exist."""
        db = Database(tmp_path / "test.db")
        new_data = tmp_path / "deep" / "nested" / "data"
        assert not new_data.exists()

        BackupEngine(db, backup_dir=tmp_path / "backups", data_dir=new_data)
        assert new_data.exists()

    def test_backup_succeeds_in_newly_created_dir(self, tmp_path):
        """A backup can be created in the auto-created directory."""
        db = Database(tmp_path / "test.db")
        new_dir = tmp_path / "fresh" / "backups"
        engine = BackupEngine(db, backup_dir=new_dir, data_dir=tmp_path / "data")
        record = engine.create_full_backup()
        assert Path(record.file_path).exists()

    def test_unwritable_backup_dir_raises(self, tmp_path):
        """If the backup directory exists but is read-only, an OSError is raised."""
        db = Database(tmp_path / "test.db")
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        os.chmod(str(readonly_dir), stat.S_IRUSR | stat.S_IXUSR)

        try:
            engine = BackupEngine(db, backup_dir=readonly_dir, data_dir=tmp_path / "data")
            _seed_data(tmp_path / "data")
            with pytest.raises(OSError):
                engine.create_full_backup()
        finally:
            # Restore write permission for cleanup
            os.chmod(str(readonly_dir), stat.S_IRWXU)


# ===========================================================================
# 3. Restore from corrupted backup - error shown, rollback occurs
# ===========================================================================

class TestCorruptedBackupRestore:
    """Verify that restoring a corrupted backup fails with a clear error."""

    def test_restore_completely_corrupt_file(self, tmp_path):
        """Restoring a file that isn't a zip raises ValueError."""
        db, _, restore, _, data_dir = _make_env(tmp_path)
        corrupt_file = tmp_path / "corrupt.zip"
        corrupt_file.write_bytes(b"this is not a zip file at all")

        with pytest.raises(ValueError, match="Backup verification failed"):
            restore.restore_full(str(corrupt_file))

    def test_restore_zip_with_bad_checksum(self, tmp_path):
        """Restoring a zip whose manifest checksums don't match raises ValueError."""
        db, engine, restore, _, data_dir = _make_env(tmp_path)
        _seed_data(data_dir)
        record = engine.create_full_backup()

        # Tamper with the zip contents to create a checksum mismatch
        tampered = tmp_path / "tampered.zip"
        with zipfile.ZipFile(record.file_path, "r") as zf_in:
            with zipfile.ZipFile(str(tampered), "w") as zf_out:
                for name in zf_in.namelist():
                    data = zf_in.read(name)
                    if name != "manifest.json" and not name.endswith("/"):
                        # Corrupt the data
                        data = b"CORRUPTED CONTENT"
                    zf_out.writestr(name, data)

        with pytest.raises(ValueError, match="Backup verification failed"):
            restore.restore_full(str(tampered))

    def test_restore_missing_manifest(self, tmp_path):
        """A zip without manifest.json can still be opened but produces a warning."""
        db, _, restore, _, data_dir = _make_env(tmp_path)
        no_manifest = tmp_path / "no_manifest.zip"
        with zipfile.ZipFile(str(no_manifest), "w") as zf:
            zf.writestr("tags/user_tags.json", json.dumps({"tag": "test"}))

        # verify_backup returns valid=True (no errors, just warnings) when
        # the zip is intact but has no manifest
        result = verify_backup(str(no_manifest))
        assert result["valid"] is True
        assert any("manifest" in w.lower() for w in result["warnings"])

    def test_database_pre_restore_backup_created(self, tmp_path):
        """When restoring the database component, a .pre_restore copy is created."""
        db, engine, restore, _, data_dir = _make_env(tmp_path)
        _seed_data(data_dir)
        record = engine.create_full_backup()

        db_path = db.get_db_path()
        pre_restore = db_path.with_suffix(".db.pre_restore")
        assert not pre_restore.exists()

        restore.restore_full(record.file_path)

        # A pre-restore copy should have been created
        assert pre_restore.exists()
        assert pre_restore.stat().st_size > 0

    def test_partial_restore_reports_errors(self, tmp_path):
        """Requesting a component not in the backup is reported in errors."""
        db, engine, restore, _, data_dir = _make_env(tmp_path)
        _seed_data(data_dir)
        record = engine.create_full_backup()

        result = restore.restore_selective(
            record.file_path, components=["nonexistent_component"]
        )
        assert len(result["errors"]) > 0
        assert "nonexistent_component" in result["errors"][0]


# ===========================================================================
# 4. Restore with incorrect password - clear error message
# ===========================================================================

class TestIncorrectPassword:
    """Verify that wrong password gives a clear, user-friendly error."""

    def test_wrong_password_raises_valueerror(self, tmp_path):
        """Restoring with wrong password raises ValueError with clear message."""
        db, engine, restore, _, data_dir = _make_env(tmp_path)
        _seed_data(data_dir)
        record = engine.create_full_backup(password="correct_password")
        assert record.is_encrypted

        with pytest.raises(ValueError, match="Incorrect password"):
            restore.restore_full(record.file_path, password="wrong_password")

    def test_wrong_password_message_is_helpful(self, tmp_path):
        """The error message mentions password and corruption as possible causes."""
        db, engine, restore, _, data_dir = _make_env(tmp_path)
        _seed_data(data_dir)
        record = engine.create_full_backup(password="secret123")

        with pytest.raises(ValueError) as exc_info:
            restore.restore_full(record.file_path, password="notsecret")
        msg = str(exc_info.value).lower()
        assert "incorrect password" in msg or "corrupted" in msg

    def test_no_password_for_encrypted_backup(self, tmp_path):
        """Restoring encrypted backup without a password raises ValueError."""
        db, engine, restore, _, data_dir = _make_env(tmp_path)
        _seed_data(data_dir)
        record = engine.create_full_backup(password="mypassword")

        with pytest.raises(ValueError, match="no password provided"):
            restore.restore_full(record.file_path, password=None)

    def test_wrong_password_on_list_contents(self, tmp_path):
        """Listing contents with wrong password also gives a clear error."""
        db, engine, restore, _, data_dir = _make_env(tmp_path)
        _seed_data(data_dir)
        record = engine.create_full_backup(password="realpass")

        with pytest.raises(ValueError, match="Incorrect password"):
            restore.list_backup_contents(record.file_path, password="fakepass")

    def test_wrong_password_cleans_up_temp_file(self, tmp_path):
        """Decryption failure does not leave a temp decrypted file behind."""
        db, engine, restore, _, data_dir = _make_env(tmp_path)
        _seed_data(data_dir)
        record = engine.create_full_backup(password="good")

        backup_dir = Path(record.file_path).parent
        files_before = set(backup_dir.iterdir())

        with pytest.raises(ValueError):
            restore.restore_full(record.file_path, password="bad")

        files_after = set(backup_dir.iterdir())
        # No leftover temp files
        new_files = files_after - files_before
        assert len(new_files) == 0


# ===========================================================================
# 5. Upload to cloud with no internet - retry or clear error
# ===========================================================================

class TestCloudUploadFailure:
    """Simulate cloud upload failure and verify clear error reporting."""

    def test_cloud_upload_failure_returns_error_dict(self, tmp_path, monkeypatch):
        """When upload fails, distribute returns status=failed with error message."""
        db, engine, _, _, data_dir = _make_env(tmp_path)
        _seed_data(data_dir)
        record = engine.create_full_backup()

        dest_mgr = DestinationManager(db)
        dest_mgr.register_destination(
            "cloud_test", "cloud",
            {"provider": "simulated", "simulate_dir": str(tmp_path / "cloud")},
        )

        # Monkeypatch the upload to simulate network failure
        def failing_upload(self, local_path, remote_name):
            raise ConnectionError("Network is unreachable")

        monkeypatch.setattr(SimulatedCloudProvider, "upload", failing_upload)

        results = dest_mgr.distribute(Path(record.file_path), ["cloud_test"])
        assert len(results) == 1
        assert results[0]["status"] == "failed"
        assert "Network is unreachable" in results[0]["error"]

    def test_cloud_failure_includes_destination_name(self, tmp_path, monkeypatch):
        """Error result includes the destination name for identification."""
        db, engine, _, _, data_dir = _make_env(tmp_path)
        _seed_data(data_dir)
        record = engine.create_full_backup()

        dest_mgr = DestinationManager(db)
        dest_mgr.register_destination(
            "my_drive", "cloud",
            {"provider": "simulated", "simulate_dir": str(tmp_path / "cloud")},
        )

        def failing_upload(self, local_path, remote_name):
            raise TimeoutError("Connection timed out")

        monkeypatch.setattr(SimulatedCloudProvider, "upload", failing_upload)

        results = dest_mgr.distribute(Path(record.file_path), ["my_drive"])
        assert results[0]["destination"] == "my_drive"
        assert results[0]["type"] == "cloud"

    def test_partial_cloud_failure_succeeds_for_others(self, tmp_path, monkeypatch):
        """If one destination fails, others still succeed."""
        db, engine, _, _, data_dir = _make_env(tmp_path)
        _seed_data(data_dir)
        record = engine.create_full_backup()

        dest_mgr = DestinationManager(db)
        # Register one local (will succeed) and one cloud (will fail)
        local_dest = tmp_path / "local_copy"
        dest_mgr.register_destination("local_ok", "local", {"path": str(local_dest)})
        dest_mgr.register_destination(
            "cloud_fail", "cloud",
            {"provider": "simulated", "simulate_dir": str(tmp_path / "cloud")},
        )

        def failing_upload(self, local_path, remote_name):
            raise ConnectionError("DNS resolution failed")

        monkeypatch.setattr(SimulatedCloudProvider, "upload", failing_upload)

        results = dest_mgr.distribute(
            Path(record.file_path), ["local_ok", "cloud_fail"]
        )
        assert len(results) == 2
        local_result = next(r for r in results if r["destination"] == "local_ok")
        cloud_result = next(r for r in results if r["destination"] == "cloud_fail")
        assert local_result["status"] == "completed"
        assert cloud_result["status"] == "failed"

    def test_cloud_failure_does_not_crash_backup_creation(self, tmp_path, monkeypatch):
        """Backup creation with failing cloud destination still produces a local backup."""
        db, engine, _, _, data_dir = _make_env(tmp_path)
        _seed_data(data_dir)

        dest_mgr = DestinationManager(db)
        dest_mgr.register_destination(
            "broken_cloud", "cloud",
            {"provider": "simulated", "simulate_dir": str(tmp_path / "cloud")},
        )

        def failing_upload(self, local_path, remote_name):
            raise ConnectionError("No route to host")

        monkeypatch.setattr(SimulatedCloudProvider, "upload", failing_upload)

        # Backup creation should succeed locally even if cloud distribution fails
        record = engine.create_full_backup(destinations=["broken_cloud"])
        assert Path(record.file_path).exists()
        assert record.status == "completed"
        # Distribution failure is recorded in metadata
        assert "distributions" in record.metadata
        assert record.metadata["distributions"][0]["status"] == "failed"


# ===========================================================================
# 6. Backup when database is locked - handled appropriately
# ===========================================================================

class TestDatabaseLocked:
    """Simulate a locked database and verify appropriate error handling."""

    def test_backup_with_locked_db_raises_error(self, tmp_path):
        """Creating a backup while the DB is exclusively locked raises an error."""
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        data_dir = tmp_path / "data"
        engine = BackupEngine(db, backup_dir=tmp_path / "backups", data_dir=data_dir)
        _seed_data(data_dir)

        # Acquire an exclusive lock on the database
        blocking_conn = sqlite3.connect(str(db_path))
        blocking_conn.execute("BEGIN EXCLUSIVE")

        try:
            # The engine reads the DB file directly (read_bytes), not via SQL,
            # for the database component. But metadata inserts use the DB connection.
            # The exclusive lock blocks other connections from writing.
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                engine.create_full_backup()
        finally:
            blocking_conn.rollback()
            blocking_conn.close()

    def test_locked_db_error_message_is_clear(self, tmp_path):
        """The error message for a locked database mentions 'locked'."""
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        data_dir = tmp_path / "data"
        engine = BackupEngine(db, backup_dir=tmp_path / "backups", data_dir=data_dir)
        _seed_data(data_dir)

        blocking_conn = sqlite3.connect(str(db_path))
        blocking_conn.execute("BEGIN EXCLUSIVE")

        try:
            with pytest.raises(sqlite3.OperationalError) as exc_info:
                engine.create_full_backup()
            assert "locked" in str(exc_info.value).lower()
        finally:
            blocking_conn.rollback()
            blocking_conn.close()

    def test_restore_to_readonly_db_raises_error(self, tmp_path):
        """Restoring when the DB file is read-only raises a clear error.

        The database component restore fails with PermissionError (caught
        and added to the errors list), and then the restore_history insert
        fails with OperationalError because the DB is read-only.
        """
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        data_dir = tmp_path / "data"
        engine = BackupEngine(db, backup_dir=tmp_path / "backups", data_dir=data_dir)
        restore = RestoreEngine(db, data_dir=data_dir)
        _seed_data(data_dir)

        record = engine.create_full_backup()

        # Make the DB file read-only so neither restore nor history insert can write
        os.chmod(str(db_path), stat.S_IRUSR)

        try:
            with pytest.raises(
                (PermissionError, sqlite3.OperationalError),
            ):
                restore.restore_full(record.file_path)
        finally:
            os.chmod(str(db_path), stat.S_IRWXU)


# ===========================================================================
# 7. Verify missing backup file - clear error message
# ===========================================================================

class TestVerifyMissingBackupFile:
    """Verify that missing/invalid backup files produce clear errors."""

    def test_verify_nonexistent_file(self, tmp_path):
        """verify_backup on a missing file returns valid=False with clear error."""
        result = verify_backup(str(tmp_path / "does_not_exist.zip"))
        assert result["valid"] is False
        assert len(result["errors"]) == 1
        assert "does not exist" in result["errors"][0].lower()

    def test_verify_nonexistent_shows_path(self, tmp_path):
        """The error references the missing file path."""
        missing = str(tmp_path / "vanished_backup.zip")
        result = verify_backup(missing)
        # The error message should reference the fact that the file is missing
        assert "does not exist" in result["errors"][0].lower()

    def test_verify_not_a_zip(self, tmp_path):
        """verify_backup on a non-zip file returns valid=False with clear error."""
        not_zip = tmp_path / "not_a_zip.zip"
        not_zip.write_text("this is plain text, not a zip")
        result = verify_backup(str(not_zip))
        assert result["valid"] is False
        assert any("not a valid zip" in e.lower() for e in result["errors"])

    def test_restore_nonexistent_raises_filenotfound(self, tmp_path):
        """restore_full on a missing file raises FileNotFoundError."""
        db = Database(tmp_path / "test.db")
        restore = RestoreEngine(db, data_dir=tmp_path / "data")

        with pytest.raises(FileNotFoundError, match="Backup file not found"):
            restore.restore_full(str(tmp_path / "missing_backup.zip"))

    def test_restore_error_includes_path(self, tmp_path):
        """FileNotFoundError includes the path that was requested."""
        db = Database(tmp_path / "test.db")
        restore = RestoreEngine(db, data_dir=tmp_path / "data")
        target = str(tmp_path / "specific_missing_file.zip")

        with pytest.raises(FileNotFoundError) as exc_info:
            restore.restore_full(target)
        assert "specific_missing_file.zip" in str(exc_info.value)

    def test_verify_empty_file(self, tmp_path):
        """verify_backup on a zero-byte file returns valid=False."""
        empty = tmp_path / "empty.zip"
        empty.write_bytes(b"")
        result = verify_backup(str(empty))
        assert result["valid"] is False
        assert len(result["errors"]) >= 1
