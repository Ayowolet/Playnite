"""Unit tests for game CRUD, favourites, hiding, and bulk ops."""
import time

import pytest

from playnite.library.organisation import LibraryManager, NotFoundError


class TestGameCRUD:
    def test_add_returns_dict(self, manager):
        g = manager.add_game(name="Test Game")
        assert g["name"] == "Test Game"
        assert "id" in g

    def test_add_with_relationships(self, manager):
        g = manager.add_game(
            name="RPG",
            genres=["RPG", "Action"],
            platforms=["PC"],
            tags=["indie"],
            categories=["Backlog"],
        )
        assert set(g["genres"]) == {"RPG", "Action"}
        assert g["platforms"] == ["PC"]
        assert g["tags"] == ["indie"]
        assert g["categories"] == ["Backlog"]

    def test_get_existing(self, manager):
        added = manager.add_game(name="X")
        fetched = manager.get_game(added["id"])
        assert fetched["id"] == added["id"]

    def test_get_missing_raises(self, manager):
        with pytest.raises(NotFoundError):
            manager.get_game("nonexistent-id")

    def test_update_scalar(self, manager):
        g = manager.add_game(name="Old")
        updated = manager.update_game(g["id"], name="New", user_score=80)
        assert updated["name"] == "New"
        assert updated["user_score"] == 80

    def test_update_missing_raises(self, manager):
        with pytest.raises(NotFoundError):
            manager.update_game("nope", name="X")

    def test_delete(self, manager):
        g = manager.add_game(name="Del")
        manager.delete_game(g["id"])
        with pytest.raises(NotFoundError):
            manager.get_game(g["id"])

    def test_delete_missing_raises(self, manager):
        with pytest.raises(NotFoundError):
            manager.delete_game("nope")

    def test_frozen_clock_used(self, frozen_clock):
        from datetime import datetime
        fixed = datetime(2024, 6, 15, 12, 0, 0)
        m = LibraryManager("sqlite:///:memory:", _clock=frozen_clock)
        g = m.add_game(name="Timed")
        updated = m.update_game(g["id"], name="Timed Updated")
        assert updated["modified"] == fixed.isoformat()


class TestFavourites:
    def test_pin_unpin(self, manager):
        g = manager.add_game(name="Fave")
        assert not g["is_favorite"]
        pinned = manager.pin_game(g["id"])
        assert pinned["is_favorite"]
        unpinned = manager.unpin_game(g["id"])
        assert not unpinned["is_favorite"]

    def test_get_favourites(self, populated):
        g_id = populated.list_games()[0]["id"]
        populated.pin_game(g_id)
        favs = populated.get_favourites()
        assert any(f["id"] == g_id for f in favs)


class TestHiding:
    def test_hide_unhide(self, manager):
        g = manager.add_game(name="Hidden")
        manager.hide_game(g["id"])
        visible = manager.list_games()
        assert all(x["id"] != g["id"] for x in visible)
        manager.unhide_game(g["id"])
        visible = manager.list_games()
        assert any(x["id"] == g["id"] for x in visible)

    def test_list_games_excludes_hidden_by_default(self, manager):
        manager.add_game(name="Visible")
        h = manager.add_game(name="Ghost")
        manager.hide_game(h["id"])
        names = [g["name"] for g in manager.list_games()]
        assert "Visible" in names
        assert "Ghost" not in names

    def test_include_hidden_flag(self, manager):
        h = manager.add_game(name="Ghost")
        manager.hide_game(h["id"])
        all_games = manager.list_games(include_hidden=True)
        assert any(g["name"] == "Ghost" for g in all_games)


class TestBulkOperations:
    def test_bulk_tag(self, populated):
        ids = [g["id"] for g in populated.list_games()[:3]]
        results = populated.bulk_tag(ids, "sale")
        assert len(results) == 3
        for g_dict in results:
            assert "sale" in g_dict["tags"]

    def test_bulk_categorize(self, populated):
        ids = [g["id"] for g in populated.list_games()[:2]]
        populated.bulk_categorize(ids, "Weekend")
        for g_dict in populated.list_games():
            if g_dict["id"] in ids:
                assert "Weekend" in g_dict["categories"]

    def test_bulk_update(self, populated):
        ids = [g["id"] for g in populated.list_games()]
        populated.bulk_update(ids, completion_status="completed")
        for g_dict in populated.list_games():
            assert g_dict["completion_status"] == "completed"

    def test_bulk_delete(self, manager):
        ids = [manager.add_game(name=f"G{i}")["id"] for i in range(5)]
        deleted = manager.bulk_delete(ids[:3])
        assert deleted == 3
        assert len(manager.list_games()) == 2

    def test_bulk_hide_unhide(self, populated):
        ids = [g["id"] for g in populated.list_games()[:3]]
        manager = populated
        manager.bulk_hide(ids)
        visible = manager.list_games()
        for gid in ids:
            assert all(g["id"] != gid for g in visible)
        manager.bulk_unhide(ids)
        visible = manager.list_games()
        assert len(visible) == 5

    def test_bulk_update_performance(self):
        """bulk_update on 500 games should complete under 0.5s."""
        m = LibraryManager("sqlite:///:memory:")
        for i in range(500):
            m.add_game(name=f"Perf{i:04d}")
        ids = [g["id"] for g in m.list_games()]
        start = time.time()
        m.bulk_update(ids, completion_status="completed")
        elapsed = time.time() - start
        assert elapsed < 0.5, f"bulk_update took {elapsed:.3f}s — must be < 0.5s"


class TestSortingAndGrouping:
    def test_sort_by_name_asc(self, populated):
        games = populated.list_games(sort_by="name", sort_order="asc")
        names = [g["name"] for g in games]
        assert names == sorted(names, key=str.lower)

    def test_sort_by_name_desc(self, populated):
        games = populated.list_games(sort_by="name", sort_order="desc")
        names = [g["name"] for g in games]
        assert names == sorted(names, key=str.lower, reverse=True)

    def test_group_by_returns_dict(self, populated):
        result = populated.list_games(group_by="completion_status")
        assert isinstance(result, dict)
        for key, items in result.items():
            assert isinstance(items, list)

    def test_sort_by_playtime(self, populated):
        games = populated.list_games(sort_by="playtime", sort_order="desc")
        times = [g["playtime"] for g in games]
        assert times == sorted(times, reverse=True)

    def test_sort_performance_1000_games(self):
        """list_games with SQL sort on 1000 games must be < 1s."""
        m = LibraryManager("sqlite:///:memory:")
        for i in range(1000):
            m.add_game(name=f"Game {i:04d}", release_year=2000 + (i % 24))
        start = time.time()
        games = m.list_games(sort_by="release_year", sort_order="desc")
        elapsed = time.time() - start
        assert elapsed < 1.0, f"list_games sort took {elapsed:.3f}s — must be < 1s"
        assert len(games) == 1000

    def test_list_games_limit(self, populated):
        games = populated.list_games(sort_by="name", sort_order="asc", limit=2)
        assert len(games) == 2

    def test_list_games_offset(self, populated):
        all_games = populated.list_games(sort_by="name", sort_order="asc")
        offset_games = populated.list_games(sort_by="name", sort_order="asc", offset=1)
        assert len(offset_games) == len(all_games) - 1
        assert offset_games[0]["name"] == all_games[1]["name"]


class TestTagOperations:
    def test_get_tag(self, manager):
        t = manager.add_tag("action")
        fetched = manager.get_tag(t["id"])
        assert fetched["name"] == "action"

    def test_get_tag_missing_raises(self, manager):
        with pytest.raises(NotFoundError):
            manager.get_tag("nope")

    def test_update_tag(self, manager):
        t = manager.add_tag("old-name")
        updated = manager.update_tag(t["id"], "new-name")
        assert updated["name"] == "new-name"
        assert manager.get_tag(t["id"])["name"] == "new-name"

    def test_update_tag_missing_raises(self, manager):
        with pytest.raises(NotFoundError):
            manager.update_tag("nope", "x")

    def test_apply_and_remove_tag(self, manager):
        g = manager.add_game(name="Tagged")
        manager.apply_tag(g["id"], "cool")
        assert "cool" in manager.get_game(g["id"])["tags"]
        manager.remove_tag(g["id"], "cool")
        assert "cool" not in manager.get_game(g["id"])["tags"]


class TestCategoryOperations:
    def test_get_category(self, manager):
        c = manager.add_category("Action")
        fetched = manager.get_category(c["id"])
        assert fetched["name"] == "Action"

    def test_get_category_missing_raises(self, manager):
        with pytest.raises(NotFoundError):
            manager.get_category("nope")

    def test_update_category(self, manager):
        c = manager.add_category("Old")
        updated = manager.update_category(c["id"], "New")
        assert updated["name"] == "New"

    def test_update_category_missing_raises(self, manager):
        with pytest.raises(NotFoundError):
            manager.update_category("nope", "x")


class TestGenresAndPlatforms:
    def test_list_genres(self, populated):
        genres = populated.list_genres()
        names = [g["name"] for g in genres]
        assert "RPG" in names
        assert "Puzzle" in names

    def test_list_platforms(self, populated):
        platforms = populated.list_platforms()
        names = [p["name"] for p in platforms]
        assert "PC" in names

    def test_list_genres_empty(self, manager):
        assert manager.list_genres() == []

    def test_list_platforms_empty(self, manager):
        assert manager.list_platforms() == []


class TestViewPresets:
    def test_list_games_with_preset(self, populated):
        populated.save_view_preset(
            "rpg-view",
            sort_by="name",
            sort_order="asc",
            filters={"genres": ["RPG"]},
        )
        result = populated.list_games_with_preset("rpg-view")
        assert isinstance(result, list)
        for g in result:
            assert "RPG" in g["genres"]

    def test_list_games_with_preset_grouped(self, populated):
        populated.save_view_preset(
            "grouped",
            group_by="completion_status",
            filters={"completion_statuses": ["completed"]},
        )
        result = populated.list_games_with_preset("grouped")
        assert isinstance(result, dict)
        assert "completed" in result

    def test_list_games_with_preset_missing_raises(self, manager):
        with pytest.raises(NotFoundError):
            manager.list_games_with_preset("no-such-preset")


class TestStats:
    def test_stats_keys(self, populated):
        s = populated.get_stats()
        assert "total_games" in s
        assert "total_playtime_hours" in s
        assert s["total_games"] == 5
