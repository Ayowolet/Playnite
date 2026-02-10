"""Tests for backup verification."""

import json
import zipfile

import pytest

from gamelibrary.database import Database
from gamelibrary.backup.engine import BackupEngine
from gamelibrary.backup.verification import verify_backup


@pytest.fixture
def engine(tmp_path):
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    backup_dir = tmp_path / "backups"
    data_dir = tmp_path / "data"
    return BackupEngine(db, backup_dir=backup_dir, data_dir=data_dir)


def _seed_data(engine: BackupEngine):
    config_file = engine.data_dir / "config.json"
    config_file.write_text(json.dumps({"setting": "value"}))


class TestVerifyValidBackup:
    def test_verify_valid_backup(self, engine):
        _seed_data(engine)
        record = engine.create_full_backup()

        result = verify_backup(record.file_path)

        assert result["valid"] is True
        assert result["errors"] == []


class TestVerifyNonexistentFile:
    def test_verify_nonexistent_file(self, tmp_path):
        result = verify_backup(tmp_path / "no_such_file.zip")

        assert result["valid"] is False
        assert any("does not exist" in e for e in result["errors"])


class TestVerifyNotAZip:
    def test_verify_not_a_zip(self, tmp_path):
        bad_file = tmp_path / "not_a_zip.zip"
        bad_file.write_text("this is not a zip")

        result = verify_backup(bad_file)

        assert result["valid"] is False
        assert any("not a valid ZIP" in e for e in result["errors"])


class TestVerifyCorruptChecksum:
    def test_verify_corrupt_checksum(self, tmp_path):
        """Create a zip with a manifest whose checksum deliberately mismatches."""
        zip_path = tmp_path / "corrupt.zip"
        file_content = b"real file content"

        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("database/test.db", file_content)
            manifest = {
                "backup_type": "full",
                "components": ["database"],
                "items": [
                    {
                        "path": "database/test.db",
                        "type": "database",
                        "size": len(file_content),
                        "checksum": "0000000000000000000000000000000000000000000000000000000000000000",
                    }
                ],
            }
            zf.writestr("manifest.json", json.dumps(manifest))

        result = verify_backup(zip_path)

        assert result["valid"] is False
        assert any("Checksum mismatch" in e for e in result["errors"])
