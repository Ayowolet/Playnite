"""Unit tests for database operations."""

import pytest
from datetime import datetime, date

from playnite_py.database import DatabaseEngine, GameOperations, LibraryOperations
from playnite_py.models import Game, Platform, Genre, Tag, Category


@pytest.fixture
def db_engine():
    """Create in-memory database for testing."""
    engine = DatabaseEngine(db_path=None)  # In-memory
    engine.create_tables()
    return engine


@pytest.fixture
def session(db_engine):
    """Create database session."""
    return db_engine.get_session()


@pytest.fixture
def game_ops(session):
    """Create GameOperations instance."""
    return GameOperations(session)


@pytest.fixture
def lib_ops(session):
    """Create LibraryOperations instance."""
    return LibraryOperations(session)


class TestGameOperations:
    """Test game CRUD operations."""

    def test_create_game(self, game_ops):
        """Test creating a game."""
        game = game_ops.create_game("Test Game")
        assert game.id is not None
        assert game.name == "Test Game"

    def test_get_game(self, game_ops):
        """Test retrieving a game."""
        game = game_ops.create_game("Test Game")
        retrieved = game_ops.get_game(game.id)
        assert retrieved is not None
        assert retrieved.name == "Test Game"

    def test_get_game_by_name(self, game_ops):
        """Test retrieving game by name."""
        game_ops.create_game("Test Game")
        retrieved = game_ops.get_game_by_name("Test Game")
        assert retrieved is not None
        assert retrieved.name == "Test Game"

    def test_update_game(self, game_ops):
        """Test updating a game."""
        game = game_ops.create_game("Test Game")
        updated = game_ops.update_game(game.id, playtime=100, is_favorite=True)
        assert updated.playtime == 100
        assert updated.is_favorite is True

    def test_delete_game(self, game_ops):
        """Test deleting a game."""
        game = game_ops.create_game("Test Game")
        result = game_ops.delete_game(game.id)
        assert result is True
        assert game_ops.get_game(game.id) is None

    def test_add_platform_to_game(self, game_ops):
        """Test adding platform to game."""
        game = game_ops.create_game("Test Game")
        result = game_ops.add_platform_to_game(game.id, "PC")
        assert result is True

        retrieved = game_ops.get_game(game.id)
        assert len(retrieved.platforms) == 1
        assert retrieved.platforms[0].name == "PC"

    def test_add_genre_to_game(self, game_ops):
        """Test adding genre to game."""
        game = game_ops.create_game("Test Game")
        result = game_ops.add_genre_to_game(game.id, "RPG")
        assert result is True

        retrieved = game_ops.get_game(game.id)
        assert len(retrieved.genres) == 1
        assert retrieved.genres[0].name == "RPG"

    def test_add_tag_to_game(self, game_ops):
        """Test adding tag to game."""
        game = game_ops.create_game("Test Game")
        result = game_ops.add_tag_to_game(game.id, "multiplayer")
        assert result is True

        retrieved = game_ops.get_game(game.id)
        assert len(retrieved.tags) == 1
        assert retrieved.tags[0].name == "multiplayer"

    def test_toggle_favorite(self, game_ops):
        """Test toggling favorite status."""
        game = game_ops.create_game("Test Game")
        result = game_ops.toggle_favorite(game.id)
        assert result is True

        result = game_ops.toggle_favorite(game.id)
        assert result is False

    def test_bulk_update(self, game_ops):
        """Test bulk update."""
        game1 = game_ops.create_game("Game 1")
        game2 = game_ops.create_game("Game 2")
        game3 = game_ops.create_game("Game 3")

        count = game_ops.bulk_update([game1.id, game2.id, game3.id], {'is_favorite': True})
        assert count == 3

        for game_id in [game1.id, game2.id, game3.id]:
            game = game_ops.get_game(game_id)
            assert game.is_favorite is True

    def test_bulk_add_tags(self, game_ops):
        """Test bulk adding tags."""
        game1 = game_ops.create_game("Game 1")
        game2 = game_ops.create_game("Game 2")

        count = game_ops.bulk_add_tags([game1.id, game2.id], ["action", "adventure"])
        assert count == 2

        game1_retrieved = game_ops.get_game(game1.id)
        assert len(game1_retrieved.tags) == 2


class TestLibraryOperations:
    """Test library metadata operations."""

    def test_create_platform(self, lib_ops):
        """Test creating a platform."""
        platform = lib_ops.create_platform("PC")
        assert platform.name == "PC"

    def test_get_all_platforms(self, lib_ops):
        """Test getting all platforms."""
        lib_ops.create_platform("PC")
        lib_ops.create_platform("PS5")
        platforms = lib_ops.get_all_platforms()
        assert len(platforms) == 2

    def test_create_tag(self, lib_ops):
        """Test creating a tag."""
        tag = lib_ops.create_tag("multiplayer")
        assert tag.name == "multiplayer"

    def test_delete_tag(self, lib_ops):
        """Test deleting a tag."""
        tag = lib_ops.create_tag("test_tag")
        result = lib_ops.delete_tag(tag.id)
        assert result is True

    def test_create_category(self, lib_ops):
        """Test creating a category."""
        category = lib_ops.create_category("Favorites", "My favorite games")
        assert category.name == "Favorites"
        assert category.description == "My favorite games"

    def test_create_collection(self, lib_ops):
        """Test creating a collection."""
        collection = lib_ops.create_collection("RPG Games", "All RPG games")
        assert collection.name == "RPG Games"
        assert collection.is_smart is False

    def test_create_smart_collection(self, lib_ops):
        """Test creating a smart collection."""
        rules = {"genres": ["RPG"], "playtime_min": 600}
        collection = lib_ops.create_collection("Long RPGs", is_smart=True, rules=rules)
        assert collection.is_smart is True
        assert collection.get_rules() == rules
