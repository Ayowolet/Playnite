"""Filter performance benchmarks."""

import pytest

from playnite_py.organisation import GameFilter


@pytest.mark.benchmark
class TestFilterPerformance:
    """Benchmark filtering operations."""

    def test_single_platform_filter(self, benchmark, benchmark_session):
        """Benchmark filtering by single platform."""
        game_filter = GameFilter(benchmark_session)

        def filter_platform():
            return game_filter.filter_games({'platforms': ['PC']})

        result = benchmark(filter_platform)
        assert isinstance(result, list)

    def test_single_genre_filter(self, benchmark, benchmark_session):
        """Benchmark filtering by single genre."""
        game_filter = GameFilter(benchmark_session)

        def filter_genre():
            return game_filter.filter_games({'genres': ['RPG']})

        result = benchmark(filter_genre)
        assert isinstance(result, list)

    def test_multi_filter_platform_genre(self, benchmark, benchmark_session):
        """Benchmark filtering by platform and genre."""
        game_filter = GameFilter(benchmark_session)

        def multi_filter():
            return game_filter.filter_games({
                'platforms': ['PC'],
                'genres': ['RPG']
            })

        result = benchmark(multi_filter)
        assert isinstance(result, list)

    def test_complex_filter(self, benchmark, benchmark_session):
        """Benchmark complex multi-criteria filter."""
        game_filter = GameFilter(benchmark_session)

        def complex_filter():
            return game_filter.filter_games({
                'platforms': ['PC', 'PlayStation 5'],
                'genres': ['RPG', 'Action'],
                'playtime_min': 100,
                'is_favorite': False
            })

        result = benchmark(complex_filter)
        assert isinstance(result, list)

    def test_filter_with_sorting(self, benchmark, benchmark_session):
        """Benchmark filtering with sorting."""
        game_filter = GameFilter(benchmark_session)

        def filter_sort():
            return game_filter.filter_games(
                {'platforms': ['PC']},
                sort_by='playtime',
                sort_desc=True
            )

        result = benchmark(filter_sort)
        assert isinstance(result, list)

    def test_filter_with_pagination(self, benchmark, benchmark_session):
        """Benchmark filtering with pagination."""
        game_filter = GameFilter(benchmark_session)

        def filter_paginate():
            return game_filter.filter_games(
                {'platforms': ['PC']},
                limit=50,
                offset=0
            )

        result = benchmark(filter_paginate)
        assert len(result) <= 50

    def test_filter_favorites_only(self, benchmark, benchmark_session):
        """Benchmark filtering favorites."""
        game_filter = GameFilter(benchmark_session)

        def filter_favorites():
            return game_filter.filter_games({'is_favorite': True})

        result = benchmark(filter_favorites)
        assert isinstance(result, list)

    def test_filter_by_playtime_range(self, benchmark, benchmark_session):
        """Benchmark filtering by playtime range."""
        game_filter = GameFilter(benchmark_session)

        def filter_playtime():
            return game_filter.filter_games({
                'playtime_min': 100,
                'playtime_max': 1000
            })

        result = benchmark(filter_playtime)
        assert isinstance(result, list)

    def test_filter_by_release_year(self, benchmark, benchmark_session):
        """Benchmark filtering by release year."""
        game_filter = GameFilter(benchmark_session)

        def filter_year():
            return game_filter.filter_games({
                'release_year_min': 2020
            })

        result = benchmark(filter_year)
        assert isinstance(result, list)


@pytest.mark.benchmark
class TestFilterLargeDatabase:
    """Benchmark filtering on large database (5000 games)."""

    def test_filter_5000_games(self, benchmark, large_session):
        """Benchmark filtering 5000 games."""
        game_filter = GameFilter(large_session)

        def filter_large():
            return game_filter.filter_games({'platforms': ['PC']})

        result = benchmark(filter_large)
        assert isinstance(result, list)

    def test_complex_filter_5000_games(self, benchmark, large_session):
        """Benchmark complex filter on 5000 games."""
        game_filter = GameFilter(large_session)

        def complex_filter_large():
            return game_filter.filter_games({
                'platforms': ['PC'],
                'genres': ['RPG'],
                'playtime_min': 100,
                'release_year_min': 2015
            })

        result = benchmark(complex_filter_large)
        assert isinstance(result, list)
