"""Integration tests for the complete backup and restore workflows."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from playnite.backup.manager import BackupManager
from playnite.backup.profiles import BackupProfileManager
from playnite.database.models import Achievement, Game, UserAchievement


def _write_test_files(config):
    """Write some test files to back up."""
    data_dir = Path(config.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Database
    db_file = Path(config.database_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    db_file.write_bytes(b"SQLite format 3\x00" + b"test_db_data" * 100)

    # Config
    (data_dir / "config.json").write_text('{"test": true}')

    # Themes
    themes_dir = data_dir / "themes"
    themes_dir.mkdir(exist_ok=True)
    (themes_dir / "default.css").write_text("body { color: black; }")

    # Plugins
    plugins_dir = data_dir / "plugins"
    plugins_dir.mkdir(exist_ok=True)
    (plugins_dir / "my_plugin.json").write_text('{"name": "my_plugin"}')

    # Controller mappings
    ctrl_dir = data_dir / "controller_mappings"
    ctrl_dir.mkdir(exist_ok=True)
    (ctrl_dir / "xbox.json").write_text('{"a": "jump"}')


# ---------------------------------------------------------------------------
# Full backup + restore
# ---------------------------------------------------------------------------


class TestFullBackupWorkflow:
    def test_create_full_backup(self, tmp_db, tmp_config, tmp_path):
        _write_test_files(tmp_config)
        mgr = BackupManager(tmp_config, tmp_db)
        result = mgr.create_full_backup(destination=str(tmp_path / "backups"))

        assert result.success
        assert result.job_id > 0
        assert Path(result.backup_path).exists()
        assert result.total_size > 0
        assert result.compressed_size > 0
        assert len(result.checksum) == 64

    def test_full_backup_listed(self, tmp_db, tmp_config, tmp_path):
        _write_test_files(tmp_config)
        mgr = BackupManager(tmp_config, tmp_db)
        result = mgr.create_full_backup(destination=str(tmp_path / "backups"))

        backups = mgr.list_backups()
        assert len(backups) == 1
        assert backups[0]["id"] == result.job_id
        assert backups[0]["type"] == "full"

    def test_restore_full_backup(self, tmp_db, tmp_config, tmp_path):
        _write_test_files(tmp_config)
        mgr = BackupManager(tmp_config, tmp_db)
        result = mgr.create_full_backup(destination=str(tmp_path / "backups"))

        restore_dest = tmp_path / "restored"
        restore_result = mgr.restore_backup(result.job_id, destination=str(restore_dest))

        assert restore_result.success
        assert restore_result.items_restored > 0
        assert (restore_dest / "database" / "playnite.db").exists()

    def test_selective_restore(self, tmp_db, tmp_config, tmp_path):
        _write_test_files(tmp_config)
        mgr = BackupManager(tmp_config, tmp_db)
        result = mgr.create_full_backup(destination=str(tmp_path / "backups"))

        restore_dest = tmp_path / "selective"
        restore_result = mgr.restore_backup(
            result.job_id,
            destination=str(restore_dest),
            categories={"themes"},
        )
        assert restore_result.success
        # Themes should be restored
        assert (restore_dest / "themes" / "default.css").exists()
        # Database should NOT be in the restore (selective)
        assert not (restore_dest / "database" / "playnite.db").exists()

    def test_backup_with_label(self, tmp_db, tmp_config, tmp_path):
        _write_test_files(tmp_config)
        mgr = BackupManager(tmp_config, tmp_db)
        result = mgr.create_full_backup(
            destination=str(tmp_path / "backups"), label="pre-update"
        )
        assert "pre-update" in Path(result.backup_path).name
        backups = mgr.list_backups()
        assert backups[0]["label"] == "pre-update"


# ---------------------------------------------------------------------------
# Incremental backup
# ---------------------------------------------------------------------------


class TestIncrementalBackupWorkflow:
    def test_incremental_after_full(self, tmp_db, tmp_config, tmp_path):
        _write_test_files(tmp_config)
        mgr = BackupManager(tmp_config, tmp_db)

        full = mgr.create_full_backup(destination=str(tmp_path / "backups"))
        incr = mgr.create_incremental_backup(
            parent_backup_id=full.job_id,
            destination=str(tmp_path / "backups"),
        )

        assert incr.success
        assert incr.backup_type == "incremental"
        assert incr.job_id > full.job_id

    def test_incremental_only_changed_files(self, tmp_db, tmp_config, tmp_path):
        _write_test_files(tmp_config)
        mgr = BackupManager(tmp_config, tmp_db)
        full = mgr.create_full_backup(destination=str(tmp_path / "backups"))

        # Modify one file
        Path(tmp_config.data_dir, "themes", "default.css").write_text("body { color: red; }")

        incr = mgr.create_incremental_backup(
            parent_backup_id=full.job_id,
            destination=str(tmp_path / "backups"),
        )
        assert incr.success
        # Incremental should be smaller than full
        assert incr.compressed_size <= full.compressed_size

    def test_restore_incremental(self, tmp_db, tmp_config, tmp_path):
        _write_test_files(tmp_config)
        mgr = BackupManager(tmp_config, tmp_db)

        full = mgr.create_full_backup(destination=str(tmp_path / "backups"))
        # Modify a file
        Path(tmp_config.data_dir, "themes", "default.css").write_text("/* updated */")
        incr = mgr.create_incremental_backup(
            parent_backup_id=full.job_id,
            destination=str(tmp_path / "backups"),
        )

        restore_dest = tmp_path / "restored_incr"
        result = mgr.restore_backup(incr.job_id, destination=str(restore_dest))
        assert result.success
        assert result.items_restored > 0


# ---------------------------------------------------------------------------
# Encrypted backup
# ---------------------------------------------------------------------------


class TestEncryptedBackupWorkflow:
    def test_encrypt_and_decrypt_roundtrip(self, tmp_db, tmp_config, tmp_path):
        _write_test_files(tmp_config)
        mgr = BackupManager(tmp_config, tmp_db)
        result = mgr.create_full_backup(
            destination=str(tmp_path / "backups"),
            password="my_secure_password",
        )

        assert result.success
        assert result.encrypted
        assert result.backup_path.endswith(".pnbe")

        # Restore with correct password
        restore_dest = tmp_path / "restored_enc"
        restore_result = mgr.restore_backup(
            result.job_id,
            destination=str(restore_dest),
            password="my_secure_password",
        )
        assert restore_result.success
        assert (restore_dest / "database" / "playnite.db").exists()

    def test_restore_wrong_password_fails(self, tmp_db, tmp_config, tmp_path):
        _write_test_files(tmp_config)
        mgr = BackupManager(tmp_config, tmp_db)
        result = mgr.create_full_backup(
            destination=str(tmp_path / "backups"),
            password="correct_password",
        )

        restore_result = mgr.restore_backup(
            result.job_id,
            destination=str(tmp_path / "bad_restore"),
            password="wrong_password",
        )
        assert not restore_result.success


# ---------------------------------------------------------------------------
# Retention policy
# ---------------------------------------------------------------------------


class TestRetentionPolicy:
    def test_retention_by_count(self, tmp_db, tmp_config, tmp_path):
        _write_test_files(tmp_config)
        mgr = BackupManager(tmp_config, tmp_db)
        dest = str(tmp_path / "backups")

        for _ in range(5):
            mgr.create_full_backup(destination=dest)

        assert len(mgr.list_backups()) == 5
        removed = mgr.apply_retention_policy(max_count=3)
        assert removed == 2
        assert len(mgr.list_backups()) == 3

    def test_retention_zero_removed_if_within_limit(self, tmp_db, tmp_config, tmp_path):
        _write_test_files(tmp_config)
        mgr = BackupManager(tmp_config, tmp_db)
        dest = str(tmp_path / "backups")

        for _ in range(2):
            mgr.create_full_backup(destination=dest)

        removed = mgr.apply_retention_policy(max_count=5)
        assert removed == 0


# ---------------------------------------------------------------------------
# Delete backup
# ---------------------------------------------------------------------------


class TestDeleteBackup:
    def test_delete_removes_record(self, tmp_db, tmp_config, tmp_path):
        _write_test_files(tmp_config)
        mgr = BackupManager(tmp_config, tmp_db)
        result = mgr.create_full_backup(destination=str(tmp_path / "backups"))
        assert len(mgr.list_backups()) == 1
        deleted = mgr.delete_backup(result.job_id)
        assert deleted
        assert len(mgr.list_backups()) == 0

    def test_delete_also_removes_file(self, tmp_db, tmp_config, tmp_path):
        _write_test_files(tmp_config)
        mgr = BackupManager(tmp_config, tmp_db)
        result = mgr.create_full_backup(destination=str(tmp_path / "backups"))
        archive = Path(result.backup_path)
        assert archive.exists()
        mgr.delete_backup(result.job_id, delete_file=True)
        assert not archive.exists()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class TestBackupReport:
    def test_report_contains_expected_fields(self, tmp_db, tmp_config, tmp_path):
        _write_test_files(tmp_config)
        mgr = BackupManager(tmp_config, tmp_db)
        result = mgr.create_full_backup(destination=str(tmp_path / "backups"))
        report = mgr.generate_report(result.job_id)

        assert report["id"] == result.job_id
        assert report["type"] == "full"
        assert "total_size" in report
        assert "compressed_size" in report
        assert "file_count" in report
        assert "categories" in report


# ---------------------------------------------------------------------------
# Library export / import
# ---------------------------------------------------------------------------


class TestLibraryExportImport:
    def _populate_achievements(self, db):
        with db.get_session() as session:
            game = Game(name="Export Test", platform="steam", platform_game_id="exp99")
            session.add(game)
            session.flush()
            ach = Achievement(
                game_id=game.id,
                achievement_id="EXP_ACH",
                name="Export Achievement",
                global_percentage=50.0,
            )
            session.add(ach)
            session.flush()
            session.add(UserAchievement(
                achievement_id=ach.id,
                platform_user_id="steam",
                is_unlocked=True,
            ))

    def test_export_library(self, tmp_db, tmp_config, tmp_path):
        self._populate_achievements(tmp_db)
        mgr = BackupManager(tmp_config, tmp_db)
        out = tmp_path / "library.json"
        checksum = mgr.export_library(out)
        assert out.exists()
        assert len(checksum) == 64
        data = json.loads(out.read_text())
        assert "achievements" in data

    def test_import_library(self, tmp_db, tmp_config, tmp_path):
        self._populate_achievements(tmp_db)
        mgr = BackupManager(tmp_config, tmp_db)

        # Export first
        out = tmp_path / "library.json"
        mgr.export_library(out)

        # Clear database and re-import
        tmp_db.drop_all()
        tmp_db.init_db()

        imported = mgr.import_library(out)
        assert imported >= 1


# ---------------------------------------------------------------------------
# Backup profiles
# ---------------------------------------------------------------------------


class TestBackupProfileWorkflow:
    def test_create_and_list_profile(self, tmp_db, tmp_config):
        pm = BackupProfileManager(tmp_db)
        profile_id = pm.create_profile(
            name="nightly",
            destinations=["/backups/nightly"],
            schedule_cron="0 1 * * *",
            encrypt=True,
            max_retention_days=14,
        )
        assert profile_id > 0
        profiles = pm.list_profiles()
        assert len(profiles) == 1
        p = profiles[0]
        assert p["name"] == "nightly"
        assert p["encrypt"] is True
        assert "/backups/nightly" in p["destinations"]

    def test_delete_profile(self, tmp_db, tmp_config):
        pm = BackupProfileManager(tmp_db)
        pid = pm.create_profile(name="temp")
        assert pm.delete_profile(pid) is True
        assert pm.list_profiles() == []

    def test_duplicate_profile_name_raises(self, tmp_db, tmp_config):
        from playnite.backup.profiles import ProfileError

        pm = BackupProfileManager(tmp_db)
        pm.create_profile(name="duplicate")
        with pytest.raises(ProfileError):
            pm.create_profile(name="duplicate")
