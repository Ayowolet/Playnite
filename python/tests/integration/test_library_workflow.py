"""Integration tests demonstrating full library management workflows via CLI."""
from __future__ import annotations

import json
import time

import pytest
from click.testing import CliRunner

from playnite.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def invoke(runner, db_path):
    """Helper that invokes CLI commands against a temp database."""
    def _invoke(*args):
        return runner.invoke(cli, ["--db", db_path] + list(args))
    return _invoke


class TestLibraryWorkflowCLI:
    def test_add_and_list_game(self, invoke):
        result = invoke("library", "games", "add", "--name", "Test Game", "--json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "Test Game"

        result = invoke("library", "games", "list", "--json")
        assert result.exit_code == 0
        games = json.loads(result.output)
        assert any(g["name"] == "Test Game" for g in games)

    def test_add_with_metadata(self, invoke):
        result = invoke(
            "library", "games", "add",
            "--name", "Epic RPG",
            "--platform", "PC",
            "--genre", "RPG",
            "--tag", "indie",
            "--developer", "SmallStudio",
            "--year", "2023",
            "--json",
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["platforms"] == ["PC"]
        assert data["genres"] == ["RPG"]
        assert "indie" in data["tags"]
        assert data["developer"] == "SmallStudio"
        assert data["release_year"] == 2023

    def test_update_game(self, invoke):
        add_result = json.loads(invoke("library", "games", "add", "--name", "Old", "--json").output)
        gid = add_result["id"]
        result = invoke("library", "games", "update", gid, "--name", "New", "--json")
        assert result.exit_code == 0
        assert json.loads(result.output)["name"] == "New"

    def test_delete_game_json(self, invoke):
        gid = json.loads(invoke("library", "games", "add", "--name", "Del", "--json").output)["id"]
        result = invoke("library", "games", "delete", gid, "--json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["id"] == gid
        games = json.loads(invoke("library", "games", "list", "--json").output)
        assert not any(g["id"] == gid for g in games)

    def test_search_game(self, invoke):
        invoke("library", "games", "add", "--name", "Portal 2")
        result = invoke("library", "games", "search", "Portal", "--json")
        assert result.exit_code == 0
        results = json.loads(result.output)
        assert len(results) >= 1
        assert results[0]["game"]["name"] == "Portal 2"

    def test_favorite_workflow(self, invoke):
        gid = json.loads(invoke("library", "games", "add", "--name", "Fave", "--json").output)["id"]
        invoke("library", "games", "favorite", gid)
        result = invoke("library", "games", "list", "--favorite", "--json")
        games = json.loads(result.output)
        assert any(g["id"] == gid for g in games)
        invoke("library", "games", "unfavorite", gid)
        result = invoke("library", "games", "list", "--favorite", "--json")
        assert not any(g["id"] == gid for g in json.loads(result.output))

    def test_hide_unhide_json(self, invoke):
        gid = json.loads(invoke("library", "games", "add", "--name", "Ghost", "--json").output)["id"]
        result = invoke("library", "games", "hide", gid, "--json")
        assert result.exit_code == 0
        assert json.loads(result.output)["is_hidden"] is True
        games = json.loads(invoke("library", "games", "list", "--json").output)
        assert not any(g["id"] == gid for g in games)
        result = invoke("library", "games", "unhide", gid, "--json")
        assert json.loads(result.output)["is_hidden"] is False
        games = json.loads(invoke("library", "games", "list", "--json").output)
        assert any(g["id"] == gid for g in games)

    def test_apply_remove_tag(self, invoke):
        gid = json.loads(invoke("library", "games", "add", "--name", "Tagged", "--json").output)["id"]
        result = invoke("library", "games", "apply-tag", gid, "--tag", "special", "--json")
        assert result.exit_code == 0
        assert "special" in json.loads(result.output)["tags"]
        result = invoke("library", "games", "remove-tag", gid, "--tag", "special", "--json")
        assert result.exit_code == 0
        assert "special" not in json.loads(result.output)["tags"]

    def test_tags_crud(self, invoke):
        result = invoke("library", "tags", "add", "indie", "--json")
        assert result.exit_code == 0
        tag = json.loads(result.output)
        assert tag["name"] == "indie"

        result = invoke("library", "tags", "get", tag["id"], "--json")
        assert json.loads(result.output)["name"] == "indie"

        result = invoke("library", "tags", "update", tag["id"], "--name", "indie-renamed", "--json")
        assert json.loads(result.output)["name"] == "indie-renamed"

        result = invoke("library", "tags", "list", "--json")
        tags = json.loads(result.output)
        assert any(t["name"] == "indie-renamed" for t in tags)

        result = invoke("library", "tags", "delete", tag["id"], "--json")
        assert result.exit_code == 0
        assert json.loads(result.output)["ok"] is True

    def test_categories_crud(self, invoke):
        result = invoke("library", "categories", "add", "Backlog", "--json")
        cat = json.loads(result.output)
        assert cat["name"] == "Backlog"

        result = invoke("library", "categories", "get", cat["id"], "--json")
        assert json.loads(result.output)["name"] == "Backlog"

        result = invoke("library", "categories", "update", cat["id"], "--name", "Wishlist", "--json")
        assert json.loads(result.output)["name"] == "Wishlist"

        result = invoke("library", "categories", "delete", cat["id"], "--json")
        assert json.loads(result.output)["ok"] is True

    def test_genres_and_platforms_list(self, invoke):
        invoke("library", "games", "add", "--name", "G1", "--genre", "RPG", "--platform", "PC")
        result = invoke("library", "genres", "list", "--json")
        assert result.exit_code == 0
        assert any(g["name"] == "RPG" for g in json.loads(result.output))

        result = invoke("library", "platforms", "list", "--json")
        assert result.exit_code == 0
        assert any(p["name"] == "PC" for p in json.loads(result.output))

    def test_smart_collection_workflow(self, invoke):
        invoke("library", "games", "add", "--name", "RPG1", "--genre", "RPG", "--year", "2020")
        invoke("library", "games", "add", "--name", "Puzzle1", "--genre", "Puzzle", "--year", "2021")

        rules = json.dumps([{"field": "genre_names", "operator": "contains", "value": "RPG"}])
        result = invoke("library", "collections", "create", "All RPGs", "--rules", rules, "--json")
        assert result.exit_code == 0
        col = json.loads(result.output)

        result = invoke("library", "collections", "games", col["id"], "--json")
        assert result.exit_code == 0
        games = json.loads(result.output)
        assert all("RPG" in g["genres"] for g in games)

        result = invoke("library", "collections", "delete", col["id"], "--json")
        assert json.loads(result.output)["ok"] is True

    def test_view_preset_workflow(self, invoke):
        result = invoke(
            "library", "presets", "save", "myview",
            "--sort", "playtime", "--order", "desc",
            "--view", "grid",
            "--json",
        )
        assert result.exit_code == 0

        result = invoke("library", "presets", "load", "myview", "--json")
        assert result.exit_code == 0
        preset = json.loads(result.output)
        assert preset["sort_by"] == "playtime"
        assert preset["sort_order"] == "desc"
        assert preset["view_type"] == "grid"

        result = invoke("library", "presets", "delete", "myview", "--json")
        assert json.loads(result.output)["ok"] is True

    def test_preset_applied_to_games_list(self, invoke):
        invoke("library", "games", "add", "--name", "RPG Game", "--genre", "RPG")
        invoke("library", "games", "add", "--name", "Action Game", "--genre", "Action")
        invoke(
            "library", "presets", "save", "rpg-only",
            "--filters", json.dumps({"genres": ["RPG"]}),
        )
        result = invoke("library", "games", "list", "--preset", "rpg-only", "--json")
        assert result.exit_code == 0
        games = json.loads(result.output)
        assert all("RPG" in g["genres"] for g in games)
        assert len(games) == 1

    def test_stats(self, invoke):
        invoke("library", "games", "add", "--name", "G1")
        invoke("library", "games", "add", "--name", "G2")
        result = invoke("library", "stats", "--json")
        assert result.exit_code == 0
        stats = json.loads(result.output)
        assert stats["total_games"] == 2

    def test_bulk_tag_cli(self, invoke):
        id1 = json.loads(invoke("library", "games", "add", "--name", "A", "--json").output)["id"]
        id2 = json.loads(invoke("library", "games", "add", "--name", "B", "--json").output)["id"]
        result = invoke("library", "games", "bulk-tag", id1, id2, "--tag", "weekend", "--json")
        assert result.exit_code == 0
        assert json.loads(result.output)["updated"] == 2

    def test_bulk_delete_cli(self, invoke):
        id1 = json.loads(invoke("library", "games", "add", "--name", "X", "--json").output)["id"]
        id2 = json.loads(invoke("library", "games", "add", "--name", "Y", "--json").output)["id"]
        result = invoke("library", "games", "bulk-delete", id1, id2, "--json")
        assert result.exit_code == 0
        assert json.loads(result.output)["deleted"] == 2
        assert json.loads(invoke("library", "games", "list", "--json").output) == []

    def test_bulk_hide_unhide_cli(self, invoke):
        id1 = json.loads(invoke("library", "games", "add", "--name", "H1", "--json").output)["id"]
        id2 = json.loads(invoke("library", "games", "add", "--name", "H2", "--json").output)["id"]
        result = invoke("library", "games", "bulk-hide", id1, id2, "--json")
        assert json.loads(result.output)["hidden"] == 2
        assert json.loads(invoke("library", "games", "list", "--json").output) == []
        result = invoke("library", "games", "bulk-unhide", id1, id2, "--json")
        assert json.loads(result.output)["unhidden"] == 2
        assert len(json.loads(invoke("library", "games", "list", "--json").output)) == 2

    def test_filter_by_platform_cli(self, invoke):
        invoke("library", "games", "add", "--name", "PC Game", "--platform", "PC")
        invoke("library", "games", "add", "--name", "Console Game", "--platform", "PS5")
        result = invoke("library", "games", "list", "--platform", "PC", "--json")
        games = json.loads(result.output)
        assert all("PC" in g["platforms"] for g in games)


class TestPerformance:
    """Verify sub-second performance with 1000+ games."""

    def test_bulk_insert_and_filter(self, db_path):
        from playnite.library.organisation import LibraryManager
        from playnite.library.filters import FilterSpec

        manager = LibraryManager(f"sqlite:///{db_path}")
        genres = ["RPG", "Action", "Puzzle", "Strategy", "Sandbox"]
        platforms = ["PC", "PS5", "Xbox", "Switch"]

        for i in range(1000):
            manager.add_game(
                name=f"Game {i:04d}",
                release_year=2000 + (i % 24),
                playtime=i * 60,
                user_score=50 + (i % 51),
                genres=[genres[i % len(genres)]],
                platforms=[platforms[i % len(platforms)]],
            )

        start = time.time()
        results = manager.list_games(
            filter_spec=FilterSpec(genres=["RPG"], release_year_min=2010, rating_min=70),
        )
        elapsed = time.time() - start

        assert elapsed < 1.0, f"Filter took {elapsed:.2f}s — must be < 1s"
        assert len(results) > 0

    def test_bulk_search_performance(self, db_path):
        from playnite.library.organisation import LibraryManager

        manager = LibraryManager(f"sqlite:///{db_path}")
        for i in range(1000):
            manager.add_game(name=f"Title {i:03d}", developer=f"Dev {i % 20}")

        start = time.time()
        results = manager.search("Title 1")
        elapsed = time.time() - start

        assert elapsed < 1.0, f"Search took {elapsed:.2f}s — must be < 1s"

    def test_sort_1000_games_under_1s(self, db_path):
        from playnite.library.organisation import LibraryManager

        manager = LibraryManager(f"sqlite:///{db_path}")
        for i in range(1000):
            manager.add_game(name=f"Sort {i:04d}", release_year=2000 + (i % 24))

        start = time.time()
        games = manager.list_games(sort_by="release_year", sort_order="desc")
        elapsed = time.time() - start

        assert elapsed < 1.0, f"Sort took {elapsed:.2f}s — must be < 1s"
        assert len(games) == 1000

    def test_bulk_update_500_games(self, db_path):
        from playnite.library.organisation import LibraryManager

        manager = LibraryManager(f"sqlite:///{db_path}")
        for i in range(500):
            manager.add_game(name=f"BulkPerf {i:04d}")
        ids = [g["id"] for g in manager.list_games()]

        start = time.time()
        manager.bulk_update(ids, completion_status="completed")
        elapsed = time.time() - start

        assert elapsed < 0.5, f"bulk_update took {elapsed:.2f}s — must be < 0.5s"
