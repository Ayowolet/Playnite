"""Unit tests for the backup CLI commands (cli/backup_cli.py)."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from playnite.cli.backup_cli import backup_group


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def ctx(tmp_db, tmp_config):
    return {"config": tmp_config, "db": tmp_db}


def _create_backup(runner, ctx, tmp_path, **extra_args):
    """Helper: create a backup via CLI and return its job_id."""
    dest = tmp_path / "bk"
    args = ["create", "--destination", str(dest), "--json"] + list(extra_args.get("extra", []))
    r = runner.invoke(backup_group, args, obj=ctx, catch_exceptions=False)
    assert r.exit_code == 0
    return json.loads(r.output)["job_id"]


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreateCommand:
    def test_create_full_backup_json(self, runner, ctx, tmp_path):
        dest = tmp_path / "bk"
        r = runner.invoke(backup_group, ["create", "--destination", str(dest), "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["success"] is True
        assert data["job_id"] > 0

    def test_create_with_label_json(self, runner, ctx, tmp_path):
        dest = tmp_path / "bk"
        r = runner.invoke(backup_group,
                          ["create", "--destination", str(dest), "--label", "pre-test", "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert json.loads(r.output)["success"] is True

    def test_create_encrypted_json(self, runner, ctx, tmp_path):
        dest = tmp_path / "bk_enc"
        r = runner.invoke(backup_group,
                          ["create", "--destination", str(dest),
                           "--encrypted", "--password", "p@ss!", "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["encrypted"] is True

    def test_create_incremental_auto_parent(self, runner, ctx, tmp_path):
        dest = tmp_path / "bk"
        # Need a full backup first so incremental can auto-select parent.
        # Auto-parent prints a status line before the JSON, so use plain output.
        runner.invoke(backup_group, ["create", "--destination", str(dest)],
                      obj=ctx, catch_exceptions=False)
        r = runner.invoke(backup_group,
                          ["create", "--destination", str(dest), "--incremental"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert "Backup created" in r.output

    def test_create_incremental_explicit_parent(self, runner, ctx, tmp_path):
        dest = tmp_path / "bk"
        parent_id = _create_backup(runner, ctx, tmp_path)
        r = runner.invoke(backup_group,
                          ["create", "--destination", str(dest),
                           "--incremental", "--parent-id", str(parent_id), "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert json.loads(r.output)["success"] is True

    def test_create_incremental_no_backups_fails(self, runner, ctx, tmp_path):
        dest = tmp_path / "bk"
        r = runner.invoke(backup_group,
                          ["create", "--destination", str(dest), "--incremental"],
                          obj=ctx)
        assert r.exit_code != 0

    def test_create_with_categories(self, runner, ctx, tmp_path):
        dest = tmp_path / "bk"
        r = runner.invoke(backup_group,
                          ["create", "--destination", str(dest),
                           "--categories", "config", "--categories", "themes", "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0

    def test_create_plain_output(self, runner, ctx, tmp_path):
        dest = tmp_path / "bk"
        r = runner.invoke(backup_group, ["create", "--destination", str(dest)],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert "Backup created" in r.output


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


class TestListCommand:
    def test_list_empty_json(self, runner, ctx):
        r = runner.invoke(backup_group, ["list", "--json"], obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert json.loads(r.output) == []

    def test_list_empty_plain(self, runner, ctx):
        r = runner.invoke(backup_group, ["list"], obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert "No backups" in r.output

    def test_list_with_backup_json(self, runner, ctx, tmp_path):
        _create_backup(runner, ctx, tmp_path)
        r = runner.invoke(backup_group, ["list", "--json"], obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert len(data) >= 1

    def test_list_with_backup_plain(self, runner, ctx, tmp_path):
        _create_backup(runner, ctx, tmp_path)
        r = runner.invoke(backup_group, ["list"], obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------


class TestRestoreCommand:
    def test_restore_json(self, runner, ctx, tmp_path):
        job_id = _create_backup(runner, ctx, tmp_path)
        restore_dest = tmp_path / "restore"
        r = runner.invoke(backup_group,
                          ["restore", str(job_id), "--destination", str(restore_dest), "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["success"] is True

    def test_restore_plain(self, runner, ctx, tmp_path):
        job_id = _create_backup(runner, ctx, tmp_path)
        restore_dest = tmp_path / "restore2"
        r = runner.invoke(backup_group,
                          ["restore", str(job_id), "--destination", str(restore_dest)],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert "Restore completed" in r.output

    def test_restore_selective_categories(self, runner, ctx, tmp_path):
        job_id = _create_backup(runner, ctx, tmp_path)
        restore_dest = tmp_path / "restore3"
        r = runner.invoke(backup_group,
                          ["restore", str(job_id), "--destination", str(restore_dest),
                           "--categories", "config", "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


class TestVerifyCommand:
    def test_verify_valid_backup_json(self, runner, ctx, tmp_path):
        job_id = _create_backup(runner, ctx, tmp_path)
        r = runner.invoke(backup_group, ["verify", str(job_id), "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert "passed" in data

    def test_verify_valid_backup_plain(self, runner, ctx, tmp_path):
        job_id = _create_backup(runner, ctx, tmp_path)
        r = runner.invoke(backup_group, ["verify", str(job_id)],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert "PASSED" in r.output or "passed" in r.output.lower()


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDeleteCommand:
    def test_delete_json(self, runner, ctx, tmp_path):
        job_id = _create_backup(runner, ctx, tmp_path)
        r = runner.invoke(backup_group, ["delete", str(job_id), "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert json.loads(r.output)["deleted"] is True

    def test_delete_plain(self, runner, ctx, tmp_path):
        job_id = _create_backup(runner, ctx, tmp_path)
        r = runner.invoke(backup_group, ["delete", str(job_id)],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert "deleted" in r.output.lower()

    def test_delete_not_found(self, runner, ctx):
        # JSON path returns {"deleted": false}, non-JSON path calls sys.exit(1)
        r = runner.invoke(backup_group, ["delete", "99999", "--json"], obj=ctx,
                          catch_exceptions=False)
        assert r.exit_code == 0
        assert json.loads(r.output)["deleted"] is False

    def test_delete_keep_file(self, runner, ctx, tmp_path):
        job_id = _create_backup(runner, ctx, tmp_path)
        r = runner.invoke(backup_group, ["delete", str(job_id), "--keep-file", "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


class TestReportCommand:
    def test_report_json(self, runner, ctx, tmp_path):
        job_id = _create_backup(runner, ctx, tmp_path)
        r = runner.invoke(backup_group, ["report", str(job_id), "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["id"] == job_id

    def test_report_plain(self, runner, ctx, tmp_path):
        job_id = _create_backup(runner, ctx, tmp_path)
        r = runner.invoke(backup_group, ["report", str(job_id)],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert "Backup Report" in r.output

    def test_report_not_found(self, runner, ctx):
        r = runner.invoke(backup_group, ["report", "99999"], obj=ctx, catch_exceptions=False)
        assert r.exit_code != 0


# ---------------------------------------------------------------------------
# export / import
# ---------------------------------------------------------------------------


class TestExportImportCommands:
    def test_export_json(self, runner, ctx, tmp_path):
        out = tmp_path / "lib.json"
        r = runner.invoke(backup_group, ["export", str(out), "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert "checksum" in data

    def test_export_plain(self, runner, ctx, tmp_path):
        out = tmp_path / "lib2.json"
        r = runner.invoke(backup_group, ["export", str(out)],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert "exported" in r.output.lower()

    def test_import_json(self, runner, ctx, tmp_path):
        out = tmp_path / "lib.json"
        runner.invoke(backup_group, ["export", str(out), "--json"],
                      obj=ctx, catch_exceptions=False)
        r = runner.invoke(backup_group, ["import", str(out), "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert "imported" in data

    def test_import_plain(self, runner, ctx, tmp_path):
        out = tmp_path / "lib3.json"
        runner.invoke(backup_group, ["export", str(out)], obj=ctx, catch_exceptions=False)
        r = runner.invoke(backup_group, ["import", str(out)], obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert "Imported" in r.output


# ---------------------------------------------------------------------------
# profile sub-commands
# ---------------------------------------------------------------------------


class TestProfileCommands:
    def test_profile_create_json(self, runner, ctx, tmp_path):
        r = runner.invoke(backup_group,
                          ["profile", "create", "--name", "daily",
                           "--destination", str(tmp_path / "d1"), "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert "id" in data

    def test_profile_create_with_cron(self, runner, ctx):
        r = runner.invoke(backup_group,
                          ["profile", "create", "--name", "nightly", "--cron", "0 2 * * *"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0

    def test_profile_create_encrypted(self, runner, ctx):
        r = runner.invoke(backup_group,
                          ["profile", "create", "--name", "secure", "--encrypt", "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0

    def test_profile_list_empty_json(self, runner, ctx):
        r = runner.invoke(backup_group, ["profile", "list", "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert json.loads(r.output) == []

    def test_profile_list_empty_plain(self, runner, ctx):
        r = runner.invoke(backup_group, ["profile", "list"], obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert "No profiles" in r.output

    def test_profile_list_with_entries(self, runner, ctx):
        runner.invoke(backup_group,
                      ["profile", "create", "--name", "test_profile", "--json"],
                      obj=ctx, catch_exceptions=False)
        r = runner.invoke(backup_group, ["profile", "list", "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert len(data) >= 1

    def test_profile_list_plain_with_entries(self, runner, ctx, tmp_path):
        runner.invoke(backup_group,
                      ["profile", "create", "--name", "show_me",
                       "--destination", str(tmp_path)],
                      obj=ctx, catch_exceptions=False)
        r = runner.invoke(backup_group, ["profile", "list"], obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0

    def test_profile_delete_json(self, runner, ctx):
        cr = runner.invoke(backup_group,
                           ["profile", "create", "--name", "to_delete", "--json"],
                           obj=ctx, catch_exceptions=False)
        pid = json.loads(cr.output)["id"]
        r = runner.invoke(backup_group, ["profile", "delete", str(pid), "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert json.loads(r.output)["deleted"] is True

    def test_profile_delete_plain(self, runner, ctx):
        cr = runner.invoke(backup_group,
                           ["profile", "create", "--name", "to_delete2", "--json"],
                           obj=ctx, catch_exceptions=False)
        pid = json.loads(cr.output)["id"]
        r = runner.invoke(backup_group, ["profile", "delete", str(pid)],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert "deleted" in r.output.lower()

    def test_profile_delete_not_found(self, runner, ctx):
        # JSON path returns {"deleted": false}, non-JSON path calls sys.exit(1)
        r = runner.invoke(backup_group, ["profile", "delete", "99999", "--json"],
                          obj=ctx, catch_exceptions=False)
        assert r.exit_code == 0
        assert json.loads(r.output)["deleted"] is False
