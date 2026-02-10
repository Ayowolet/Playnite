"""Tests for the backup engine."""

import json
import time
from pathlib import Path

import pytest

from gamelibrary.database import Database
from gamelibrary.backup.engine import BackupEngine


@pytest.fixture
def engine(tmp_path):
    """Create a BackupEngine with its own tmp_path DB, backup dir, and data dir."""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    backup_dir = tmp_path / "backups"
    data_dir = tmp_path / "data"
    return BackupEngine(db, backup_dir=backup_dir, data_dir=data_dir)


def _seed_data(engine: BackupEngine):
    """Put a small amount of data into the data_dir so backups have content."""
    config_file = engine.data_dir / "config.json"
    config_file.write_text(json.dumps({"theme": "dark", "language": "en"}))
    tags_dir = engine.data_dir / "tags"
    tags_dir.mkdir(parents=True, exist_ok=True)
    (tags_dir / "user_tags.json").write_text(json.dumps(["rpg", "fps"]))


class TestCreateFullBackup:
    def test_create_full_backup(self, engine):
        _seed_data(engine)
        record = engine.create_full_backup()

        assert record.id is not None
        assert record.backup_type == "full"
        assert record.status == "completed"
        assert record.checksum != ""
        assert Path(record.file_path).exists()

    def test_create_full_backup_with_components(self, engine):
        _seed_data(engine)
        record = engine.create_full_backup(components=["database", "config"])

        assert record.metadata["components"] == ["database", "config"]

    def test_create_full_backup_encrypted(self, engine):
        _seed_data(engine)
        record = engine.create_full_backup(password="s3cret!")

        assert record.is_encrypted is True
        assert record.file_path.endswith(".enc")
        assert Path(record.file_path).exists()


class TestCreateIncrementalBackup:
    def test_create_incremental_backup(self, engine):
        _seed_data(engine)
        full = engine.create_full_backup()

        # Modify data so incremental has something to pick up
        config_file = engine.data_dir / "config.json"
        config_file.write_text(json.dumps({"theme": "light", "language": "en"}))

        incr = engine.create_incremental_backup(parent_backup_id=full.id)

        assert incr.backup_type == "incremental"
        assert incr.parent_backup_id == full.id
        assert incr.status == "completed"
        assert Path(incr.file_path).exists()


class TestListBackups:
    def test_list_backups(self, engine):
        _seed_data(engine)
        engine.create_full_backup()
        # Tiny sleep so timestamps differ
        time.sleep(0.05)
        engine.create_full_backup()

        backups = engine.list_backups()
        assert len(backups) == 2


class TestDeleteBackup:
    def test_delete_backup(self, engine):
        _seed_data(engine)
        record = engine.create_full_backup()
        backup_path = Path(record.file_path)
        assert backup_path.exists()

        engine.delete_backup(record.id)

        assert not backup_path.exists()
        remaining = engine.list_backups()
        assert len(remaining) == 0


class TestBackupReport:
    def test_backup_report(self, engine):
        _seed_data(engine)
        record = engine.create_full_backup()
        report = engine.get_backup_report(record.id)

        assert report.backup_id == record.id
        assert report.backup_type == "full"
        assert report.file_path != ""
        assert report.created_at != ""
        assert report.is_verified is True


class TestCleanupOldBackups:
    def test_cleanup_old_backups(self, engine):
        _seed_data(engine)
        # Create several backups
        for _ in range(5):
            engine.create_full_backup()
            time.sleep(0.05)

        assert len(engine.list_backups()) == 5

        # Keep at most 2 backups
        engine.cleanup_old_backups(max_age_days=9999, max_count=2)

        remaining = engine.list_backups()
        assert len(remaining) <= 2
