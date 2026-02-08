"""Unit tests for search and view presets."""
import pytest


class TestSearch:
    def test_search_by_title(self, populated):
        results = populated.search("Witcher")
        assert len(results) >= 1
        assert results[0]["game"]["name"] == "The Witcher 3"

    def test_search_by_developer(self, populated):
        results = populated.search("Valve")
        names = [r["game"]["name"] for r in results]
        assert "Portal 2" in names

    def test_search_by_tag(self, populated):
        results = populated.search("fantasy")
        names = {r["game"]["name"] for r in results}
        assert "The Witcher 3" in names
        assert "Dark Souls" in names

    def test_search_empty_returns_all(self, populated):
        results = populated.search("")
        assert len(results) == 5

    def test_fuzzy_search(self, populated):
        # "Suls" should fuzzy-match "Souls"
        results = populated.search("Suls", threshold=40)
        names = [r["game"]["name"] for r in results]
        assert "Dark Souls" in names

    def test_search_no_match(self, populated):
        results = populated.search("xyznotexist", threshold=90)
        assert results == []

    def test_results_sorted_by_score(self, populated):
        results = populated.search("Portal")
        if len(results) > 1:
            scores = [r["score"] for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_search_pagination(self, populated):
        all_results = populated.search("a")
        paginated = populated.search("a", limit=1, offset=0)
        assert len(paginated) == 1
        assert paginated[0]["game"]["name"] == all_results[0]["game"]["name"]


class TestViewPresets:
    def test_save_and_load(self, manager):
        manager.save_view_preset(
            "mypreset",
            sort_by="playtime",
            sort_order="desc",
            group_by="completion_status",
            view_type="grid",
            filters={"genres": ["RPG"]},
            columns=["name", "playtime"],
        )
        loaded = manager.load_view_preset("mypreset")
        assert loaded["sort_by"] == "playtime"
        assert loaded["sort_order"] == "desc"
        assert loaded["group_by"] == "completion_status"
        assert loaded["view_type"] == "grid"
        assert loaded["filters"] == {"genres": ["RPG"]}
        assert loaded["columns"] == ["name", "playtime"]

    def test_overwrite_preset(self, manager):
        manager.save_view_preset("p", sort_by="name")
        manager.save_view_preset("p", sort_by="playtime")
        loaded = manager.load_view_preset("p")
        assert loaded["sort_by"] == "playtime"

    def test_list_presets(self, manager):
        manager.save_view_preset("alpha")
        manager.save_view_preset("beta")
        names = [p["name"] for p in manager.list_view_presets()]
        assert "alpha" in names
        assert "beta" in names

    def test_delete_preset(self, manager):
        manager.save_view_preset("gone")
        manager.delete_view_preset("gone")
        assert not any(p["name"] == "gone" for p in manager.list_view_presets())

    def test_load_missing_raises(self, manager):
        from playnite.library.organisation import NotFoundError
        with pytest.raises(NotFoundError):
            manager.load_view_preset("noexist")
