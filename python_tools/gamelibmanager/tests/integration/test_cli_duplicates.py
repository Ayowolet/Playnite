"""Integration tests for duplicate CLI commands."""

import json
from datetime import datetime

import pytest
from click.testing import CliRunner

from gamelibmanager.cli.main import cli
from gamelibmanager.db.database import GameDatabase
from tests.factories import (
    make_game, make_lookup_tables, make_witcher_steam, make_witcher_gog,
    STEAM_SOURCE_ID,
)


class TestCLIDuplicates:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.db_path = str(tmp_path / "test.db")
        db = GameDatabase(self.db_path)
        db.open()
        make_lookup_tables(db)
        # Add some duplicates
        db.add_games_batch([
            make_witcher_steam(),
            make_witcher_gog(),
            make_game(name="Unique Game"),
        ])
        db.close()
        self.runner = CliRunner()

    def test_scan_text_output(self):
        result = self.runner.invoke(cli, ["--db", self.db_path, "duplicates", "scan",
                                          "--threshold", "0.70"])
        assert result.exit_code == 0
        assert "Duplicate Detection Report" in result.output

    def test_scan_json_output(self):
        result = self.runner.invoke(cli, ["--db", self.db_path, "--format", "json",
                                          "duplicates", "scan", "--threshold", "0.70"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total_groups" in data
        assert "groups" in data

    def test_report_to_file(self, tmp_path):
        output_file = str(tmp_path / "report.json")
        result = self.runner.invoke(cli, ["--db", self.db_path, "--format", "json",
                                          "duplicates", "report", "-o", output_file])
        assert result.exit_code == 0
        with open(output_file) as f:
            data = json.loads(f.read())
        assert "total_groups" in data

    def test_resolve_dry_run(self):
        result = self.runner.invoke(cli, ["--db", self.db_path, "--format", "json",
                                          "duplicates", "resolve", "--action", "hide",
                                          "--all", "--dry-run"])
        assert result.exit_code == 0

    def test_history_empty(self, tmp_path):
        db_path = str(tmp_path / "empty.db")
        db = GameDatabase(db_path)
        db.open()
        db.close()
        result = self.runner.invoke(cli, ["--db", db_path, "duplicates", "history"])
        assert result.exit_code == 0

    def test_undo_empty(self, tmp_path):
        db_path = str(tmp_path / "empty.db")
        db = GameDatabase(db_path)
        db.open()
        db.close()
        result = self.runner.invoke(cli, ["--db", db_path, "duplicates", "undo"])
        assert result.exit_code == 0
        assert "Nothing to undo" in result.output

    def test_scan_with_threshold(self):
        result = self.runner.invoke(cli, ["--db", self.db_path, "duplicates", "scan",
                                          "--threshold", "0.99"])
        assert result.exit_code == 0

    def test_scan_exclude_hidden(self):
        result = self.runner.invoke(cli, ["--db", self.db_path, "duplicates", "scan",
                                          "--exclude-hidden"])
        assert result.exit_code == 0

    def test_missing_db_error(self):
        result = self.runner.invoke(cli, ["duplicates", "scan"])
        assert result.exit_code != 0

    def test_resolve_hide_actual(self):
        result = self.runner.invoke(cli, ["--db", self.db_path, "duplicates", "resolve",
                                          "--action", "hide", "--all"])
        assert result.exit_code == 0
        assert result.output  # some output produced
        with GameDatabase(self.db_path) as db:
            games = db.get_all_games()
            assert any(g.hidden for g in games)

    def test_resolve_delete_actual(self):
        result = self.runner.invoke(cli, ["--db", self.db_path, "duplicates", "resolve",
                                          "--action", "delete", "--all"])
        assert result.exit_code == 0
        with GameDatabase(self.db_path) as db:
            assert db.game_count() < 3

    def test_resolve_merge_actual(self):
        result = self.runner.invoke(cli, ["--db", self.db_path, "duplicates", "resolve",
                                          "--action", "merge", "--all"])
        assert result.exit_code == 0
        with GameDatabase(self.db_path) as db:
            assert db.game_count() < 3

    def test_resolve_specific_group(self):
        result = self.runner.invoke(cli, ["--db", self.db_path, "duplicates", "resolve",
                                          "--group-id", "0", "--action", "hide"])
        assert result.exit_code == 0

    def test_override_not_duplicate(self):
        with GameDatabase(self.db_path) as db:
            games = db.get_all_games()
            game_uuid = str(games[0].id)
        result = self.runner.invoke(cli, ["--db", self.db_path, "duplicates", "override",
                                          game_uuid, "--not-duplicate"])
        assert result.exit_code == 0
        assert "not a duplicate" in result.output

    def test_override_set_master(self):
        with GameDatabase(self.db_path) as db:
            games = db.get_all_games()
            game_uuid = str(games[0].id)
        result = self.runner.invoke(cli, ["--db", self.db_path, "duplicates", "override",
                                          game_uuid, "--set-master"])
        assert result.exit_code == 0

    def test_history_with_records_text(self):
        # First, resolve to create history records
        self.runner.invoke(cli, ["--db", self.db_path, "duplicates", "resolve",
                                 "--action", "hide", "--all"])
        result = self.runner.invoke(cli, ["--db", self.db_path, "duplicates", "history"])
        assert result.exit_code == 0
        assert "No resolution history" not in result.output

    def test_history_with_records_json(self):
        # First, resolve to create history records
        self.runner.invoke(cli, ["--db", self.db_path, "duplicates", "resolve",
                                 "--action", "hide", "--all"])
        result = self.runner.invoke(cli, ["--db", self.db_path, "--format", "json",
                                          "duplicates", "history"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_report_text_stdout(self):
        result = self.runner.invoke(cli, ["--db", self.db_path, "duplicates", "report"])
        assert result.exit_code == 0
        assert "Duplicate Detection Report" in result.output
