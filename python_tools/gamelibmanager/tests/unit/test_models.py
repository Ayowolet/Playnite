"""Tests for data models."""

import os
import sys
import uuid
from datetime import datetime

import pytest
from gamelibmanager.models.base import DatabaseObject
from gamelibmanager.models.game import Game
from gamelibmanager.models.release_date import ReleaseDate
from gamelibmanager.models.link import Link
from gamelibmanager.models.game_action import GameAction, GameActionType
from gamelibmanager.models.game_rom import GameRom
from gamelibmanager.models.lookup_tables import Platform, Genre, Company


class TestDatabaseObject:
    def test_equality_by_id(self):
        uid = uuid.uuid4()
        a = DatabaseObject(id=uid, name="A")
        b = DatabaseObject(id=uid, name="B")
        assert a == b

    def test_inequality_different_id(self):
        a = DatabaseObject(name="Same Name")
        b = DatabaseObject(name="Same Name")
        assert a != b

    def test_hash_by_id(self):
        uid = uuid.uuid4()
        a = DatabaseObject(id=uid)
        b = DatabaseObject(id=uid)
        assert hash(a) == hash(b)

    def test_auto_generated_id(self):
        obj = DatabaseObject(name="Test")
        assert isinstance(obj.id, uuid.UUID)


class TestReleaseDate:
    def test_year_only(self):
        rd = ReleaseDate(year=2020)
        assert rd.serialize() == "2020"

    def test_year_month(self):
        rd = ReleaseDate(year=2020, month=6)
        assert rd.serialize() == "2020-6"

    def test_year_month_day(self):
        rd = ReleaseDate(year=2020, month=6, day=15)
        assert rd.serialize() == "2020-6-15"

    def test_deserialize_year(self):
        rd = ReleaseDate.deserialize("2020")
        assert rd.year == 2020
        assert rd.month is None
        assert rd.day is None

    def test_deserialize_year_month(self):
        rd = ReleaseDate.deserialize("2020-6")
        assert rd.year == 2020
        assert rd.month == 6

    def test_deserialize_year_month_day(self):
        rd = ReleaseDate.deserialize("2020-6-15")
        assert rd.year == 2020
        assert rd.month == 6
        assert rd.day == 15

    def test_round_trip(self):
        original = ReleaseDate(2015, 5, 19)
        s = original.serialize()
        restored = ReleaseDate.deserialize(s)
        assert restored == original

    def test_date_property(self):
        rd = ReleaseDate(2020, 6, 15)
        d = rd.date
        assert d.year == 2020
        assert d.month == 6
        assert d.day == 15


class TestGame:
    def test_default_construction(self):
        g = Game(name="Test")
        assert g.name == "Test"
        assert isinstance(g.id, uuid.UUID)
        assert g.hidden is False
        assert g.is_installed is False
        assert g.playtime == 0

    def test_release_year_property(self):
        g = Game(name="Test", release_date=ReleaseDate(2020))
        assert g.release_year == 2020

    def test_release_year_none(self):
        g = Game(name="Test")
        assert g.release_year is None

    def test_is_custom_game(self):
        g = Game(name="Custom")
        assert g.is_custom_game is True

    def test_not_custom_game(self):
        g = Game(name="Plugin", plugin_id=uuid.uuid4())
        assert g.is_custom_game is False


class TestLink:
    def test_equality(self):
        a = Link(name="Store", url="https://store.example.com")
        b = Link(name="Store", url="https://store.example.com")
        assert a == b

    def test_inequality(self):
        a = Link(name="Store", url="https://a.com")
        b = Link(name="Store", url="https://b.com")
        assert a != b


class TestGameRom:
    def test_equality(self):
        a = GameRom(name="rom.iso", path="/roms/rom.iso")
        b = GameRom(name="rom.iso", path="/roms/rom.iso")
        assert a == b

    @pytest.mark.skipif(sys.platform != "win32", reason="normcase only lowercases on Windows")
    def test_equality_case_insensitive_path_windows(self):
        """Paths differing only in case should be equal on Windows."""
        a = GameRom(name="rom.iso", path="C:\\Roms\\Game.iso")
        b = GameRom(name="rom.iso", path="c:\\roms\\game.iso")
        assert a == b

    @pytest.mark.skipif(sys.platform != "win32", reason="normcase only lowercases on Windows")
    def test_hash_case_insensitive_path_windows(self):
        """Hash should be identical for paths differing only in case on Windows."""
        a = GameRom(name="rom.iso", path="C:\\Roms\\Game.iso")
        b = GameRom(name="rom.iso", path="c:\\roms\\game.iso")
        assert hash(a) == hash(b)

    def test_normcase_applied_to_path(self):
        """Verify os.path.normcase is applied: paths equal after normcase are equal."""
        raw = "/Roms/Game.iso"
        a = GameRom(name="rom.iso", path=raw)
        b = GameRom(name="rom.iso", path=os.path.normcase(raw))
        assert a == b
        assert hash(a) == hash(b)

    def test_inequality_different_path(self):
        a = GameRom(name="rom.iso", path="/roms/a.iso")
        b = GameRom(name="rom.iso", path="/roms/b.iso")
        assert a != b


class TestLookupTables:
    def test_platform_fields(self):
        p = Platform(name="PC", specification_id="pc_windows")
        assert p.name == "PC"
        assert p.specification_id == "pc_windows"

    def test_genre_is_database_object(self):
        g = Genre(name="RPG")
        assert isinstance(g, DatabaseObject)

    def test_company_is_database_object(self):
        c = Company(name="Valve")
        assert isinstance(c, DatabaseObject)
