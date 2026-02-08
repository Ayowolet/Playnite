"""Search performance benchmarks."""

import pytest

from playnite_py.organisation import GameSearch


@pytest.mark.benchmark
class TestSearchPerformance:
    """Benchmark search operations."""

    def test_simple_search_1000_games(self, benchmark, benchmark_session):
        """Benchmark simple name search on 1000 games."""
        search = GameSearch(benchmark_session)

        def search_games():
            return search.search("Game", fuzzy=False, limit=50)

        result = benchmark(search_games)
        assert isinstance(result, list)

    def test_fuzzy_search_1000_games(self, benchmark, benchmark_session):
        """Benchmark fuzzy search on 1000 games."""
        search = GameSearch(benchmark_session)

        def fuzzy_search():
            return search.search("Gam", fuzzy=True, limit=50)

        result = benchmark(fuzzy_search)
        assert isinstance(result, list)

    def test_search_with_limit_10(self, benchmark, benchmark_session):
        """Benchmark search with small result limit."""
        search = GameSearch(benchmark_session)

        def search_limited():
            return search.search("a", fuzzy=False, limit=10)

        result = benchmark(search_limited)
        assert len(result) <= 10

    def test_search_by_tag(self, benchmark, benchmark_session):
        """Benchmark searching by tag."""
        search = GameSearch(benchmark_session)

        def search_tag():
            return search.search_by_tag("indie")

        result = benchmark(search_tag)
        assert isinstance(result, list)

    def test_search_empty_query(self, benchmark, benchmark_session):
        """Benchmark search with empty query (should be fast)."""
        search = GameSearch(benchmark_session)

        def search_empty():
            return search.search("")

        result = benchmark(search_empty)
        assert result == []

    def test_search_no_results(self, benchmark, benchmark_session):
        """Benchmark search with no results."""
        search = GameSearch(benchmark_session)

        def search_no_results():
            return search.search("ZZZZZZZZZZZZZZZ")

        result = benchmark(search_no_results)
        assert len(result) == 0


@pytest.mark.benchmark
class TestSearchLargeDatabase:
    """Benchmark search on large database (5000 games)."""

    def test_search_5000_games(self, benchmark, large_session):
        """Benchmark search on 5000 games."""
        search = GameSearch(large_session)

        def search_large():
            return search.search("Game", limit=100)

        result = benchmark(search_large)
        assert isinstance(result, list)

    def test_fuzzy_search_5000_games(self, benchmark, large_session):
        """Benchmark fuzzy search on 5000 games."""
        search = GameSearch(large_session)

        def fuzzy_search_large():
            return search.search("Gam", fuzzy=True, limit=100)

        result = benchmark(fuzzy_search_large)
        assert isinstance(result, list)
