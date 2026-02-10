"""Tests for the backup restore engine."""

import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from gamelibrary.database import Database
from gamelibrary.backup.engine import BackupEngine
from gamelibrary.backup.restore import RestoreEngine


@pytest.fixture
def setup(tmp_path):
    """Return a dict with db, engine, restore engine, and key paths."""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    backup_dir = tmp_path / "backups"
    data_dir = tmp_path / "data"
    engine = BackupEngine(db, backup_dir=backup_dir, data_dir=data_dir)
    restore = RestoreEngine(db, data_dir=data_dir)
    return {
        "db": db,
        "engine": engine,
        "restore": restore,
        "data_dir": data_dir,
        "backup_dir": backup_dir,
    }


def _seed_dirs(data_dir: Path, value="original"):
    """Seed directory-based components that round-trip correctly through backup/restore.

    The backup engine stores directory-component files as ``<component>/<relative>``,
    and the restore engine writes them back to ``data_dir/<component>/<relative>``.
    Using actual directories (not standalone ``*.json`` files) ensures the paths
    match after a round-trip.
    """
    tags_dir = data_dir / "tags"
    tags_dir.mkdir(parents=True, exist_ok=True)
    (tags_dir / "user_tags.json").write_text(json.dumps({"label": value}))

    cats_dir = data_dir / "categories"
    cats_dir.mkdir(parents=True, exist_ok=True)
    (cats_dir / "cats.json").write_text(json.dumps({"cat": value}))


class TestRestoreFull:
    def test_restore_full(self, setup):
        data_dir = setup["data_dir"]
        engine = setup["engine"]
        restore = setup["restore"]

        # Seed data and back it up
        _seed_dirs(data_dir, "original")
        record = engine.create_full_backup()

        # Modify data after backup
        _seed_dirs(data_dir, "modified")
        tags_file = data_dir / "tags" / "user_tags.json"
        assert json.loads(tags_file.read_text())["label"] == "modified"

        # Restore
        result = restore.restore_full(record.file_path)

        assert result["items_restored"] > 0
        assert len(result["components_restored"]) > 0
        # Tags should be back to the original value
        restored = json.loads(tags_file.read_text())
        assert restored["label"] == "original"


class TestRestoreSelective:
    def test_restore_selective(self, setup):
        data_dir = setup["data_dir"]
        engine = setup["engine"]
        restore = setup["restore"]

        _seed_dirs(data_dir, "original")
        record = engine.create_full_backup()

        # Modify both tags and categories
        _seed_dirs(data_dir, "modified")

        # Restore only tags
        result = restore.restore_selective(record.file_path, components=["tags"])

        assert "tags" in result["components_restored"]
        restored_tags = json.loads((data_dir / "tags" / "user_tags.json").read_text())
        assert restored_tags["label"] == "original"
        # Categories should still be modified
        cats = json.loads((data_dir / "categories" / "cats.json").read_text())
        assert cats["cat"] == "modified"


class TestRestoreEncrypted:
    def test_restore_encrypted(self, setup):
        data_dir = setup["data_dir"]
        engine = setup["engine"]
        restore = setup["restore"]

        _seed_dirs(data_dir, "original")
        record = engine.create_full_backup(password="mypass")
        assert record.is_encrypted

        # Modify
        _seed_dirs(data_dir, "modified")

        # Restore with correct password
        result = restore.restore_full(record.file_path, password="mypass")
        assert result["items_restored"] > 0
        restored_tags = json.loads((data_dir / "tags" / "user_tags.json").read_text())
        assert restored_tags["label"] == "original"

    def test_restore_wrong_password_fails(self, setup):
        data_dir = setup["data_dir"]
        engine = setup["engine"]
        restore = setup["restore"]

        _seed_dirs(data_dir, "original")
        record = engine.create_full_backup(password="correctpass")

        with pytest.raises((InvalidTag, ValueError)):
            restore.restore_full(record.file_path, password="wrongpass")


class TestListBackupContents:
    def test_list_backup_contents(self, setup):
        data_dir = setup["data_dir"]
        engine = setup["engine"]
        restore = setup["restore"]

        _seed_dirs(data_dir, "v1")
        record = engine.create_full_backup()

        contents = restore.list_backup_contents(record.file_path)

        assert contents["backup_type"] == "full"
        assert "components" in contents
        assert contents["total_files"] > 0
