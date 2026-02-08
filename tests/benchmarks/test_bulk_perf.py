"""Bulk operations performance benchmarks."""

import pytest

from playnite_py.organisation import BulkOperations
from playnite_py.database import GameOperations


@pytest.mark.benchmark
class TestBulkOperationsPerformance:
    """Benchmark bulk operations."""

    def test_bulk_add_tags_100_games(self, benchmark, benchmark_session):
        """Benchmark bulk adding tags to 100 games."""
        bulk_ops = BulkOperations(benchmark_session)
        game_ids = list(range(1, 101))

        def bulk_add_tags():
            bulk_ops.bulk_add_tags(game_ids, ['benchmark-tag'])

        benchmark(bulk_add_tags)

    def test_bulk_add_tags_500_games(self, benchmark, benchmark_session):
        """Benchmark bulk adding tags to 500 games."""
        bulk_ops = BulkOperations(benchmark_session)
        game_ids = list(range(1, 501))

        def bulk_add_tags_500():
            bulk_ops.bulk_add_tags(game_ids, ['benchmark-tag'])

        benchmark(bulk_add_tags_500)

    def test_bulk_set_favorite_100_games(self, benchmark, benchmark_session):
        """Benchmark bulk setting favorites for 100 games."""
        bulk_ops = BulkOperations(benchmark_session)
        game_ids = list(range(1, 101))

        def bulk_favorite():
            bulk_ops.bulk_set_favorite(game_ids, True)

        benchmark(bulk_favorite)

    def test_bulk_set_hidden_100_games(self, benchmark, benchmark_session):
        """Benchmark bulk hiding 100 games."""
        bulk_ops = BulkOperations(benchmark_session)
        game_ids = list(range(1, 101))

        def bulk_hidden():
            bulk_ops.bulk_set_hidden(game_ids, True)

        benchmark(bulk_hidden)

    def test_bulk_update_field_100_games(self, benchmark, benchmark_session):
        """Benchmark bulk updating a field for 100 games."""
        bulk_ops = BulkOperations(benchmark_session)
        game_ids = list(range(1, 101))

        def bulk_update():
            bulk_ops.bulk_update_field(game_ids, 'user_score', 85)

        benchmark(bulk_update)

    def test_bulk_add_multiple_tags_100_games(self, benchmark, benchmark_session):
        """Benchmark bulk adding multiple tags to 100 games."""
        bulk_ops = BulkOperations(benchmark_session)
        game_ids = list(range(1, 101))

        def bulk_add_multi_tags():
            bulk_ops.bulk_add_tags(game_ids, ['tag1', 'tag2', 'tag3'])

        benchmark(bulk_add_multi_tags)

    def test_bulk_remove_tags_100_games(self, benchmark, benchmark_session):
        """Benchmark bulk removing tags from 100 games."""
        bulk_ops = BulkOperations(benchmark_session)
        game_ids = list(range(1, 101))

        # First add tags to remove
        bulk_ops.bulk_add_tags(game_ids, ['remove-tag'])

        def bulk_remove_tags():
            bulk_ops.bulk_remove_tags(game_ids, ['remove-tag'])

        benchmark(bulk_remove_tags)

    def test_bulk_delete_100_games(self, benchmark, benchmark_session):
        """Benchmark bulk deleting 100 games."""
        ops = GameOperations(benchmark_session)
        bulk_ops = BulkOperations(benchmark_session)

        def setup_and_delete():
            # Create 100 games to delete
            game_ids = []
            for i in range(100):
                game = ops.create_game(f"Delete Test Game {i}")
                game_ids.append(game.id)

            # Delete them
            bulk_ops.bulk_delete(game_ids)

        benchmark(setup_and_delete)


@pytest.mark.benchmark
class TestBulkOperationsLargeScale:
    """Benchmark bulk operations at larger scale."""

    def test_bulk_add_tags_1000_games(self, benchmark, large_session):
        """Benchmark bulk adding tags to 1000 games."""
        bulk_ops = BulkOperations(large_session)
        game_ids = list(range(1, 1001))

        def bulk_add_1000():
            bulk_ops.bulk_add_tags(game_ids, ['large-scale-tag'])

        benchmark(bulk_add_1000)

    def test_bulk_set_favorite_1000_games(self, benchmark, large_session):
        """Benchmark bulk setting favorites for 1000 games."""
        bulk_ops = BulkOperations(large_session)
        game_ids = list(range(1, 1001))

        def bulk_favorite_1000():
            bulk_ops.bulk_set_favorite(game_ids, True)

        benchmark(bulk_favorite_1000)

    def test_bulk_update_field_500_games(self, benchmark, large_session):
        """Benchmark bulk updating field for 500 games."""
        bulk_ops = BulkOperations(large_session)
        game_ids = list(range(1, 501))

        def bulk_update_500():
            bulk_ops.bulk_update_field(game_ids, 'playtime', 100)

        benchmark(bulk_update_500)
