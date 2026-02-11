"""
Integration tests: complete library merge workflow via CLI.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from game_library.cli.main import cli
from game_library.storage.json_store import JsonStore
from tests.conftest import make_game, make_library


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def master_file(tmp_path):
    games = [
        make_game("The Witcher 3: Wild Hunt", year=2015, platforms=["PC"],
                  developers=["CD Projekt Red"], source="Steam", installed=True,
                  playtime=7200, cover="cover_steam.jpg",
                  description="Open world RPG."),
        make_game("Portal 2", year=2011, platforms=["PC"], developers=["Valve"],
                  source="Steam", installed=True, playtime=1800),
        make_game("Master Exclusive Game", year=2022, platforms=["PC"], source="Steam"),
    ]
    lib = make_library("master", games)
    path = tmp_path / "master.json"
    JsonStore(path).save(lib)
    return str(path)


@pytest.fixture
def source_file(tmp_path):
    games = [
        make_game("The Witcher 3: Wild Hunt", year=2015, platforms=["PC"],
                  developers=["CD Projekt Red"], source="GOG", playtime=3600,
                  cover="cover_gog.jpg"),
        make_game("Portal 2", year=2011, platforms=["PC"],
                  developers=["Valve Corporation"], source="GOG"),
        make_game("Source Exclusive Game", year=2023, platforms=["PC"], source="GOG"),
    ]
    lib = make_library("source", games)
    path = tmp_path / "source.json"
    JsonStore(path).save(lib)
    return str(path)


# ── preview ───────────────────────────────────────────────────────────────────

class TestPreviewCommand:
    def test_preview_json_output(self, runner, master_file, source_file):
        result = runner.invoke(cli, [
            "merge", "preview", master_file, source_file,
            "--threshold", "0.80",
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "new_games" in data
        assert "updated_games" in data
        assert data["new_games"] == 1  # Source Exclusive Game

    def test_preview_identifies_updates(self, runner, master_file, source_file):
        result = runner.invoke(cli, [
            "merge", "preview", master_file, source_file,
            "--threshold", "0.80",
            "--json-output",
        ])
        data = json.loads(result.output)
        assert data["updated_games"] >= 2  # Witcher 3 + Portal 2

    def test_preview_saves_file(self, runner, master_file, source_file, tmp_path):
        preview_path = str(tmp_path / "preview.json")
        runner.invoke(cli, [
            "merge", "preview", master_file, source_file,
            "--save-preview", preview_path,
        ])
        assert Path(preview_path).exists()

    def test_preview_doesnt_modify_master(self, runner, master_file, source_file):
        before = json.loads(Path(master_file).read_text())
        runner.invoke(cli, [
            "merge", "preview", master_file, source_file,
        ])
        after = json.loads(Path(master_file).read_text())
        assert before == after


# ── execute ───────────────────────────────────────────────────────────────────

class TestExecuteCommand:
    def test_execute_adds_source_exclusive_game(self, runner, master_file, source_file, tmp_path):
        out_path = str(tmp_path / "merged.json")
        result = runner.invoke(cli, [
            "merge", "execute", master_file, source_file,
            "--threshold", "0.80",
            "--output-path", out_path,
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["games_added"] == 1
        assert data["success"] is True

    def test_execute_backup_created(self, runner, master_file, source_file, tmp_path):
        backup_dir = str(tmp_path / "backups")
        result = runner.invoke(cli, [
            "merge", "execute", master_file, source_file,
            "--threshold", "0.80",
            "--backup-dir", backup_dir,
            "--json-output",
        ])
        data = json.loads(result.output)
        assert data["backup_id"] is not None
        # Backup directory should contain at least one file
        assert any(Path(backup_dir).iterdir())

    def test_execute_keep_master_strategy(self, runner, master_file, source_file, tmp_path):
        out_path = str(tmp_path / "merged_km.json")
        runner.invoke(cli, [
            "merge", "execute", master_file, source_file,
            "--strategy", "keep_master",
            "--threshold", "0.80",
            "--output-path", out_path,
        ])
        merged = JsonStore(out_path).load()
        witcher = next(
            (g for g in merged.all_games() if "Witcher" in g.Name), None
        )
        assert witcher is not None
        # With keep_master, master's cover should be preserved
        assert witcher.CoverImage == "cover_steam.jpg"

    def test_execute_keep_source_strategy(self, runner, master_file, source_file, tmp_path):
        out_path = str(tmp_path / "merged_ks.json")
        runner.invoke(cli, [
            "merge", "execute", master_file, source_file,
            "--strategy", "keep_source",
            "--threshold", "0.80",
            "--output-path", out_path,
        ])
        merged = JsonStore(out_path).load()
        witcher = next(
            (g for g in merged.all_games() if "Witcher" in g.Name), None
        )
        assert witcher is not None
        # With keep_source, source's cover should win
        assert witcher.CoverImage == "cover_gog.jpg"

    def test_execute_selective_merge(self, runner, source_file, tmp_path):
        """Only a specified game ID should be merged."""
        src = JsonStore(source_file).load()
        exclusive = next(g for g in src.all_games() if "Exclusive" in g.Name)
        master_games = [make_game("Unrelated Game", source="Steam")]
        master = make_library("m", master_games)
        master_path = tmp_path / "m.json"
        JsonStore(master_path).save(master)
        out_path = str(tmp_path / "selective.json")
        runner.invoke(cli, [
            "merge", "execute", str(master_path), source_file,
            "--include-game-id", exclusive.Id,
            "--output-path", out_path,
        ])
        merged = JsonStore(out_path).load()
        merged_names = {g.Name for g in merged.all_games()}
        assert "Source Exclusive Game" in merged_names
        assert "The Witcher 3: Wild Hunt" not in merged_names

    def test_execute_saves_result_file(self, runner, master_file, source_file, tmp_path):
        result_path = str(tmp_path / "result.json")
        runner.invoke(cli, [
            "merge", "execute", master_file, source_file,
            "--save-result", result_path,
        ])
        assert Path(result_path).exists()
        data = json.loads(Path(result_path).read_text())
        assert "backup_id" in data

    def test_execute_incremental_merge(self, runner, tmp_path):
        """Only source games modified after incremental_since are merged."""
        old_game = make_game("Old Source Game", year=2019, source="GOG")
        old_game.Modified = "2022-01-01T00:00:00"
        new_game = make_game("New Source Game", year=2023, source="GOG")
        new_game.Modified = "2024-06-01T00:00:00"
        source = make_library("source", [old_game, new_game])
        source_path = tmp_path / "inc_source.json"
        JsonStore(source_path).save(source)
        master = make_library("master", [])
        master_path = tmp_path / "inc_master.json"
        JsonStore(master_path).save(master)
        out_path = str(tmp_path / "inc_out.json")
        runner.invoke(cli, [
            "merge", "execute", str(master_path), str(source_path),
            "--incremental-since", "2023-01-01T00:00:00",
            "--output-path", out_path,
        ])
        result_lib = JsonStore(out_path).load()
        names = {g.Name for g in result_lib.all_games()}
        assert "New Source Game" in names
        assert "Old Source Game" not in names

    def test_execute_field_override(self, runner, master_file, source_file, tmp_path):
        out_path = str(tmp_path / "field_override.json")
        runner.invoke(cli, [
            "merge", "execute", master_file, source_file,
            "--strategy", "keep_master",
            "--field-override", "Description=keep_source",
            "--threshold", "0.80",
            "--output-path", out_path,
        ])
        merged = JsonStore(out_path).load()
        # Master's cover preserved (keep_master default)
        witcher = next(g for g in merged.all_games() if "Witcher" in g.Name)
        assert witcher.CoverImage == "cover_steam.jpg"


# ── rollback ──────────────────────────────────────────────────────────────────

class TestRollbackCommand:
    def test_rollback_restores_original(self, runner, master_file, source_file, tmp_path):
        before = json.loads(Path(master_file).read_text())
        backup_dir = str(tmp_path / "backups")
        result_path = str(tmp_path / "result.json")
        runner.invoke(cli, [
            "merge", "execute", master_file, source_file,
            "--threshold", "0.80",
            "--backup-dir", backup_dir,
            "--save-result", result_path,
        ])
        # Now roll back
        result = runner.invoke(cli, [
            "merge", "rollback", master_file, result_path,
            "--backup-dir", backup_dir,
        ])
        assert result.exit_code == 0
        after = json.loads(Path(master_file).read_text())
        before_ids = {g["Id"] for g in before["games"]}
        after_ids = {g["Id"] for g in after["games"]}
        assert before_ids == after_ids

    def test_rollback_json_output(self, runner, master_file, source_file, tmp_path):
        backup_dir = str(tmp_path / "backups")
        result_path = str(tmp_path / "result.json")
        runner.invoke(cli, [
            "merge", "execute", master_file, source_file,
            "--backup-dir", backup_dir,
            "--save-result", result_path,
        ])
        result = runner.invoke(cli, [
            "merge", "rollback", master_file, result_path,
            "--backup-dir", backup_dir,
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["rolled_back"] is True


# ── config export/import ──────────────────────────────────────────────────────

class TestConfigExportImport:
    def test_export_and_use_config(self, runner, master_file, source_file, tmp_path):
        config_path = str(tmp_path / "config.json")
        runner.invoke(cli, [
            "merge", "export-config", config_path,
            "--strategy", "most_complete",
            "--threshold", "0.78",
        ])
        assert Path(config_path).exists()
        cfg = json.loads(Path(config_path).read_text())
        assert cfg["strategy"] == "most_complete"
        assert cfg["match_threshold"] == 0.78

        # Use the config in an execute command
        out_path = str(tmp_path / "from_config.json")
        result = runner.invoke(cli, [
            "merge", "execute", master_file, source_file,
            "--config-file", config_path,
            "--output-path", out_path,
        ])
        assert result.exit_code == 0


# ── backup listing ────────────────────────────────────────────────────────────

class TestListBackupsCommand:
    def test_list_backups_after_merge(self, runner, master_file, source_file, tmp_path):
        backup_dir = str(tmp_path / "backups")
        runner.invoke(cli, [
            "merge", "execute", master_file, source_file,
            "--backup-dir", backup_dir,
        ])
        result = runner.invoke(cli, [
            "merge", "list-backups",
            "--backup-dir", backup_dir,
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) >= 1

    def test_list_backups_empty(self, runner, tmp_path):
        backup_dir = str(tmp_path / "empty_backups")
        result = runner.invoke(cli, [
            "merge", "list-backups",
            "--backup-dir", backup_dir,
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []
