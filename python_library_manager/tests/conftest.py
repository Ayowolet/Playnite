"""
Shared pytest fixtures.

All test data is built programmatically so that tests remain self-contained
and run without an external Playnite installation.
"""
from __future__ import annotations

import uuid
import pytest

from game_library.models.game import Game, ReleaseDate
from game_library.models.library import Library, LibrarySource, NamedEntity


# ── Named-entity helpers ──────────────────────────────────────────────────────

def _entity(name: str) -> NamedEntity:
    return NamedEntity(Id=str(uuid.uuid4()), Name=name)


# ── Game factory ──────────────────────────────────────────────────────────────

def make_game(
    name: str,
    year: int | None = None,
    platforms: list[str] | None = None,
    developers: list[str] | None = None,
    publishers: list[str] | None = None,
    categories: list[str] | None = None,
    source: str = "Steam",
    installed: bool = False,
    hidden: bool = False,
    playtime: int = 0,
    cover: str = "",
    description: str = "",
) -> Game:
    """Return a fully-populated :class:`Game` fixture."""
    game = Game(
        Id=str(uuid.uuid4()),
        Name=name,
        IsInstalled=installed,
        Hidden=hidden,
        Playtime=playtime,
        CoverImage=cover,
        Description=description,
    )
    if year:
        game.ReleaseDate = ReleaseDate(Year=year)
    # resolved names (simulating Library.resolve_all)
    game._platform_names = platforms or []
    game._developer_names = developers or []
    game._publisher_names = publishers or []
    game._category_names = categories or []
    game._source_name = source
    return game


# ── Library factory ───────────────────────────────────────────────────────────

def make_library(name: str, games: list[Game], priority: int = 0) -> Library:
    """Return a :class:`Library` containing *games* with pre-populated entities."""
    lib = Library(source=LibrarySource(name=name, path=f"/fake/{name}", priority=priority))

    for game in games:
        # Create platform entities
        for pname in game._platform_names:
            pid = lib.get_or_create_platform(pname)
            if pid not in game.PlatformIds:
                game.PlatformIds.append(pid)
        # Create company entities
        for dname in game._developer_names:
            did = lib.get_or_create_company(dname)
            if did not in game.DeveloperIds:
                game.DeveloperIds.append(did)
        for pubname in game._publisher_names:
            pubid = lib.get_or_create_company(pubname)
            if pubid not in game.PublisherIds:
                game.PublisherIds.append(pubid)
        # Create category entities
        for catname in game._category_names:
            cid = lib.get_or_create_category(catname)
            if cid not in game.CategoryIds:
                game.CategoryIds.append(cid)
        # Create source entity
        if game._source_name:
            sid = lib.get_or_create_source(game._source_name)
            game.SourceId = sid
        lib.games[game.Id] = game

    return lib


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def witcher3_steam():
    return make_game(
        "The Witcher 3: Wild Hunt",
        year=2015,
        platforms=["PC"],
        developers=["CD Projekt Red"],
        publishers=["CD Projekt"],
        source="Steam",
        installed=True,
        playtime=7200,
        cover="cover_steam.jpg",
        description="Open world RPG.",
    )


@pytest.fixture
def witcher3_gog():
    return make_game(
        "The Witcher 3: Wild Hunt",
        year=2015,
        platforms=["PC"],
        developers=["CD Projekt RED"],
        publishers=["CD Projekt"],
        source="GOG",
        installed=False,
        playtime=3600,
        cover="cover_gog.jpg",
    )


@pytest.fixture
def witcher3_goty():
    """GOTY edition – should match after edition stripping."""
    return make_game(
        "The Witcher 3: Wild Hunt – Game of the Year Edition",
        year=2016,
        platforms=["PC"],
        developers=["CD Projekt Red"],
        source="Steam",
    )


@pytest.fixture
def portal2():
    return make_game(
        "Portal 2",
        year=2011,
        platforms=["PC"],
        developers=["Valve"],
        publishers=["Valve"],
        source="Steam",
        installed=True,
        playtime=1800,
    )


@pytest.fixture
def portal2_gog():
    return make_game(
        "Portal 2",
        year=2011,
        platforms=["PC"],
        developers=["Valve Corporation"],
        source="GOG",
    )


@pytest.fixture
def unrelated_game():
    return make_game(
        "Cyberpunk 2077",
        year=2020,
        platforms=["PC"],
        developers=["CD Projekt Red"],
        source="GOG",
    )


@pytest.fixture
def master_library(witcher3_steam, portal2, unrelated_game):
    return make_library("master", [witcher3_steam, portal2, unrelated_game], priority=0)


@pytest.fixture
def source_library(witcher3_gog, portal2_gog):
    return make_library("source", [witcher3_gog, portal2_gog], priority=1)
