"""Shared pytest fixtures."""
from datetime import datetime

import pytest

from playnite.library.organisation import LibraryManager

_FROZEN_DT = datetime(2024, 6, 15, 12, 0, 0)


@pytest.fixture
def frozen_clock():
    """Return a callable that always returns a fixed datetime for deterministic tests."""
    return lambda: _FROZEN_DT


@pytest.fixture
def manager():
    """Fresh in-memory library for each test."""
    return LibraryManager("sqlite:///:memory:")


@pytest.fixture
def make_game(manager):
    """Factory fixture: add a game to the default manager."""
    def _factory(name: str = "Test Game", **kwargs) -> dict:
        return manager.add_game(name=name, **kwargs)
    return _factory


@pytest.fixture
def make_tag(manager):
    """Factory fixture: add a tag to the default manager."""
    def _factory(name: str = "test-tag") -> dict:
        return manager.add_tag(name)
    return _factory


@pytest.fixture
def populated(manager):
    """Library pre-loaded with 5 diverse games."""
    manager.add_game(
        name="The Witcher 3",
        developer="CD Projekt Red",
        publisher="CD Projekt",
        release_year=2015,
        genres=["RPG", "Action"],
        platforms=["PC", "PS4"],
        tags=["open-world", "fantasy"],
        playtime=7200,
        user_score=95,
        completion_status="completed",
    )
    manager.add_game(
        name="Dark Souls",
        developer="FromSoftware",
        publisher="Bandai Namco",
        release_year=2011,
        genres=["RPG", "Action"],
        platforms=["PC", "PS3"],
        tags=["challenging", "fantasy"],
        playtime=3600,
        user_score=90,
        completion_status="completed",
    )
    manager.add_game(
        name="Minecraft",
        developer="Mojang",
        publisher="Microsoft",
        release_year=2011,
        genres=["Sandbox"],
        platforms=["PC", "Xbox"],
        tags=["building", "multiplayer"],
        playtime=18000,
        user_score=88,
    )
    manager.add_game(
        name="Cyberpunk 2077",
        developer="CD Projekt Red",
        publisher="CD Projekt",
        release_year=2020,
        genres=["RPG", "Action"],
        platforms=["PC", "PS5"],
        tags=["cyberpunk", "open-world"],
        playtime=1800,
        user_score=75,
    )
    manager.add_game(
        name="Portal 2",
        developer="Valve",
        publisher="Valve",
        release_year=2011,
        genres=["Puzzle"],
        platforms=["PC"],
        tags=["puzzle", "co-op"],
        playtime=600,
        user_score=98,
    )
    return manager
