"""Database operations performance benchmarks."""

import pytest

from playnite_py.database import GameOperations


@pytest.mark.benchmark
class TestDatabasePerformance:
    """Benchmark database operations on 1000+ games."""

    def test_query_single_game(self, benchmark, benchmark_session):
        """Benchmark querying a single game by ID."""
        ops = GameOperations(benchmark_session)

        def query_game():
            return ops.get_game(500)

        result = benchmark(query_game)
        assert result is not None

    def test_query_all_games(self, benchmark, benchmark_session):
        """Benchmark querying all games."""
        ops = GameOperations(benchmark_session)

        def query_all():
            return ops.get_all_games(limit=1000)

        result = benchmark(query_all)
        assert len(result) > 0

    def test_query_games_with_relationships(self, benchmark, benchmark_session):
        """Benchmark querying games with eager loading of relationships."""
        ops = GameOperations(benchmark_session)

        def query_with_relationships():
            games = ops.get_all_games(limit=100)
            # Access relationships to trigger loading
            for game in games:
                _ = game.platforms
                _ = game.genres
                _ = game.tags
            return games

        result = benchmark(query_with_relationships)
        assert len(result) > 0

    def test_update_game(self, benchmark, benchmark_session):
        """Benchmark updating a game."""
        ops = GameOperations(benchmark_session)

        def update_game():
            game = ops.get_game(100)
            ops.update_game(game.id, playtime=game.playtime + 60)
            return game

        benchmark(update_game)

    def test_bulk_update_100_games(self, benchmark, benchmark_session):
        """Benchmark bulk updating 100 games."""
        ops = GameOperations(benchmark_session)

        def bulk_update():
            game_ids = list(range(1, 101))
            ops.bulk_update(game_ids, {'is_favorite': True})

        benchmark(bulk_update)

    def test_create_game(self, benchmark, benchmark_session):
        """Benchmark creating a new game."""
        ops = GameOperations(benchmark_session)
        counter = [0]

        def create_game():
            counter[0] += 1
            return ops.create_game(f"Benchmark Game {counter[0]}")

        result = benchmark(create_game)
        assert result.id is not None

    def test_delete_game(self, benchmark, benchmark_session):
        """Benchmark deleting a game."""
        ops = GameOperations(benchmark_session)

        # Create a game to delete
        def setup():
            return ops.create_game("Game to Delete")

        def delete_game():
            game = setup()
            ops.delete_game(game.id)

        benchmark(delete_game)

    def test_add_tags_to_game(self, benchmark, benchmark_session):
        """Benchmark adding tags to a game."""
        ops = GameOperations(benchmark_session)

        def add_tags():
            ops.add_tag_to_game(50, "benchmark-tag")

        benchmark(add_tags)


@pytest.mark.benchmark
class TestLargeDatabasePerformance:
    """Benchmark operations on 5000+ games."""

    def test_query_all_games_5000(self, benchmark, large_session):
        """Benchmark querying 5000 games."""
        ops = GameOperations(large_session)

        def query_all():
            return ops.get_all_games(limit=5000)

        result = benchmark(query_all)
        assert len(result) > 0

    def test_search_in_large_db(self, benchmark, large_session):
        """Benchmark searching in large database."""
        from playnite_py.organisation import GameSearch

        search = GameSearch(large_session)

        def search_games():
            return search.search("Game", limit=50)

        result = benchmark(search_games)
        assert len(result) >= 0

    def test_filter_in_large_db(self, benchmark, large_session):
        """Benchmark filtering in large database."""
        from playnite_py.organisation import GameFilter

        game_filter = GameFilter(large_session)

        def filter_games():
            return game_filter.filter_games(
                {'platforms': ['PC']},
                limit=100
            )

        result = benchmark(filter_games)
        assert len(result) >= 0
