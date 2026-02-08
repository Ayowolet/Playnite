"""Unit tests for the filtering system."""
import pytest

from playnite.library.filters import FilterSpec


class TestFilterSpec:
    def test_to_dict_omits_none(self):
        spec = FilterSpec(platforms=["PC"], release_year_min=2010)
        d = spec.to_dict()
        assert "platforms" in d
        assert "release_year_min" in d
        assert "genres" not in d

    def test_from_dict_roundtrip(self):
        original = FilterSpec(platforms=["PC"], is_favorite=True, playtime_min=3600)
        restored = FilterSpec.from_dict(original.to_dict())
        assert restored.platforms == ["PC"]
        assert restored.is_favorite is True
        assert restored.playtime_min == 3600


class TestFiltering:
    def test_filter_by_platform(self, populated):
        from playnite.library.filters import FilterSpec
        results = populated.list_games(filter_spec=FilterSpec(platforms=["PS4"]))
        assert all("PS4" in g["platforms"] for g in results)
        assert len(results) >= 1

    def test_filter_by_genre(self, populated):
        results = populated.list_games(filter_spec=FilterSpec(genres=["Puzzle"]))
        assert all("Puzzle" in g["genres"] for g in results)

    def test_filter_by_tag(self, populated):
        results = populated.list_games(filter_spec=FilterSpec(tags=["fantasy"]))
        assert all("fantasy" in g["tags"] for g in results)
        assert len(results) == 2  # Witcher 3 + Dark Souls

    def test_filter_by_year_range(self, populated):
        results = populated.list_games(filter_spec=FilterSpec(release_year_min=2015, release_year_max=2020))
        for g in results:
            assert 2015 <= g["release_year"] <= 2020

    def test_filter_by_playtime(self, populated):
        results = populated.list_games(filter_spec=FilterSpec(playtime_min=3600))
        for g in results:
            assert g["playtime"] >= 3600

    def test_filter_by_completion_status(self, populated):
        results = populated.list_games(filter_spec=FilterSpec(completion_statuses=["completed"]))
        assert all(g["completion_status"] == "completed" for g in results)
        assert len(results) == 2

    def test_filter_by_rating(self, populated):
        results = populated.list_games(filter_spec=FilterSpec(rating_min=90))
        for g in results:
            assert g["user_score"] >= 90

    def test_filter_by_favorite(self, populated):
        games = populated.list_games()
        populated.pin_game(games[0]["id"])
        results = populated.list_games(filter_spec=FilterSpec(is_favorite=True))
        assert len(results) == 1

    def test_filter_by_developer(self, populated):
        results = populated.list_games(filter_spec=FilterSpec(developer="CD Projekt"))
        assert len(results) == 2
        for g in results:
            assert "CD Projekt" in g["developer"]

    def test_filter_by_publisher(self, populated):
        results = populated.list_games(filter_spec=FilterSpec(publisher="Valve"))
        assert len(results) == 1
        assert results[0]["name"] == "Portal 2"

    def test_multiple_filters_combined(self, populated):
        results = populated.list_games(
            filter_spec=FilterSpec(genres=["RPG"], release_year_min=2015)
        )
        for g in results:
            assert "RPG" in g["genres"]
            assert g["release_year"] >= 2015
