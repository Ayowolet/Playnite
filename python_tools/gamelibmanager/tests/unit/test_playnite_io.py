"""Tests for Playnite I/O."""

import json
import uuid

import pytest
from gamelibmanager.db.database import GameDatabase
from gamelibmanager.db.playnite_io import PlayniteLibraryReader, PlayniteLibraryWriter
from gamelibmanager.models.game import Game
from gamelibmanager.models.release_date import ReleaseDate
from gamelibmanager.models.link import Link


class TestPlayniteLibraryReader:
    def test_read_game(self, tmp_playnite_lib):
        reader = PlayniteLibraryReader(tmp_playnite_lib)
        games = reader.read_all_games()
        assert len(games) == 1
        assert games[0].name == "Test Game Alpha"
        assert games[0].playtime == 3600

    def test_read_release_date(self, tmp_playnite_lib):
        reader = PlayniteLibraryReader(tmp_playnite_lib)
        games = reader.read_all_games()
        assert games[0].release_date is not None
        assert games[0].release_date.year == 2020
        assert games[0].release_date.month == 6
        assert games[0].release_date.day == 15

    def test_read_platforms(self, tmp_playnite_lib):
        reader = PlayniteLibraryReader(tmp_playnite_lib)
        platforms = reader.read_all_platforms()
        assert len(platforms) == 1
        assert platforms[0].name == "PC"

    def test_read_sources(self, tmp_playnite_lib):
        reader = PlayniteLibraryReader(tmp_playnite_lib)
        sources = reader.read_all_sources()
        assert len(sources) == 1
        assert sources[0].name == "Steam"

    def test_import_to_database(self, tmp_playnite_lib, tmp_path):
        reader = PlayniteLibraryReader(tmp_playnite_lib)
        db_path = tmp_path / "imported.db"
        with GameDatabase(str(db_path)) as db:
            count = reader.import_to_database(db)
            assert count == 1
            assert db.game_count() == 1

    def test_read_empty_directory(self, tmp_path):
        lib_path = tmp_path / "empty_lib"
        (lib_path / "games").mkdir(parents=True)
        reader = PlayniteLibraryReader(lib_path)
        games = reader.read_all_games()
        assert len(games) == 0

    def test_read_game_with_links(self, tmp_path):
        lib_path = tmp_path / "lib"
        (lib_path / "games").mkdir(parents=True)
        game_id = str(uuid.uuid4())
        game_data = {
            "Id": game_id,
            "Name": "Linked Game",
            "Links": [
                {"Name": "Store", "Url": "https://store.example.com"},
                {"Name": "Wiki", "Url": "https://wiki.example.com"},
            ],
        }
        with open(lib_path / "games" / f"{game_id}.json", "w") as f:
            json.dump(game_data, f)

        reader = PlayniteLibraryReader(lib_path)
        games = reader.read_all_games()
        assert len(games) == 1
        assert len(games[0].links) == 2
        assert games[0].links[0].name == "Store"

    def test_read_invalid_json_skipped(self, tmp_path):
        lib_path = tmp_path / "lib"
        (lib_path / "games").mkdir(parents=True)
        with open(lib_path / "games" / "bad.json", "w") as f:
            f.write("not valid json{{{")
        reader = PlayniteLibraryReader(lib_path)
        games = reader.read_all_games()
        assert len(games) == 0


class TestPlayniteLibraryWriter:
    def test_write_game(self, tmp_path):
        lib_path = tmp_path / "output"
        game = Game(name="Written Game", release_date=ReleaseDate(2020, 6, 15))
        PlayniteLibraryWriter.write_game(game, lib_path)

        fp = lib_path / "games" / f"{game.id}.json"
        assert fp.exists()
        with open(fp) as f:
            data = json.load(f)
        assert data["Name"] == "Written Game"
        assert data["ReleaseDate"] == "2020-6-15"

    def test_write_game_with_links(self, tmp_path):
        lib_path = tmp_path / "output"
        game = Game(
            name="Link Game",
            links=[Link(name="Store", url="https://store.example.com")],
        )
        PlayniteLibraryWriter.write_game(game, lib_path)

        fp = lib_path / "games" / f"{game.id}.json"
        with open(fp) as f:
            data = json.load(f)
        assert len(data["Links"]) == 1
        assert data["Links"][0]["Name"] == "Store"

    def test_round_trip(self, tmp_path):
        lib_path = tmp_path / "roundtrip"
        game = Game(
            name="Round Trip Game",
            game_id="rt_123",
            release_date=ReleaseDate(2020, 6),
            playtime=1800,
            is_installed=True,
        )
        PlayniteLibraryWriter.write_game(game, lib_path)

        reader = PlayniteLibraryReader(lib_path)
        games = reader.read_all_games()
        assert len(games) == 1
        assert games[0].name == "Round Trip Game"
        assert games[0].game_id == "rt_123"
        assert games[0].release_date.year == 2020
        assert games[0].release_date.month == 6
        assert games[0].playtime == 1800
