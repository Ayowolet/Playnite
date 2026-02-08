"""Unit tests for organisation features."""

import pytest
from datetime import date

from playnite_py.database import DatabaseEngine, GameOperations
from playnite_py.organisation import GameFilter, GameSearch, SmartCollectionManager, BulkOperations


@pytest.fixture
def db_engine():
    """Create in-memory database."""
    engine = DatabaseEngine(db_path=None)
    engine.create_tables()
    return engine


@pytest.fixture
def session(db_engine):
    """Create database session."""
    return db_engine.get_session()


@pytest.fixture
def sample_games(session):
    """Create sample games for testing."""
    ops = GameOperations(session)

    games = []

    # Create diverse set of games
    game1 = ops.create_game("The Witcher 3", playtime=2400, is_favorite=True,
                             release_date=date(2015, 5, 19))
    ops.add_platform_to_game(game1.id, "PC")
    ops.add_genre_to_game(game1.id, "RPG")
    ops.add_tag_to_game(game1.id, "open-world")
    games.append(game1)

    game2 = ops.create_game("Dark Souls", playtime=1200,
                             release_date=date(2011, 9, 22))
    ops.add_platform_to_game(game2.id, "PC")
    ops.add_genre_to_game(game2.id, "RPG")
    ops.add_tag_to_game(game2.id, "challenging")
    games.append(game2)

    game3 = ops.create_game("Portal 2", playtime=600, is_favorite=True,
                             release_date=date(2011, 4, 19))
    ops.add_platform_to_game(game3.id, "PC")
    ops.add_genre_to_game(game3.id, "Puzzle")
    games.append(game3)

    game4 = ops.create_game("Bloodborne", playtime=1800,
                             release_date=date(2015, 3, 24))
    ops.add_platform_to_game(game4.id, "PS4")
    ops.add_genre_to_game(game4.id, "Action")
    ops.add_tag_to_game(game4.id, "challenging")
    games.append(game4)

    game5 = ops.create_game("Celeste", playtime=300,
                             release_date=date(2018, 1, 25))
    ops.add_platform_to_game(game5.id, "PC")
    ops.add_genre_to_game(game5.id, "Platformer")
    games.append(game5)

    return games


class TestGameFilter:
    """Test game filtering."""

    def test_filter_by_platform(self, session, sample_games):
        """Test filtering by platform."""
        game_filter = GameFilter(session)
        results = game_filter.filter_games({'platforms': ['PC']})
        assert len(results) == 4  # Witcher 3, Dark Souls, Portal 2, Celeste

    def test_filter_by_genre(self, session, sample_games):
        """Test filtering by genre."""
        game_filter = GameFilter(session)
        results = game_filter.filter_games({'genres': ['RPG']})
        assert len(results) == 2  # Witcher 3, Dark Souls

    def test_filter_by_multiple_genres(self, session, sample_games):
        """Test filtering by multiple genres."""
        game_filter = GameFilter(session)
        results = game_filter.filter_games({'genres': ['RPG', 'Puzzle']})
        assert len(results) == 3  # Witcher 3, Dark Souls, Portal 2

    def test_filter_by_tag(self, session, sample_games):
        """Test filtering by tag."""
        game_filter = GameFilter(session)
        results = game_filter.filter_games({'tags': ['challenging']})
        assert len(results) == 2  # Dark Souls, Bloodborne

    def test_filter_by_favorite(self, session, sample_games):
        """Test filtering favorites."""
        game_filter = GameFilter(session)
        results = game_filter.filter_games({'is_favorite': True})
        assert len(results) == 2  # Witcher 3, Portal 2

    def test_filter_by_playtime(self, session, sample_games):
        """Test filtering by playtime."""
        game_filter = GameFilter(session)
        results = game_filter.filter_games({'playtime_min': 1000})
        assert len(results) == 3  # Witcher 3, Dark Souls, Bloodborne

    def test_filter_by_release_year(self, session, sample_games):
        """Test filtering by release year."""
        game_filter = GameFilter(session)
        results = game_filter.filter_games({'release_year_min': 2015})
        assert len(results) == 3  # Witcher 3 (2015), Bloodborne (2015), Celeste (2018)

    def test_combined_filters(self, session, sample_games):
        """Test combining multiple filters."""
        game_filter = GameFilter(session)
        results = game_filter.filter_games({
            'platforms': ['PC'],
            'genres': ['RPG'],
            'playtime_min': 1000
        })
        assert len(results) == 2  # Witcher 3, Dark Souls

    def test_sorting(self, session, sample_games):
        """Test sorting results."""
        game_filter = GameFilter(session)
        results = game_filter.filter_games({}, sort_by='playtime', sort_desc=True)
        assert results[0].name == "The Witcher 3"  # Highest playtime

    def test_pagination(self, session, sample_games):
        """Test pagination."""
        game_filter = GameFilter(session)
        results = game_filter.filter_games({}, limit=2, offset=0, sort_by='name')
        assert len(results) == 2

        results_page2 = game_filter.filter_games({}, limit=2, offset=2, sort_by='name')
        assert len(results_page2) == 2


class TestGameSearch:
    """Test game search functionality."""

    def test_search_by_name(self, session, sample_games):
        """Test searching by game name."""
        search = GameSearch(session)
        results = search.search("Witcher")
        assert len(results) > 0
        assert results[0][0].name == "The Witcher 3"

    def test_fuzzy_search(self, session, sample_games):
        """Test fuzzy matching."""
        search = GameSearch(session)
        # Test fuzzy scoring on substring matches
        results = search.search("Witch", fuzzy=True)  # Partial match
        assert len(results) > 0  # Should find Witcher
        assert results[0][0].name == "The Witcher 3"

    def test_exact_search(self, session, sample_games):
        """Test exact matching."""
        search = GameSearch(session)
        results = search.search("Dark", fuzzy=False)
        assert len(results) == 1
        assert "Dark" in results[0][0].name

    def test_search_limit(self, session, sample_games):
        """Test search result limiting."""
        search = GameSearch(session)
        results = search.search("e", limit=2)  # Many games have 'e'
        assert len(results) <= 2

    def test_search_by_tag(self, session, sample_games):
        """Test searching by tag."""
        search = GameSearch(session)
        results = search.search_by_tag("challenging")
        assert len(results) == 2


class TestSmartCollectionManager:
    """Test smart collections."""

    def test_create_smart_collection(self, session, sample_games):
        """Test creating smart collection."""
        manager = SmartCollectionManager(session)
        collection = manager.create_smart_collection(
            "PC RPGs",
            {'platforms': ['PC'], 'genres': ['RPG']}
        )
        assert collection.is_smart is True
        assert len(collection.games) == 2  # Witcher 3, Dark Souls

    def test_update_smart_collection(self, session, sample_games):
        """Test updating smart collection."""
        manager = SmartCollectionManager(session)
        collection = manager.create_smart_collection(
            "Favorites",
            {'is_favorite': True}
        )
        initial_count = len(collection.games)

        # Add more favorites
        ops = GameOperations(session)
        game = sample_games[1]  # Dark Souls
        ops.toggle_favorite(game.id)

        # Update collection
        count = manager.update_smart_collection(collection.id)
        assert count > initial_count

    def test_collection_rules(self, session, sample_games):
        """Test collection rule storage."""
        manager = SmartCollectionManager(session)
        rules = {'playtime_min': 1000, 'genres': ['RPG']}
        collection = manager.create_smart_collection("Long RPGs", rules)

        retrieved_rules = collection.get_rules()
        assert retrieved_rules == rules

    def test_modify_collection_rules(self, session, sample_games):
        """Test modifying collection rules."""
        manager = SmartCollectionManager(session)
        collection = manager.create_smart_collection(
            "Test Collection",
            {'platforms': ['PC']}
        )
        initial_count = len(collection.games)

        # Modify rules to be more restrictive
        new_rules = {'platforms': ['PC'], 'genres': ['RPG']}
        count = manager.modify_smart_collection_rules(collection.id, new_rules)
        assert count <= initial_count

    def test_collection_preview(self, session, sample_games):
        """Test previewing smart collection."""
        manager = SmartCollectionManager(session)
        rules = {'is_favorite': True}
        preview = manager.get_smart_collection_preview(rules)
        assert len(preview) == 2  # 2 favorites


class TestBulkOperations:
    """Test bulk operations."""

    def test_bulk_add_tags(self, session, sample_games):
        """Test bulk adding tags."""
        bulk_ops = BulkOperations(session)
        game_ids = [g.id for g in sample_games[:3]]
        count = bulk_ops.bulk_add_tags(game_ids, ["test_tag", "bulk_test"])
        assert count == 3

        ops = GameOperations(session)
        for game_id in game_ids:
            game = ops.get_game(game_id)
            tag_names = [t.name for t in game.tags]
            assert "test_tag" in tag_names

    def test_bulk_remove_tags(self, session, sample_games):
        """Test bulk removing tags."""
        bulk_ops = BulkOperations(session)
        game_ids = [g.id for g in sample_games if len(g.tags) > 0]
        if game_ids:
            tag_name = sample_games[0].tags[0].name if sample_games[0].tags else "challenging"
            count = bulk_ops.bulk_remove_tags(game_ids, [tag_name])
            assert count > 0

    def test_bulk_set_favorite(self, session, sample_games):
        """Test bulk setting favorites."""
        bulk_ops = BulkOperations(session)
        game_ids = [g.id for g in sample_games[:2]]
        count = bulk_ops.bulk_set_favorite(game_ids, True)
        assert count == 2

        ops = GameOperations(session)
        for game_id in game_ids:
            game = ops.get_game(game_id)
            assert game.is_favorite is True

    def test_bulk_set_hidden(self, session, sample_games):
        """Test bulk hiding games."""
        bulk_ops = BulkOperations(session)
        game_ids = [g.id for g in sample_games[:2]]
        count = bulk_ops.bulk_set_hidden(game_ids, True)
        assert count == 2

    def test_bulk_delete(self, session, sample_games):
        """Test bulk deleting games."""
        bulk_ops = BulkOperations(session)
        game_ids = [sample_games[0].id, sample_games[1].id]
        count = bulk_ops.bulk_delete(game_ids)
        assert count == 2

        ops = GameOperations(session)
        assert ops.get_game(game_ids[0]) is None
        assert ops.get_game(game_ids[1]) is None


class TestAutomaticSmartCollections:
    """Test automatic smart collection updates."""

    def test_smart_collection_batch_methods(self, session, sample_games):
        """Test batch update methods."""
        manager = SmartCollectionManager(session)

        # Create two smart collections
        collection1 = manager.create_smart_collection("RPGs", {'genres': ['RPG']})
        collection2 = manager.create_smart_collection("Favorites", {'is_favorite': True})

        initial_count1 = len(collection1.games)
        initial_count2 = len(collection2.games)

        # Batch update
        results = manager.update_collections_batch([collection1.id, collection2.id])

        assert collection1.id in results
        assert collection2.id in results
        assert results[collection1.id] == initial_count1
        assert results[collection2.id] == initial_count2

    def test_get_collections_with_rule_type(self, session, sample_games):
        """Test getting collections by rule type."""
        manager = SmartCollectionManager(session)

        # Create collections with different rule types
        collection1 = manager.create_smart_collection("RPGs", {'genres': ['RPG']})
        collection2 = manager.create_smart_collection("PC Games", {'platforms': ['PC']})
        collection3 = manager.create_smart_collection("Long Games", {'playtime_min': 1000})

        # Get collections with genre rules
        genre_collections = manager.get_collections_with_rule_type('genres')
        assert len(genre_collections) == 1
        assert genre_collections[0].id == collection1.id

        # Get collections with platform rules
        platform_collections = manager.get_collections_with_rule_type('platforms')
        assert len(platform_collections) == 1
        assert platform_collections[0].id == collection2.id

    def test_event_handler_init(self, session):
        """Test that event handler can be initialized."""
        from playnite_py.database.events import SmartCollectionEventHandler

        handler = SmartCollectionEventHandler(session, enabled=True)
        assert handler.enabled is True
        assert handler.session == session
        assert handler.update_queue is not None

    def test_update_queue(self):
        """Test smart collection update queue."""
        from playnite_py.database.events import SmartCollectionUpdateQueue

        queue = SmartCollectionUpdateQueue()
        queue.add(1)
        queue.add(2)
        queue.add(1)  # Duplicate

        queued = queue.get_and_clear()
        assert len(queued) == 2  # Should have 1 and 2 (set removes duplicates)
        assert 1 in queued
        assert 2 in queued

        # Queue should be empty after get_and_clear
        queued2 = queue.get_and_clear()
        assert len(queued2) == 0

