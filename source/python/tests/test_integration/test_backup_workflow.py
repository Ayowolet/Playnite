"""Integration test: full backup/restore workflow via CLI runner."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from gamelibrary.cli import main


@pytest.fixture
def cli(tmp_path):
    runner = CliRunner()
    db_path = str(tmp_path / "test.db")
    backup_dir = str(tmp_path / "backups")
    data_dir = str(tmp_path / "data")
    Path(data_dir).mkdir(parents=True, exist_ok=True)

    def invoke(*args):
        full_args = list(args)
        return runner.invoke(main, full_args, catch_exceptions=False)

    return invoke, db_path, backup_dir, data_dir


class TestFullBackupRestoreWorkflow:
    def test_full_backup_restore_workflow(self, cli, tmp_path):
        invoke, db_path, backup_dir, data_dir = cli

        # -----------------------------------------------------------------
        # 0. Seed some achievement data so the database is non-trivial
        # -----------------------------------------------------------------
        result = invoke(
            "achievements", "--db", db_path, "--json",
            "register-platform", "TestPlat", "manual",
        )
        assert result.exit_code == 0, result.output

        result = invoke(
            "achievements", "--db", db_path, "--json",
            "add-game", "Test Game", "--platform", "TestPlat",
        )
        assert result.exit_code == 0, result.output
        game_id = json.loads(result.output)["game_id"]

        result = invoke(
            "achievements", "--db", db_path, "--json",
            "add-achievement", str(game_id), "First Blood",
            "--unlocked", "--global-pct", "70.0",
            "--unlock-time", "2025-01-01T00:00:00",
        )
        assert result.exit_code == 0, result.output

        # Put a directory-based component in data_dir so it round-trips
        # through backup/restore correctly.
        tags_dir = Path(data_dir) / "tags"
        tags_dir.mkdir(parents=True, exist_ok=True)
        tags_file = tags_dir / "user_tags.json"
        tags_file.write_text(json.dumps({"label": "original"}))

        # -----------------------------------------------------------------
        # 1. Create a backup profile
        # -----------------------------------------------------------------
        result = invoke(
            "backup", "--db", db_path, "--backup-dir", backup_dir,
            "--data-dir", data_dir, "--json",
            "profile", "create", "nightly",
            "--description", "Nightly backup",
            "--retention-days", "7",
            "--max-backups", "5",
        )
        assert result.exit_code == 0, result.output
        profile = json.loads(result.output)
        assert profile["name"] == "nightly"

        # -----------------------------------------------------------------
        # 2. Create a full backup
        # -----------------------------------------------------------------
        result = invoke(
            "backup", "--db", db_path, "--backup-dir", backup_dir,
            "--data-dir", data_dir, "--json",
            "create",
        )
        assert result.exit_code == 0, result.output
        full_backup = json.loads(result.output)
        full_backup_id = full_backup["id"]
        full_backup_path = full_backup["file_path"]
        assert Path(full_backup_path).exists()

        # -----------------------------------------------------------------
        # 3. Modify data after the full backup
        # -----------------------------------------------------------------
        tags_file.write_text(json.dumps({"label": "modified"}))

        result = invoke(
            "achievements", "--db", db_path, "--json",
            "add-achievement", str(game_id), "Second Wind",
            "--unlocked", "--global-pct", "30.0",
            "--unlock-time", "2025-02-01T00:00:00",
        )
        assert result.exit_code == 0, result.output

        # -----------------------------------------------------------------
        # 4. Create an incremental backup
        # -----------------------------------------------------------------
        result = invoke(
            "backup", "--db", db_path, "--backup-dir", backup_dir,
            "--data-dir", data_dir, "--json",
            "create-incremental", str(full_backup_id),
        )
        assert result.exit_code == 0, result.output
        incr_backup = json.loads(result.output)
        assert incr_backup["backup_type"] == "incremental"
        assert incr_backup["parent_backup_id"] == full_backup_id

        # -----------------------------------------------------------------
        # 5. List backups - should have 2
        # -----------------------------------------------------------------
        result = invoke(
            "backup", "--db", db_path, "--backup-dir", backup_dir,
            "--data-dir", data_dir, "--json",
            "list",
        )
        assert result.exit_code == 0, result.output
        backup_list = json.loads(result.output)
        assert len(backup_list) == 2

        # -----------------------------------------------------------------
        # 6. Verify the full backup
        # -----------------------------------------------------------------
        result = invoke(
            "backup", "--db", db_path, "--backup-dir", backup_dir,
            "--data-dir", data_dir, "--json",
            "verify", full_backup_path,
        )
        assert result.exit_code == 0, result.output
        verification = json.loads(result.output)
        assert verification["valid"] is True

        # -----------------------------------------------------------------
        # 7. View backup contents
        # -----------------------------------------------------------------
        result = invoke(
            "backup", "--db", db_path, "--backup-dir", backup_dir,
            "--data-dir", data_dir, "--json",
            "contents", full_backup_path,
        )
        assert result.exit_code == 0, result.output
        contents = json.loads(result.output)
        assert contents["backup_type"] == "full"
        assert contents["total_files"] > 0

        # -----------------------------------------------------------------
        # 8. Restore from the full backup to bring tags back to original
        # -----------------------------------------------------------------
        result = invoke(
            "backup", "--db", db_path, "--backup-dir", backup_dir,
            "--data-dir", data_dir, "--json",
            "restore", full_backup_path, "--components", "tags",
        )
        assert result.exit_code == 0, result.output
        restore_result = json.loads(result.output)
        assert "tags" in restore_result["components_restored"]

        # Verify the tags file is back to original
        restored_tags = json.loads(tags_file.read_text())
        assert restored_tags["label"] == "original"

        # -----------------------------------------------------------------
        # 9. Get a backup report
        # -----------------------------------------------------------------
        result = invoke(
            "backup", "--db", db_path, "--backup-dir", backup_dir,
            "--data-dir", data_dir, "--json",
            "report", str(full_backup_id),
        )
        assert result.exit_code == 0, result.output
        report = json.loads(result.output)
        assert report["backup_id"] == full_backup_id
        assert report["is_verified"] is True
