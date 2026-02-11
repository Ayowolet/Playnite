"""
Unit tests for GameDatabase — resolve_names and context-manager behaviour.
"""
from __future__ import annotations

import pytest

from playnite_python.database.game_database import GameDatabase
from playnite_python.models.game import Game, Platform, Genre, Tag


@pytest.fixture
def db():
    database = GameDatabase(":memory:")
    database.open()
    yield database
    database.close()


# ---------------------------------------------------------------------------
# resolve_names
# ---------------------------------------------------------------------------

class TestResolveNames:
    def test_all_missing_ids_return_empty_lists(self, db):
        """IDs not present in any collection are silently omitted."""
        game = Game(
            name="Ghost Game",
            platform_ids=["nonexistent-platform"],
            genre_ids=["nonexistent-genre"],
            tag_ids=["nonexistent-tag"],
        )
        result = db.resolve_names(game)
        assert result["platforms"] == []
        assert result["genres"] == []
        assert result["tags"] == []

    def test_partial_ids_resolves_present_ones(self, db):
        """Present IDs resolve to names; missing IDs are dropped silently."""
        p = Platform(name="Steam")
        db.platforms.add(p)
        game = Game(name="Mixed", platform_ids=[p.id, "ghost-id"])
        result = db.resolve_names(game)
        assert result["platforms"] == ["Steam"]

    def test_all_eight_keys_always_present(self, db):
        """All eight keys are returned even for a game with no IDs."""
        game = Game(name="Empty")
        result = db.resolve_names(game)
        assert set(result.keys()) == {
            "platforms", "genres", "developers", "publishers",
            "tags", "categories", "features", "series",
        }

    def test_resolved_names_match_collection(self, db):
        """Names in the result match what was stored in the collection."""
        g = Genre(name="Action")
        db.genres.add(g)
        t = Tag(name="Co-op")
        db.tags.add(t)
        game = Game(name="Fighter", genre_ids=[g.id], tag_ids=[t.id])
        result = db.resolve_names(game)
        assert result["genres"] == ["Action"]
        assert result["tags"] == ["Co-op"]


# ---------------------------------------------------------------------------
# Context manager / double-init guard
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_enter_on_already_open_db_does_not_reinitialise(self):
        """Calling __enter__ on an already-open DB must be a no-op."""
        db = GameDatabase(":memory:")
        db.open()
        conn_before = db._conn
        db.__enter__()
        assert db._conn is conn_before
        db.close()

    def test_context_manager_opens_and_closes(self):
        """with-block opens a closed DB and closes it on exit."""
        db = GameDatabase(":memory:")
        assert not db.is_open()
        with db:
            assert db.is_open()
        assert not db.is_open()

    def test_nested_context_manager_safe(self):
        """Nesting with-blocks does not close the DB until the outermost block exits."""
        db = GameDatabase(":memory:")
        with db as outer:
            conn_outer = outer._conn
            with db as inner:
                assert inner._conn is conn_outer  # same connection, no re-init
            # inner __exit__ decrements depth; connection must still be open
            assert db.is_open()
        # Only after the outermost __exit__ should the DB be closed
        assert not db.is_open()
