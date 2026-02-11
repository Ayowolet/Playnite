"""Shared pytest fixtures."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

import pytest

from gamelibmanager.db.database import GameDatabase
from gamelibmanager.models.game import Game
from gamelibmanager.models.release_date import ReleaseDate
from tests.factories import make_lookup_tables, populate_test_library


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary GameDatabase."""
    db_path = tmp_path / "test.db"
    db = GameDatabase(str(db_path))
    db.open()
    yield db
    db.close()


@pytest.fixture
def populated_db(tmp_db):
    """A GameDatabase populated with test games."""
    populate_test_library(tmp_db)
    return tmp_db


@pytest.fixture
def tmp_playnite_lib(tmp_path):
    """Create a temporary Playnite-format library directory."""
    lib_path = tmp_path / "library"
    for subdir in ["games", "platforms", "sources", "companies", "genres", "files"]:
        (lib_path / subdir).mkdir(parents=True)

    # Write a sample game JSON
    game_id = str(uuid.uuid4())
    game_data = {
        "Id": game_id,
        "Name": "Test Game Alpha",
        "GameId": "12345",
        "Hidden": False,
        "Favorite": False,
        "IsInstalled": True,
        "Playtime": 3600,
        "ReleaseDate": "2020-6-15",
    }
    with open(lib_path / "games" / f"{game_id}.json", "w") as f:
        json.dump(game_data, f)

    # Write a source
    source_id = str(uuid.uuid4())
    with open(lib_path / "sources" / f"{source_id}.json", "w") as f:
        json.dump({"Id": source_id, "Name": "Steam"}, f)

    # Write a platform
    plat_id = str(uuid.uuid4())
    with open(lib_path / "platforms" / f"{plat_id}.json", "w") as f:
        json.dump({"Id": plat_id, "Name": "PC", "SpecificationId": "pc_windows"}, f)

    return lib_path
