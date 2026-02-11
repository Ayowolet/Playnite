"""
Tests for game_library.storage.json_store.JsonStore.

Covers:
- Flat layout round-trips (save → load → compare)
- Playnite layout round-trips
- Schema versioning (v1 field present on save; legacy v0 files load cleanly;
  future-version files log a warning but still load)
- Atomic write safety (tmp file is cleaned up; original survives a failed write)
- Malformed / corrupt file recovery (skipped with a logged warning)
- PermissionError forwarding with user-readable messages
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any
from unittest import mock

import pytest

from game_library.models.game import Game, Link, ReleaseDate
from game_library.models.library import Library, LibrarySource, NamedEntity
from game_library.storage.json_store import SCHEMA_VERSION, JsonStore


# ── Helpers ───────────────────────────────────────────────────────────────────

def _game(name: str, year: int | None = None) -> Game:
    g = Game(Id=str(uuid.uuid4()), Name=name)
    if year:
        g.ReleaseDate = ReleaseDate(Year=year)
    return g


def _lib(name: str = "test", games: list[Game] | None = None) -> Library:
    lib = Library(source=LibrarySource(name=name, path="/fake", priority=5))
    for g in games or []:
        lib.games[g.Id] = g
    return lib


# ── Schema version constant ───────────────────────────────────────────────────

class TestSchemaVersionConstant:
    def test_is_positive_int(self):
        assert isinstance(SCHEMA_VERSION, int)
        assert SCHEMA_VERSION >= 1


# ── Flat layout round-trips ───────────────────────────────────────────────────

class TestFlatRoundTrip:
    def test_empty_library(self, tmp_path):
        path = tmp_path / "lib.json"
        JsonStore(path).save(_lib())
        loaded = JsonStore(path).load()
        assert len(loaded.games) == 0

    def test_single_game_preserved(self, tmp_path):
        path = tmp_path / "lib.json"
        game = _game("Portal 2", year=2011)
        JsonStore(path).save(_lib(games=[game]))
        loaded = JsonStore(path).load()
        assert game.Id in loaded.games
        lg = loaded.games[game.Id]
        assert lg.Name == "Portal 2"
        assert lg.release_year == 2011

    def test_multiple_games_preserved(self, tmp_path):
        path = tmp_path / "lib.json"
        games = [_game(f"Game {i}", year=2000 + i) for i in range(10)]
        JsonStore(path).save(_lib(games=games))
        loaded = JsonStore(path).load()
        assert len(loaded.games) == 10
        for g in games:
            assert loaded.games[g.Id].Name == g.Name

    def test_source_metadata_preserved(self, tmp_path):
        path = tmp_path / "lib.json"
        lib = Library(source=LibrarySource(name="MyLib", path="/real/path", priority=3))
        JsonStore(path).save(lib)
        loaded = JsonStore(path).load()
        assert loaded.source.name == "MyLib"
        assert loaded.source.priority == 3

    def test_game_with_all_fields_preserved(self, tmp_path):
        """Playtime, scores, flags, links, and dates all survive the round-trip."""
        path = tmp_path / "lib.json"
        game = Game(
            Id=str(uuid.uuid4()),
            Name="The Witcher 3",
            Playtime=7200,
            PlayCount=5,
            UserScore=95,
            CriticScore=93,
            CommunityScore=92,
            IsInstalled=True,
            Favorite=True,
            ReleaseDate=ReleaseDate(Year=2015, Month=5, Day=19),
            Links=[Link(Name="GOG", Url="https://example.com")],
            Description="Open world RPG",
        )
        JsonStore(path).save(_lib(games=[game]))
        loaded = JsonStore(path).load()
        lg = loaded.games[game.Id]
        assert lg.Playtime == 7200
        assert lg.Favorite is True
        assert lg.UserScore == 95
        assert lg.release_year == 2015
        assert len(lg.Links) == 1
        assert lg.Links[0].Name == "GOG"

    def test_reference_entities_preserved(self, tmp_path):
        path = tmp_path / "lib.json"
        lib = _lib()
        lib.platforms["p1"] = NamedEntity(Id="p1", Name="PC")
        lib.companies["c1"] = NamedEntity(Id="c1", Name="Valve")
        lib.genres["g1"] = NamedEntity(Id="g1", Name="Action")
        JsonStore(path).save(lib)
        loaded = JsonStore(path).load()
        assert loaded.platforms["p1"].Name == "PC"
        assert loaded.companies["c1"].Name == "Valve"
        assert loaded.genres["g1"].Name == "Action"

    def test_nonexistent_file_returns_empty_library(self, tmp_path):
        path = tmp_path / "does_not_exist.json"
        loaded = JsonStore(path).load(source_name="default")
        assert len(loaded.games) == 0

    def test_overwrite_replaces_all_games(self, tmp_path):
        path = tmp_path / "lib.json"
        JsonStore(path).save(_lib(games=[_game("Game A")]))
        lib2 = _lib(games=[_game("Game B"), _game("Game C")])
        JsonStore(path).save(lib2)
        loaded = JsonStore(path).load()
        assert len(loaded.games) == 2
        assert {g.Name for g in loaded.games.values()} == {"Game B", "Game C"}

    def test_load_passes_source_name_when_not_stored(self, tmp_path):
        path = tmp_path / "lib.json"
        # Write a legacy file without a source block
        path.write_text(
            json.dumps({
                "schema_version": SCHEMA_VERSION,
                "games": [],
                "platforms": [], "companies": [], "genres": [],
                "categories": [], "tags": [], "series": [],
                "sources": [], "age_ratings": [], "regions": [],
                "completion_statuses": [],
            }),
            encoding="utf-8",
        )
        loaded = JsonStore(path).load(source_name="custom")
        assert loaded.source.name == "custom"


# ── Schema versioning ─────────────────────────────────────────────────────────

class TestFlatSchemaVersion:
    def test_saved_file_contains_schema_version(self, tmp_path):
        path = tmp_path / "lib.json"
        JsonStore(path).save(_lib())
        data = json.loads(path.read_text())
        assert data.get("schema_version") == SCHEMA_VERSION

    def test_legacy_file_without_version_loads_cleanly(self, tmp_path):
        """Files written before versioning was added must still load."""
        path = tmp_path / "lib.json"
        legacy: dict[str, Any] = {
            "source": {"name": "legacy", "path": "", "priority": 99},
            "games": [],
            "platforms": [], "companies": [], "genres": [],
            "categories": [], "tags": [], "series": [],
            "sources": [], "age_ratings": [], "regions": [],
            "completion_statuses": [],
            # No "schema_version" key
        }
        path.write_text(json.dumps(legacy), encoding="utf-8")
        loaded = JsonStore(path).load()
        assert loaded.source.name == "legacy"

    def test_future_schema_version_logs_warning_and_still_loads(self, tmp_path, caplog):
        path = tmp_path / "lib.json"
        future: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION + 999,
            "source": {"name": "future", "path": "", "priority": 99},
            "games": [],
            "platforms": [], "companies": [], "genres": [],
            "categories": [], "tags": [], "series": [],
            "sources": [], "age_ratings": [], "regions": [],
            "completion_statuses": [],
        }
        path.write_text(json.dumps(future), encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="game_library.storage.json_store"):
            loaded = JsonStore(path).load()
        assert loaded.source.name == "future"
        assert any(
            "schema" in r.message.lower() or "version" in r.message.lower()
            for r in caplog.records
        )

    def test_current_version_produces_no_migration_warning(self, tmp_path, caplog):
        path = tmp_path / "lib.json"
        JsonStore(path).save(_lib())
        with caplog.at_level(logging.WARNING, logger="game_library.storage.json_store"):
            JsonStore(path).load()
        assert not any(
            "schema" in r.message.lower() and "version" in r.message.lower()
            for r in caplog.records
        )


# ── Atomic write safety ───────────────────────────────────────────────────────

class TestFlatAtomicWrite:
    def test_tmp_file_cleaned_up_after_success(self, tmp_path):
        path = tmp_path / "lib.json"
        JsonStore(path).save(_lib())
        assert not path.with_suffix(".tmp").exists()

    def test_original_file_unchanged_when_replace_fails(self, tmp_path):
        """If os.replace raises, the original must be left intact."""
        path = tmp_path / "lib.json"
        JsonStore(path).save(_lib(games=[_game("Original")]))
        original_text = path.read_text()

        with mock.patch("os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                JsonStore(path).save(_lib(games=[_game("New")]))

        assert path.read_text() == original_text

    def test_tmp_file_removed_when_replace_fails(self, tmp_path):
        path = tmp_path / "lib.json"
        JsonStore(path).save(_lib())

        with mock.patch("os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                JsonStore(path).save(_lib(games=[_game("New")]))

        assert not path.with_suffix(".tmp").exists()


# ── Flat error handling ───────────────────────────────────────────────────────

class TestFlatErrorHandling:
    def test_malformed_json_raises(self, tmp_path):
        path = tmp_path / "lib.json"
        path.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            JsonStore(path).load()

    @pytest.mark.skipif(os.name == "nt", reason="chmod not reliable on Windows")
    def test_unreadable_file_raises_permission_error_with_message(self, tmp_path):
        path = tmp_path / "lib.json"
        JsonStore(path).save(_lib())
        path.chmod(0o000)
        try:
            with pytest.raises(PermissionError, match="Cannot read"):
                JsonStore(path).load()
        finally:
            path.chmod(0o644)


# ── Playnite layout round-trips ───────────────────────────────────────────────

class TestPlayniteRoundTrip:
    def test_empty_library(self, tmp_path):
        JsonStore(tmp_path, playnite=True).save(_lib())
        loaded = JsonStore(tmp_path, playnite=True).load()
        assert len(loaded.games) == 0

    def test_single_game_preserved(self, tmp_path):
        game = _game("Halo 2", year=2004)
        JsonStore(tmp_path, playnite=True).save(_lib(games=[game]))
        loaded = JsonStore(tmp_path, playnite=True).load()
        assert game.Id in loaded.games
        assert loaded.games[game.Id].Name == "Halo 2"
        assert loaded.games[game.Id].release_year == 2004

    def test_creates_games_and_platforms_directories(self, tmp_path):
        lib = _lib(games=[_game("Test")])
        lib.platforms["p1"] = NamedEntity(Id="p1", Name="PC")
        JsonStore(tmp_path, playnite=True).save(lib)
        assert (tmp_path / "games").is_dir()
        assert (tmp_path / "platforms").is_dir()

    def test_each_game_gets_own_json_file(self, tmp_path):
        games = [_game(f"Game {i}") for i in range(3)]
        JsonStore(tmp_path, playnite=True).save(_lib(games=games))
        assert len(list((tmp_path / "games").glob("*.json"))) == 3

    def test_entity_tables_preserved(self, tmp_path):
        lib = _lib()
        lib.platforms["p1"] = NamedEntity(Id="p1", Name="PlayStation 5")
        lib.companies["c1"] = NamedEntity(Id="c1", Name="Sony")
        JsonStore(tmp_path, playnite=True).save(lib)
        loaded = JsonStore(tmp_path, playnite=True).load()
        assert loaded.platforms["p1"].Name == "PlayStation 5"
        assert loaded.companies["c1"].Name == "Sony"

    def test_missing_games_dir_returns_empty_library(self, tmp_path):
        loaded = JsonStore(tmp_path, playnite=True).load()
        assert len(loaded.games) == 0

    def test_multiple_games_round_trip(self, tmp_path):
        games = [_game(f"Title {i}", year=2010 + i) for i in range(5)]
        JsonStore(tmp_path, playnite=True).save(_lib(games=games))
        loaded = JsonStore(tmp_path, playnite=True).load()
        assert len(loaded.games) == 5
        for g in games:
            assert g.Id in loaded.games


# ── Playnite corrupt file recovery ───────────────────────────────────────────

class TestPlayniteCorruptFileRecovery:
    def test_corrupt_game_file_skipped_with_warning(self, tmp_path, caplog):
        """A corrupt JSON file in games/ is skipped; valid games still load."""
        lib = _lib(games=[_game("Good Game")])
        JsonStore(tmp_path, playnite=True).save(lib)
        (tmp_path / "games" / "corrupt.json").write_text("{invalid}", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="game_library.storage.json_store"):
            loaded = JsonStore(tmp_path, playnite=True).load()

        assert len(loaded.games) == 1
        assert any(
            "corrupt" in r.message.lower() or "skip" in r.message.lower()
            for r in caplog.records
        )

    def test_corrupt_entity_file_skipped_with_warning(self, tmp_path, caplog):
        """A corrupt platform JSON is skipped; the rest of the library loads."""
        JsonStore(tmp_path, playnite=True).save(_lib())
        (tmp_path / "platforms").mkdir(exist_ok=True)
        (tmp_path / "platforms" / "bad.json").write_text("{invalid}", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="game_library.storage.json_store"):
            loaded = JsonStore(tmp_path, playnite=True).load()

        assert isinstance(loaded, Library)
        assert any(
            "corrupt" in r.message.lower() or "skip" in r.message.lower()
            for r in caplog.records
        )

    def test_multiple_corrupt_games_all_skipped(self, tmp_path, caplog):
        """Each corrupt file generates its own warning; valid games are kept."""
        good = _game("Valid")
        lib = _lib(games=[good])
        JsonStore(tmp_path, playnite=True).save(lib)
        for i in range(3):
            (tmp_path / "games" / f"bad_{i}.json").write_text("not json", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="game_library.storage.json_store"):
            loaded = JsonStore(tmp_path, playnite=True).load()

        assert len(loaded.games) == 1
        assert loaded.games[good.Id].Name == "Valid"
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 3
