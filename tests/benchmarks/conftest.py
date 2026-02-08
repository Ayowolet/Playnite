"""Pytest fixtures for benchmark tests."""

import pytest

from playnite_py.database import DatabaseEngine
from .fixtures.data_generator import GameDataGenerator


@pytest.fixture(scope="session")
def benchmark_db():
    """Create in-memory database with 1000 games for benchmarking."""
    engine = DatabaseEngine(db_path=None)  # In-memory SQLite
    engine.create_tables(register_events=False)  # Disable events for benchmarking

    session = engine.get_session()
    generator = GameDataGenerator(seed=42)

    # Generate 1000 test games
    generator.generate_test_games(1000, session)

    yield engine

    session.close()


@pytest.fixture(scope="session")
def large_db():
    """Create in-memory database with 5000 games for stress testing."""
    engine = DatabaseEngine(db_path=None)
    engine.create_tables(register_events=False)

    session = engine.get_session()
    generator = GameDataGenerator(seed=42)

    # Generate 5000 test games
    generator.generate_test_games(5000, session)

    yield engine

    session.close()


@pytest.fixture
def benchmark_session(benchmark_db):
    """Get a database session from benchmark database."""
    session = benchmark_db.get_session()
    yield session
    session.close()


@pytest.fixture
def large_session(large_db):
    """Get a database session from large database."""
    session = large_db.get_session()
    yield session
    session.close()
