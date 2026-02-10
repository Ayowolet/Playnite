"""Unit tests for the main CLI entry point (cli/main.py)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from playnite.cli.main import cli, config_group, disaster_recovery_cmd, init_db_cmd


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def ctx(tmp_db, tmp_config):
    return {"config": tmp_config, "db": tmp_db}


# ---------------------------------------------------------------------------
# Top-level CLI
# ---------------------------------------------------------------------------


class TestTopLevelCLI:
    def test_help(self, runner):
        r = runner.invoke(cli, ["--help"])
        assert r.exit_code == 0

    def test_version(self, runner, tmp_config, tmp_db):
        # Patch Config.load so the CLI does not hit the real filesystem
        with patch("playnite.cli.main.Config.load", return_value=tmp_config):
            with patch("playnite.cli.main.DatabaseManager") as mock_db_cls:
                mock_db_cls.return_value = tmp_db
                r = runner.invoke(cli, ["--version"])
        assert r.exit_code == 0

    def test_verbose_flag_help(self, runner):
        r = runner.invoke(cli, ["--verbose", "--help"])
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# config show
# ---------------------------------------------------------------------------


class TestConfigShowCommand:
    def test_config_show_json(self, runner, ctx):
        r = runner.invoke(
            config_group, ["show", "--json"], obj=ctx, catch_exceptions=False
        )
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert "steam" in data
        assert "backup" in data

    def test_config_show_redacts_api_key(self, runner, ctx):
        """API keys must not appear in plaintext in config show output."""
        ctx["config"].steam.api_key = "SUPERSECRETKEY12345"
        r = runner.invoke(
            config_group, ["show", "--json"], obj=ctx, catch_exceptions=False
        )
        assert r.exit_code == 0
        data = json.loads(r.output)
        # Key should be redacted — original value must not appear
        assert data["steam"]["api_key"] != "SUPERSECRETKEY12345"

    def test_config_show_plain(self, runner, ctx):
        r = runner.invoke(config_group, ["show"], obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0

    def test_config_show_empty_api_key_redaction(self, runner, ctx):
        """An empty api_key should not cause an error during redaction."""
        ctx["config"].steam.api_key = ""
        r = runner.invoke(
            config_group, ["show", "--json"], obj=ctx, catch_exceptions=False
        )
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["steam"]["api_key"] == ""


# ---------------------------------------------------------------------------
# config set
# ---------------------------------------------------------------------------


class TestConfigSetCommand:
    def test_config_set_string_value(self, runner, ctx):
        r = runner.invoke(
            config_group,
            ["set", "steam.steam_id", "12345678"],
            obj=ctx,
            catch_exceptions=False,
        )
        assert r.exit_code == 0
        assert ctx["config"].steam.steam_id == "12345678"

    def test_config_set_bool_value_true(self, runner, ctx):
        # First set enabled to False so we know the change takes effect
        ctx["config"].steam.enabled = False
        r = runner.invoke(
            config_group,
            ["set", "steam.enabled", "true"],
            obj=ctx,
            catch_exceptions=False,
        )
        assert r.exit_code == 0
        assert ctx["config"].steam.enabled is True

    def test_config_set_bool_value_false(self, runner, ctx):
        ctx["config"].steam.enabled = True
        r = runner.invoke(
            config_group,
            ["set", "steam.enabled", "false"],
            obj=ctx,
            catch_exceptions=False,
        )
        assert r.exit_code == 0
        assert ctx["config"].steam.enabled is False

    def test_config_set_int_value(self, runner, ctx):
        r = runner.invoke(
            config_group,
            ["set", "backup.max_backups", "5"],
            obj=ctx,
            catch_exceptions=False,
        )
        assert r.exit_code == 0
        assert ctx["config"].backup.max_backups == 5

    def test_config_set_float_value(self, runner, ctx):
        r = runner.invoke(
            config_group,
            ["set", "achievements.rare_threshold", "5.0"],
            obj=ctx,
            catch_exceptions=False,
        )
        assert r.exit_code == 0
        assert ctx["config"].achievements.rare_threshold == 5.0

    def test_config_set_top_level_key(self, runner, ctx, tmp_path):
        new_data_dir = str(tmp_path / "new_data_dir")
        r = runner.invoke(
            config_group,
            ["set", "data_dir", new_data_dir],
            obj=ctx,
            catch_exceptions=False,
        )
        assert r.exit_code == 0

    def test_config_set_unknown_section_exits_nonzero(self, runner, ctx):
        r = runner.invoke(
            config_group,
            ["set", "nonexistent.field", "value"],
            obj=ctx,
        )
        assert r.exit_code != 0


# ---------------------------------------------------------------------------
# init-db
# ---------------------------------------------------------------------------


class TestInitDbCommand:
    def test_init_db(self, runner, ctx):
        r = runner.invoke(init_db_cmd, [], obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0

    def test_init_db_idempotent(self, runner, ctx):
        """Running init-db twice should not raise."""
        r1 = runner.invoke(init_db_cmd, [], obj=ctx, catch_exceptions=False)
        r2 = runner.invoke(init_db_cmd, [], obj=ctx, catch_exceptions=False)
        assert r1.exit_code == 0
        assert r2.exit_code == 0


# ---------------------------------------------------------------------------
# disaster-recovery
# ---------------------------------------------------------------------------


class TestDisasterRecoveryCommand:
    def test_disaster_recovery_plain(self, runner, ctx, tmp_path, tmp_config, tmp_db):
        """Create a real backup archive and recover from it."""
        from playnite.backup.manager import BackupManager

        mgr = BackupManager(tmp_config, tmp_db)
        dest = tmp_path / "backups"
        result = mgr.create_full_backup(destination=str(dest))
        assert result.success

        restore_dest = tmp_path / "recovered"
        r = runner.invoke(
            disaster_recovery_cmd,
            [result.backup_path, "--destination", str(restore_dest)],
            obj=ctx,
            catch_exceptions=False,
        )
        assert r.exit_code == 0
        # Output should indicate success
        assert "complete" in r.output.lower() or "restored" in r.output.lower()

    def test_disaster_recovery_json(self, runner, ctx, tmp_path, tmp_config, tmp_db):
        """JSON output from disaster-recovery includes success and items_restored."""
        from playnite.backup.manager import BackupManager

        mgr = BackupManager(tmp_config, tmp_db)
        dest = tmp_path / "backups2"
        result = mgr.create_full_backup(destination=str(dest))
        assert result.success

        restore_dest = tmp_path / "recovered2"
        r = runner.invoke(
            disaster_recovery_cmd,
            [
                result.backup_path,
                "--destination",
                str(restore_dest),
                "--json",
            ],
            obj=ctx,
            catch_exceptions=False,
        )
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["success"] is True
        assert data["items_restored"] >= 0
        assert "destination" in data

    def test_disaster_recovery_no_destination_uses_config_data_dir(
        self, runner, ctx, tmp_path, tmp_config, tmp_db
    ):
        """When no --destination is given, data_dir from config is used."""
        from playnite.backup.manager import BackupManager

        mgr = BackupManager(tmp_config, tmp_db)
        dest = tmp_path / "backups3"
        result = mgr.create_full_backup(destination=str(dest))
        assert result.success

        r = runner.invoke(
            disaster_recovery_cmd,
            [result.backup_path, "--json"],
            obj=ctx,
            catch_exceptions=False,
        )
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["success"] is True
