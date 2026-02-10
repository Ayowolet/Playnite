"""Tests for disaster recovery module."""


import pytest
from pathlib import Path

from gamelibrary.database import Database
from gamelibrary.backup.engine import BackupEngine
from gamelibrary.backup.disaster_recovery import DisasterRecovery


@pytest.fixture
def dr_setup(tmp_path):
    """Set up disaster recovery test environment."""
    db_path = tmp_path / "test.db"
    backup_dir = tmp_path / "backups"
    data_dir = tmp_path / "data"
    backup_dir.mkdir()
    data_dir.mkdir()

    db = Database(db_path)
    engine = BackupEngine(db, backup_dir, data_dir)
    dr = DisasterRecovery(db, backup_dir, data_dir)
    return db, engine, dr, tmp_path


class TestCheckDatabaseHealth:
    def test_healthy_database(self, dr_setup):
        db, engine, dr, tmp_path = dr_setup
        result = dr.check_database_health()
        assert result["exists"] is True
        assert result["healthy"] is True
        assert result["size_bytes"] > 0
        assert result["issues"] == []

    def test_missing_database(self, tmp_path):
        db_path = tmp_path / "nonexistent.db"
        db = Database(db_path)
        # Remove the file after Database.__init__ creates it
        db_path.unlink()
        dr = DisasterRecovery(db, tmp_path / "backups", tmp_path / "data")
        result = dr.check_database_health()
        assert result["exists"] is False
        assert result["healthy"] is False
        assert len(result["issues"]) > 0

    def test_corrupt_database(self, tmp_path):
        db_path = tmp_path / "corrupt.db"
        db_path.write_bytes(b"not a database at all!!!")
        db = Database.__new__(Database)
        db.db_path = db_path
        dr = DisasterRecovery(db, tmp_path / "backups", tmp_path / "data")
        result = dr.check_database_health()
        assert result["exists"] is True
        assert result["healthy"] is False

    def test_health_check_reports_path(self, dr_setup):
        db, engine, dr, tmp_path = dr_setup
        result = dr.check_database_health()
        assert "path" in result
        assert str(db.get_db_path()) == result["path"]


class TestRecoverFromBackup:
    def test_recover_from_backup(self, dr_setup):
        db, engine, dr, tmp_path = dr_setup
        # Seed some data
        db.execute_insert(
            "INSERT INTO platforms (name, api_type) VALUES (?, ?)",
            ("TestPlatform", "manual"),
        )
        # Create a backup
        engine.create_full_backup()

        # Corrupt the database by removing a table's data
        db.execute("DELETE FROM platforms")
        rows = db.execute("SELECT COUNT(*) as cnt FROM platforms")
        assert rows[0]["cnt"] == 0

        # Recover
        result = dr.recover_from_backup()
        assert "recovered_from" in result
        assert result["items_restored"] > 0

    def test_recover_no_backups_raises(self, tmp_path):
        db_path = tmp_path / "test.db"
        backup_dir = tmp_path / "empty_backups"
        backup_dir.mkdir()
        db = Database(db_path)
        dr = DisasterRecovery(db, backup_dir)
        with pytest.raises(RuntimeError, match="No valid backups"):
            dr.recover_from_backup()

    def test_recover_returns_dict(self, dr_setup):
        db, engine, dr, tmp_path = dr_setup
        engine.create_full_backup()
        result = dr.recover_from_backup()
        assert isinstance(result, dict)
        assert "restored_at" in result


class TestRebuildDatabase:
    def test_rebuild_creates_fresh_db(self, dr_setup):
        db, engine, dr, tmp_path = dr_setup
        result = dr.rebuild_database()
        assert result["status"] == "rebuilt"
        assert "new_database" in result
        # The new database should exist
        assert Path(result["new_database"]).exists()

    def test_rebuild_backs_up_corrupt_db(self, dr_setup):
        db, engine, dr, tmp_path = dr_setup
        result = dr.rebuild_database()
        if result["corrupt_backup"]:
            assert Path(result["corrupt_backup"]).exists()

    def test_rebuild_when_no_existing_db(self, tmp_path):
        db_path = tmp_path / "rebuild_test.db"
        db = Database(db_path)
        # Remove the database file
        db_path.unlink()
        dr = DisasterRecovery(db, tmp_path / "backups", tmp_path / "data")
        result = dr.rebuild_database()
        assert result["status"] == "rebuilt"
        assert result["corrupt_backup"] is None


class TestExportForMigration:
    def test_export_creates_file(self, dr_setup):
        db, engine, dr, tmp_path = dr_setup
        output_path = tmp_path / "export" / "migration.zip"
        result = dr.export_for_migration(output_path)
        assert output_path.exists()
        assert result["size_bytes"] > 0
        assert result["exported_to"] == str(output_path)

    def test_export_has_checksum(self, dr_setup):
        db, engine, dr, tmp_path = dr_setup
        output_path = tmp_path / "export" / "migration.zip"
        result = dr.export_for_migration(output_path)
        assert result["checksum"]
        assert len(result["checksum"]) == 64  # SHA-256 hex digest

    def test_export_encrypted(self, dr_setup):
        db, engine, dr, tmp_path = dr_setup
        output_path = tmp_path / "export" / "migration.zip.enc"
        result = dr.export_for_migration(output_path, password="secret")
        assert result["is_encrypted"] is True


class TestImportFromBackup:
    def test_import_restores_data(self, dr_setup):
        db, engine, dr, tmp_path = dr_setup
        # Seed data
        db.execute_insert(
            "INSERT INTO platforms (name, api_type) VALUES (?, ?)",
            ("ImportTest", "manual"),
        )
        # Create and export backup
        record = engine.create_full_backup()

        # Clear and re-import
        db.execute("DELETE FROM platforms")
        result = dr.import_from_backup(record.file_path)
        assert result["items_restored"] > 0

    def test_import_nonexistent_raises(self, dr_setup):
        db, engine, dr, tmp_path = dr_setup
        with pytest.raises(FileNotFoundError):
            dr.import_from_backup(tmp_path / "nonexistent.zip")


class TestFindValidBackups:
    def test_finds_zip_backups(self, dr_setup):
        db, engine, dr, tmp_path = dr_setup
        engine.create_full_backup()
        backups = dr._find_valid_backups()
        assert len(backups) >= 1
        assert all(str(b).endswith(".zip") for b in backups)

    def test_backups_sorted_by_recency(self, dr_setup):
        db, engine, dr, tmp_path = dr_setup
        engine.create_full_backup()
        engine.create_full_backup()
        backups = dr._find_valid_backups()
        if len(backups) >= 2:
            assert backups[0].stat().st_mtime >= backups[1].stat().st_mtime

    def test_empty_backup_dir(self, tmp_path):
        db_path = tmp_path / "test.db"
        backup_dir = tmp_path / "empty_backups"
        backup_dir.mkdir()
        db = Database(db_path)
        dr = DisasterRecovery(db, backup_dir)
        assert dr._find_valid_backups() == []
