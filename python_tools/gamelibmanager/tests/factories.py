"""Test data factories for creating sample games and libraries."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from gamelibmanager.models.game import Game
from gamelibmanager.models.lookup_tables import (
    Category, Company, GameSource, Genre, Platform,
)
from gamelibmanager.models.release_date import ReleaseDate

# Fixed UUIDs for consistent testing
STEAM_SOURCE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
GOG_SOURCE_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
EPIC_SOURCE_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
STEAM_PLUGIN_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
GOG_PLUGIN_ID = uuid.UUID("10000000-0000-0000-0000-000000000002")

PC_PLATFORM_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")
PS5_PLATFORM_ID = uuid.UUID("20000000-0000-0000-0000-000000000002")

DEV_CDPR_ID = uuid.UUID("30000000-0000-0000-0000-000000000001")
PUB_CDPR_ID = uuid.UUID("30000000-0000-0000-0000-000000000002")
DEV_VALVE_ID = uuid.UUID("30000000-0000-0000-0000-000000000003")
DEV_FROMSOFT_ID = uuid.UUID("30000000-0000-0000-0000-000000000004")

GENRE_RPG_ID = uuid.UUID("40000000-0000-0000-0000-000000000001")
GENRE_ACTION_ID = uuid.UUID("40000000-0000-0000-0000-000000000002")

CAT_SINGLEPLAYER_ID = uuid.UUID("50000000-0000-0000-0000-000000000001")


def make_game(name: str = "Test Game", **overrides) -> Game:
    """Create a Game with sensible defaults. Any field can be overridden."""
    defaults = dict(
        id=uuid.uuid4(),
        name=name,
        game_id=str(uuid.uuid4()),
        source_id=STEAM_SOURCE_ID,
        platform_ids=[PC_PLATFORM_ID],
        is_installed=True,
        added=datetime(2024, 1, 1),
        modified=datetime(2024, 6, 1),
    )
    defaults.update(overrides)
    return Game(**defaults)


def make_lookup_tables(db) -> None:
    """Populate a GameDatabase with standard lookup tables."""
    db.add_lookup(GameSource(id=STEAM_SOURCE_ID, name="Steam"))
    db.add_lookup(GameSource(id=GOG_SOURCE_ID, name="GOG"))
    db.add_lookup(GameSource(id=EPIC_SOURCE_ID, name="Epic"))
    db.add_lookup(Platform(id=PC_PLATFORM_ID, name="PC"))
    db.add_lookup(Platform(id=PS5_PLATFORM_ID, name="PlayStation 5"))
    db.add_lookup(Company(id=DEV_CDPR_ID, name="CD Projekt Red"))
    db.add_lookup(Company(id=PUB_CDPR_ID, name="CD Projekt"))
    db.add_lookup(Company(id=DEV_VALVE_ID, name="Valve"))
    db.add_lookup(Company(id=DEV_FROMSOFT_ID, name="FromSoftware"))
    db.add_lookup(Genre(id=GENRE_RPG_ID, name="RPG"))
    db.add_lookup(Genre(id=GENRE_ACTION_ID, name="Action"))
    db.add_lookup(Category(id=CAT_SINGLEPLAYER_ID, name="Singleplayer"))


def make_witcher_steam() -> Game:
    return make_game(
        name="The Witcher 3: Wild Hunt",
        game_id="292030",
        plugin_id=STEAM_PLUGIN_ID,
        source_id=STEAM_SOURCE_ID,
        platform_ids=[PC_PLATFORM_ID],
        developer_ids=[DEV_CDPR_ID],
        publisher_ids=[PUB_CDPR_ID],
        genre_ids=[GENRE_RPG_ID, GENRE_ACTION_ID],
        release_date=ReleaseDate(2015, 5, 19),
        is_installed=True,
        description="An epic RPG",
        cover_image="witcher3_cover.jpg",
        critic_score=92,
        community_score=90,
        modified=datetime(2024, 6, 1),
    )


def make_witcher_gog() -> Game:
    return make_game(
        name="The Witcher 3 Wild Hunt",
        game_id="witcher3",
        plugin_id=GOG_PLUGIN_ID,
        source_id=GOG_SOURCE_ID,
        platform_ids=[PC_PLATFORM_ID],
        developer_ids=[DEV_CDPR_ID],
        release_date=ReleaseDate(2015, 5, 19),
        is_installed=False,
        modified=datetime(2024, 3, 1),
    )


def make_witcher_goty() -> Game:
    return make_game(
        name="The Witcher 3: Wild Hunt - Game of the Year Edition",
        game_id="witcher3goty",
        plugin_id=GOG_PLUGIN_ID,
        source_id=GOG_SOURCE_ID,
        platform_ids=[PC_PLATFORM_ID],
        developer_ids=[DEV_CDPR_ID],
        release_date=ReleaseDate(2016, 8, 30),
        is_installed=True,
        modified=datetime(2024, 5, 1),
    )


def make_elden_ring() -> Game:
    return make_game(
        name="ELDEN RING",
        game_id="1245620",
        plugin_id=STEAM_PLUGIN_ID,
        source_id=STEAM_SOURCE_ID,
        platform_ids=[PC_PLATFORM_ID],
        developer_ids=[DEV_FROMSOFT_ID],
        release_date=ReleaseDate(2022, 2, 25),
        is_installed=True,
        modified=datetime(2024, 5, 1),
    )


def make_half_life() -> Game:
    return make_game(
        name="Half-Life 2",
        game_id="220",
        plugin_id=STEAM_PLUGIN_ID,
        source_id=STEAM_SOURCE_ID,
        platform_ids=[PC_PLATFORM_ID],
        developer_ids=[DEV_VALVE_ID],
        release_date=ReleaseDate(2004, 11, 16),
        is_installed=True,
        modified=datetime(2024, 1, 1),
    )


def populate_test_library(db, num_games: int = 10) -> list[Game]:
    """Populate a database with a variety of test games."""
    make_lookup_tables(db)
    games = [
        make_witcher_steam(),
        make_witcher_gog(),
        make_witcher_goty(),
        make_elden_ring(),
        make_half_life(),
    ]
    # Add generic filler games
    for i in range(max(0, num_games - len(games))):
        games.append(make_game(
            name=f"Generic Game {i + 1}",
            source_id=STEAM_SOURCE_ID,
            modified=datetime(2024, 1, 1),
        ))
    db.add_games_batch(games)
    return games
