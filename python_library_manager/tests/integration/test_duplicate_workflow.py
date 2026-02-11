"""
Integration tests: complete duplicate detection and resolution workflow via CLI.

Each test calls the ``gamelibrary duplicates`` commands through the Click
test runner so that the full code path (storage → detection → resolution →
output) is exercised end-to-end.
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
def library_file(tmp_path):
    """Write a small library to a flat JSON file and return its path."""
    games = [
        make_game("The Witcher 3: Wild Hunt", year=2015, platforms=["PC"],
                  developers=["CD Projekt Red"], source="Steam", installed=True, playtime=7200,
                  cover="cover_steam.jpg"),
        make_game("The Witcher 3: Wild Hunt", year=2015, platforms=["PC"],
                  developers=["CD Projekt Red"], source="GOG", playtime=3600),
        make_game("Portal 2", year=2011, platforms=["PC"], developers=["Valve"], source="Steam"),
        make_game("Portal 2", year=2011, platforms=["PC"], developers=["Valve Corporation"],
                  source="GOG"),
        make_game("Cyberpunk 2077", year=2020, platforms=["PC"],
                  developers=["CD Projekt Red"], source="GOG"),
    ]
    lib = make_library("integration-test", games)
    lib_path = tmp_path / "library.json"
    JsonStore(lib_path).save(lib)
    return str(lib_path)


# ── detect ────────────────────────────────────────────────────────────────────

class TestDetectCommand:
    def test_detect_exits_1_when_duplicates_found(self, runner, library_file):
        result = runner.invoke(cli, ["duplicates", "detect", library_file])
        assert result.exit_code == 1  # duplicates found → exit 1

    def test_detect_json_output(self, runner, library_file):
        result = runner.invoke(cli, ["duplicates", "detect", library_file, "--json-output"])
        assert result.exit_code in (0, 1)
        data = json.loads(result.output)
        assert "groups" in data
        assert "total_games" in data
        assert data["group_count"] >= 2  # Witcher 3 + Portal 2

    def test_detect_saves_report(self, runner, library_file, tmp_path):
        report_path = str(tmp_path / "report.json")
        result = runner.invoke(cli, [
            "duplicates", "detect", library_file,
            "--save-report", report_path,
        ])
        assert Path(report_path).exists()
        data = json.loads(Path(report_path).read_text())
        assert "groups" in data

    def test_detect_respects_threshold(self, runner, library_file, tmp_path):
        """Very high threshold should find fewer or no groups."""
        result_strict = runner.invoke(cli, [
            "duplicates", "detect", library_file,
            "--threshold", "0.99",
            "--json-output",
        ])
        result_loose = runner.invoke(cli, [
            "duplicates", "detect", library_file,
            "--threshold", "0.70",
            "--json-output",
        ])
        strict_data = json.loads(result_strict.output)
        loose_data = json.loads(result_loose.output)
        assert strict_data["group_count"] <= loose_data["group_count"]

    def test_detect_source_priority(self, runner, library_file, tmp_path):
        """Steam should be master when listed first."""
        result = runner.invoke(cli, [
            "duplicates", "detect", library_file,
            "--source-priority", "Steam",
            "--source-priority", "GOG",
            "--json-output",
        ])
        data = json.loads(result.output)
        for group in data["groups"]:
            assert group["master"]["source"] == "Steam"

    def test_detect_exclude_hidden(self, runner, tmp_path):
        """Hidden games should be excluded when --exclude-hidden is set."""
        games = [
            make_game("Doom Eternal", year=2020, source="Steam"),
            make_game("Doom Eternal", year=2020, source="GOG", hidden=True),
        ]
        lib = make_library("test", games)
        lib_path = tmp_path / "hidden_test.json"
        JsonStore(lib_path).save(lib)
        result = runner.invoke(cli, [
            "duplicates", "detect", str(lib_path),
            "--exclude-hidden",
            "--json-output",
        ])
        data = json.loads(result.output)
        assert data["games_scanned"] == 1  # hidden game excluded

    def test_detect_similarity_mode(self, runner, library_file):
        result = runner.invoke(cli, [
            "duplicates", "detect", library_file,
            "--similarity-mode",
            "--similarity-threshold", "0.60",
            "--json-output",
        ])
        assert result.exit_code in (0, 1)
        data = json.loads(result.output)
        assert "groups" in data


# ── resolve ───────────────────────────────────────────────────────────────────

class TestResolveCommand:
    @pytest.fixture
    def report_file(self, runner, library_file, tmp_path):
        report_path = str(tmp_path / "report.json")
        runner.invoke(cli, [
            "duplicates", "detect", library_file,
            "--threshold", "0.80",
            "--save-report", report_path,
        ])
        return report_path

    def test_resolve_hide_action(self, runner, library_file, report_file, tmp_path):
        out_path = str(tmp_path / "out.json")
        result = runner.invoke(cli, [
            "duplicates", "resolve", library_file, report_file,
            "--action", "hide",
            "--output-path", out_path,
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["action"] == "hide"
        assert data["groups_processed"] >= 2

    def test_resolve_delete_action(self, runner, library_file, report_file, tmp_path):
        out_path = str(tmp_path / "out_delete.json")
        result = runner.invoke(cli, [
            "duplicates", "resolve", library_file, report_file,
            "--action", "delete",
            "--output-path", out_path,
        ])
        assert result.exit_code == 0
        # Verify the output library has fewer games
        restored = JsonStore(out_path).load()
        assert len(restored.games) < 5  # started with 5 games

    def test_resolve_saves_history(self, runner, library_file, report_file, tmp_path):
        history_path = str(tmp_path / "history.json")
        out_path = str(tmp_path / "out.json")
        result = runner.invoke(cli, [
            "duplicates", "resolve", library_file, report_file,
            "--action", "merge",
            "--save-history", history_path,
            "--output-path", out_path,
        ])
        assert result.exit_code == 0
        assert Path(history_path).exists()
        history = json.loads(Path(history_path).read_text())
        assert len(history) >= 2


# ── report display ────────────────────────────────────────────────────────────

class TestReportCommand:
    def test_report_json_output(self, runner, library_file, tmp_path):
        report_path = str(tmp_path / "report.json")
        runner.invoke(cli, [
            "duplicates", "detect", library_file,
            "--save-report", report_path,
        ])
        result = runner.invoke(cli, [
            "duplicates", "report", report_path,
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "groups" in data

    def test_report_text_output(self, runner, library_file, tmp_path):
        report_path = str(tmp_path / "report.json")
        runner.invoke(cli, [
            "duplicates", "detect", library_file,
            "--save-report", report_path,
        ])
        result = runner.invoke(cli, ["duplicates", "report", report_path])
        assert result.exit_code == 0
        assert "Duplicate Detection Report" in result.output


# ── end-to-end: complete workflow ─────────────────────────────────────────────

class TestCompleteWorkflow:
    def test_detect_then_bulk_hide_100_duplicates(self, tmp_path):
        """100+ duplicate pairs should be handled within bulk operation.

        Each pair has an identical title across Steam and GOG sources.
        Titles use short MD5 hex digests to ensure cross-pair similarity is
        low enough that no false cross-matching occurs.
        """
        import hashlib
        games = []
        for i in range(100):
            # Unique 8-char hex suffix per pair → very low cross-pair similarity
            uid = hashlib.md5(f"pair-{i}".encode()).hexdigest()[:8]
            title = f"{uid}"
            year = 2000 + (i % 23)
            games.append(make_game(title, year=year, source="Steam"))
            games.append(make_game(title, year=year, source="GOG"))
        lib = make_library("big", games)
        lib_path = tmp_path / "big_lib.json"
        JsonStore(lib_path).save(lib)
        runner = CliRunner()
        # Step 1: detect
        report_path = str(tmp_path / "report.json")
        r1 = runner.invoke(cli, [
            "duplicates", "detect", str(lib_path),
            "--threshold", "0.80",
            "--save-report", report_path,
            "--json-output",
        ])
        data = json.loads(r1.output)
        assert data["group_count"] == 100, (
            f"Expected 100 groups, got {data['group_count']}"
        )
        # Step 2: resolve (hide all duplicates)
        out_path = str(tmp_path / "resolved.json")
        r2 = runner.invoke(cli, [
            "duplicates", "resolve", str(lib_path), report_path,
            "--action", "hide",
            "--output-path", out_path,
        ])
        assert r2.exit_code == 0
        # Each group has 1 master + 1 duplicate → 100 hidden games
        resolved_lib = JsonStore(out_path).load()
        hidden_count = sum(1 for g in resolved_lib.all_games() if g.Hidden)
        assert hidden_count == 100  # one duplicate per pair hidden
