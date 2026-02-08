"""Unit tests for tags, categories, and smart collections."""
import pytest

from playnite.library.organisation import LibraryManager, NotFoundError


class TestTagCRUD:
    def test_add_and_list(self, manager):
        manager.add_tag("indie")
        tags = manager.list_tags()
        assert any(t["name"] == "indie" for t in tags)

    def test_add_idempotent(self, manager):
        manager.add_tag("dup")
        manager.add_tag("dup")
        assert len([t for t in manager.list_tags() if t["name"] == "dup"]) == 1

    def test_delete(self, manager):
        t = manager.add_tag("gone")
        manager.delete_tag(t["id"])
        assert not any(x["name"] == "gone" for x in manager.list_tags())

    def test_delete_missing_raises(self, manager):
        with pytest.raises(NotFoundError):
            manager.delete_tag("nope")

    def test_apply_and_remove_tag(self, manager):
        g = manager.add_game(name="Tagged")
        manager.apply_tag(g["id"], "cool")
        assert "cool" in manager.get_game(g["id"])["tags"]
        manager.remove_tag(g["id"], "cool")
        assert "cool" not in manager.get_game(g["id"])["tags"]


class TestCategoryCRUD:
    def test_add_list_delete(self, manager):
        c = manager.add_category("Action")
        assert c["name"] == "Action"
        assert any(x["name"] == "Action" for x in manager.list_categories())
        manager.delete_category(c["id"])
        assert not any(x["name"] == "Action" for x in manager.list_categories())


class TestSmartCollections:
    def test_create_and_list(self, manager):
        col = manager.create_smart_collection(
            "Favourites", rules=[{"field": "is_favorite", "operator": "is_true", "value": None}]
        )
        assert col["name"] == "Favourites"
        assert len(manager.list_smart_collections()) == 1

    def test_get_collection(self, manager):
        col = manager.create_smart_collection("Test", rules=[])
        fetched = manager.get_smart_collection(col["id"])
        assert fetched["id"] == col["id"]

    def test_update_collection(self, manager):
        col = manager.create_smart_collection("Old", rules=[])
        updated = manager.update_smart_collection(col["id"], name="New")
        assert updated["name"] == "New"

    def test_delete_collection(self, manager):
        col = manager.create_smart_collection("Temp", rules=[])
        manager.delete_smart_collection(col["id"])
        with pytest.raises(NotFoundError):
            manager.get_smart_collection(col["id"])

    def test_collection_games_AND_logic(self, populated):
        col = populated.create_smart_collection(
            "RPG 90+",
            rules=[
                {"field": "completion_status", "operator": "equals", "value": "completed"},
                {"field": "user_score", "operator": "gte", "value": 90},
            ],
            logic="AND",
        )
        games = populated.get_smart_collection_games(col["id"])
        assert len(games) == 2  # Witcher 3 (95) + Dark Souls (90), both completed

    def test_collection_games_OR_logic(self, populated):
        col = populated.create_smart_collection(
            "Puzzle or Sandbox",
            rules=[
                {"field": "genre_names", "operator": "contains", "value": "Puzzle"},
                {"field": "genre_names", "operator": "contains", "value": "Sandbox"},
            ],
            logic="OR",
        )
        games = populated.get_smart_collection_games(col["id"])
        names = {g["name"] for g in games}
        assert "Portal 2" in names
        assert "Minecraft" in names

    def test_collection_updates_dynamically(self, populated):
        col = populated.create_smart_collection(
            "High Score",
            rules=[{"field": "user_score", "operator": "gt", "value": 96}],
        )
        before = populated.get_smart_collection_games(col["id"])
        assert len(before) == 1  # Portal 2 (98)

        # Add another high-scorer
        populated.add_game(name="New Hit", user_score=99)
        after = populated.get_smart_collection_games(col["id"])
        assert len(after) == 2

    def test_collection_with_tag_rule(self, populated):
        col = populated.create_smart_collection(
            "Open World",
            rules=[{"field": "tag_names", "operator": "contains", "value": "open-world"}],
        )
        games = populated.get_smart_collection_games(col["id"])
        names = {g["name"] for g in games}
        assert "The Witcher 3" in names
        assert "Cyberpunk 2077" in names
