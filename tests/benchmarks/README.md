# Performance Benchmarks

This directory contains performance benchmarks for Playnite Python.

## Installation

Install benchmark dependencies:

```bash
pip install pytest-benchmark faker
```

Or install from requirements.txt:

```bash
pip install -r requirements.txt
```

## Running Benchmarks

Run all benchmarks:

```bash
pytest tests/benchmarks/ --benchmark-only
```

Run specific benchmark file:

```bash
pytest tests/benchmarks/test_database_perf.py --benchmark-only
```

Run with benchmark comparison:

```bash
# First run
pytest tests/benchmarks/ --benchmark-only --benchmark-autosave

# After code changes
pytest tests/benchmarks/ --benchmark-only --benchmark-compare
```

## Benchmark Categories

### Database Operations (`test_database_perf.py`)

Tests database CRUD operations on 1000 and 5000 game databases:
- Single game queries
- Bulk queries
- Updates and deletions
- Relationship loading

**Target Performance:**
- Single game query: < 100ms
- Query all games (1000): < 500ms
- Bulk update (100 games): < 2s

### Search Operations (`test_search_perf.py`)

Tests search functionality:
- Simple name search
- Fuzzy matching
- Tag-based search
- Large database searches (5000 games)

**Target Performance:**
- Simple search: < 200ms
- Fuzzy search: < 500ms

### Filter Operations (`test_filter_perf.py`)

Tests filtering with various criteria:
- Single filter (platform, genre)
- Multi-criteria filters
- Complex filters with sorting and pagination

**Target Performance:**
- Single filter: < 100ms
- Multi-filter: < 200ms
- Complex filter: < 300ms

### Bulk Operations (`test_bulk_perf.py`)

Tests bulk operations on multiple games:
- Bulk tag addition/removal
- Bulk favorite/hidden updates
- Bulk deletion

**Target Performance:**
- Bulk add tags (100 games): < 3s
- Bulk delete (500 games): < 1s

## Test Fixtures

The `conftest.py` provides:
- `benchmark_db`: In-memory database with 1000 games
- `large_db`: In-memory database with 5000 games
- `benchmark_session`: Database session from benchmark_db
- `large_session`: Database session from large_db

## Data Generation

The `fixtures/data_generator.py` provides `GameDataGenerator` class that creates realistic test data with:
- Random game names
- Log-normal distributed playtimes
- Release dates over 20 years
- Multiple platforms, genres, and tags per game

## Notes

- Benchmarks use in-memory SQLite databases for speed
- Event handlers are disabled during benchmark data generation
- Random seed (42) ensures reproducible test data
- All benchmarks are marked with `@pytest.mark.benchmark`
