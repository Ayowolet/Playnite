"""Tests for GameDatabase."""

import sqlite3
import uuid
from datetime import datetime

import pytest
from gamelibmanager.db.concurrency import DatabaseLockedError
from gamelibmanager.db.database import GameDatabase
from gamelibmanager.models.game import Game
from gamelibmanager.models.release_date import ReleaseDate
from gamelibmanager.models.lookup_tables import Platform, Genre, Company, GameSource
from gamelibmanager.models.link import Link
from tests.factories import make_game, make_lookup_tables


class TestGameDatabase:
    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        self.db_path = tmp_path / "test.db"
        self.db = GameDatabase(str(self.db_path))
        self.db.open()
        yield
        self.db.close()

    def test_open_creates_tables(self):
        # Tables should exist after open
        row = self.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='games'"
        ).fetchone()
        assert row is not None

    def test_add_and_get_game(self):
        game = make_game(name="DOOM")
        self.db.add_game(game)
        retrieved = self.db.get_game(game.id)
        assert retrieved is not None
        assert retrieved.name == "DOOM"
        assert retrieved.id == game.id

    def test_add_games_batch(self):
        games = [make_game(name=f"Game {i}") for i in range(10)]
        self.db.add_games_batch(games)
        assert self.db.game_count() == 10

    def test_update_game(self):
        game = make_game(name="Before")
        self.db.add_game(game)
        game.name = "After"
        game.hidden = True
        self.db.update_game(game)
        retrieved = self.db.get_game(game.id)
        assert retrieved.name == "After"
        assert retrieved.hidden is True

    def test_delete_game(self):
        game = make_game(name="ToDelete")
        self.db.add_game(game)
        assert self.db.game_count() == 1
        self.db.delete_game(game.id)
        assert self.db.game_count() == 0

    def test_get_all_games(self):
        games = [make_game(name=f"G{i}") for i in range(5)]
        self.db.add_games_batch(games)
        all_games = self.db.get_all_games()
        assert len(all_games) == 5

    def test_game_round_trip_all_fields(self):
        game = Game(
            name="Full Game",
            game_id="steam_123",
            plugin_id=uuid.uuid4(),
            description="A description",
            notes="Some notes",
            hidden=True,
            favorite=True,
            is_installed=True,
            platform_ids=[uuid.uuid4(), uuid.uuid4()],
            developer_ids=[uuid.uuid4()],
            publisher_ids=[uuid.uuid4()],
            genre_ids=[uuid.uuid4()],
            release_date=ReleaseDate(2020, 6, 15),
            last_activity=datetime(2024, 1, 1, 12, 0),
            added=datetime(2023, 1, 1),
            modified=datetime(2024, 6, 1),
            playtime=7200,
            play_count=5,
            user_score=85,
            critic_score=92,
            community_score=88,
            icon="icon.png",
            cover_image="cover.jpg",
            background_image="bg.png",
            install_directory="/games/full",
            version="1.2.3",
            links=[Link(name="Store", url="https://store.example.com")],
        )
        self.db.add_game(game)
        retrieved = self.db.get_game(game.id)

        assert retrieved.name == "Full Game"
        assert retrieved.game_id == "steam_123"
        assert retrieved.plugin_id == game.plugin_id
        assert retrieved.description == "A description"
        assert retrieved.hidden is True
        assert retrieved.favorite is True
        assert retrieved.is_installed is True
        assert len(retrieved.platform_ids) == 2
        assert retrieved.release_date == ReleaseDate(2020, 6, 15)
        assert retrieved.playtime == 7200
        assert retrieved.user_score == 85
        assert retrieved.icon == "icon.png"
        assert len(retrieved.links) == 1
        assert retrieved.links[0].url == "https://store.example.com"

    def test_game_with_none_fields(self):
        game = Game(name="Minimal")
        self.db.add_game(game)
        retrieved = self.db.get_game(game.id)
        assert retrieved.name == "Minimal"
        assert retrieved.platform_ids is None
        assert retrieved.release_date is None
        assert retrieved.user_score is None

    def test_lookup_crud(self):
        make_lookup_tables(self.db)
        platform = self.db.get_lookup(Platform, uuid.UUID("20000000-0000-0000-0000-000000000001"))
        assert platform is not None
        assert platform.name == "PC"

    def test_find_lookup_by_name(self):
        make_lookup_tables(self.db)
        source = self.db.find_lookup_by_name(GameSource, "Steam")
        assert source is not None
        assert source.name == "Steam"

    def test_find_lookup_by_name_not_found(self):
        make_lookup_tables(self.db)
        source = self.db.find_lookup_by_name(GameSource, "NonExistent")
        assert source is None

    def test_get_games_by_ids(self):
        g1 = make_game(name="A")
        g2 = make_game(name="B")
        g3 = make_game(name="C")
        self.db.add_games_batch([g1, g2, g3])
        results = self.db.get_games_by_ids([g1.id, g3.id])
        names = {g.name for g in results}
        assert names == {"A", "C"}

    def test_savepoint_and_rollback(self):
        g1 = make_game(name="Keep")
        self.db.add_game(g1)
        self.db.savepoint("test_sp")
        g2 = make_game(name="Discard")
        self.db.add_game(g2)
        assert self.db.game_count() == 2
        self.db.rollback_to_savepoint("test_sp")
        assert self.db.game_count() == 1
        remaining = self.db.get_all_games()
        assert remaining[0].name == "Keep"

    def test_context_manager(self, tmp_path):
        db_path = tmp_path / "ctx.db"
        with GameDatabase(str(db_path)) as db:
            db.add_game(make_game(name="Ctx"))
            assert db.game_count() == 1

    # ------------------------------------------------------------------ #
    # Concurrent-access helpers
    # ------------------------------------------------------------------ #

    def test_open_sets_busy_timeout(self):
        row = self.db.conn.execute("PRAGMA busy_timeout").fetchone()
        assert row[0] == 30000

    def test_open_custom_busy_timeout(self, tmp_path):
        db = GameDatabase(str(tmp_path / "custom.db"))
        db.open(busy_timeout_ms=5000)
        row = db.conn.execute("PRAGMA busy_timeout").fetchone()
        assert row[0] == 5000
        db.close()

    def test_check_write_access_succeeds_when_unlocked(self):
        self.db.check_write_access(timeout_ms=500)

    def test_check_write_access_raises_when_locked(self):
        blocker = sqlite3.connect(str(self.db_path))
        blocker.execute("BEGIN EXCLUSIVE")
        try:
            with pytest.raises(DatabaseLockedError):
                self.db.check_write_access(timeout_ms=100)
        finally:
            blocker.rollback()
            blocker.close()

    def test_sqlite_backup_creates_consistent_copy(self, tmp_path):
        self.db.add_game(make_game(name="Backup Test"))

        dest = tmp_path / "backup.db"
        self.db.sqlite_backup(str(dest))

        verify = sqlite3.connect(str(dest))
        verify.row_factory = sqlite3.Row
        integrity = verify.execute("PRAGMA integrity_check").fetchone()
        assert integrity[0] == "ok"
        count = verify.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        assert count == 1
        verify.close()

    def test_rebuild_normalized_names(self):
        """rebuild_normalized_names re-computes cached _normalized_name."""
        game = make_game(name="Pokémon X")
        self.db.add_game(game)
        # Simulate stale cached value from old normalizer
        self.db.conn.execute(
            "UPDATE games SET _normalized_name = ? WHERE id = ?",
            ("pokemon 10", str(game.id)),
        )
        count = self.db.rebuild_normalized_names()
        assert count >= 1
        row = self.db.conn.execute(
            "SELECT _normalized_name FROM games WHERE id = ?",
            (str(game.id),),
        ).fetchone()
        assert row["_normalized_name"] == "pokemon x"
