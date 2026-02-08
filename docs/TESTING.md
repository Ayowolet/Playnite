# Testing Guide

This document explains how to run tests and contribute to the test suite for Playnite Python.

## Overview

The project uses pytest for testing with three levels of tests:

1. **Unit Tests** - Test individual components in isolation
2. **Integration Tests** - Test component interactions and workflows
3. **Benchmark Tests** - Measure performance on realistic datasets

## Quick Start

```bash
# Install test dependencies
pip install pytest pytest-cov pytest-benchmark faker

# Run all unit tests
pytest tests/unit/

# Run all tests with coverage
pytest --cov=playnite_py tests/

# Run integration tests
pytest tests/integration/

# Run benchmarks
pytest tests/benchmarks/ --benchmark-only
```

## Test Structure

```
tests/
├── unit/                       # Unit tests
│   ├── test_database.py       # Database operations
│   ├── test_organisation.py   # Filtering, search, collections
│   ├── test_controller.py     # Controller input
│   └── test_navigation.py     # Navigation state machine
├── integration/                # Integration tests
│   └── test_cli_workflow.py   # End-to-end CLI workflows
└── benchmarks/                 # Performance benchmarks
    ├── README.md              # Benchmark documentation
    ├── conftest.py            # Benchmark fixtures
    ├── test_database_perf.py  # Database benchmarks
    ├── test_search_perf.py    # Search benchmarks
    ├── test_filter_perf.py    # Filter benchmarks
    └── test_bulk_perf.py      # Bulk operation benchmarks
```

## Unit Tests

### Running Unit Tests

```bash
# Run all unit tests
pytest tests/unit/

# Run specific test file
pytest tests/unit/test_database.py

# Run specific test class
pytest tests/unit/test_database.py::TestGameOperations

# Run specific test
pytest tests/unit/test_database.py::TestGameOperations::test_create_game

# Run with verbose output
pytest tests/unit/ -v

# Stop on first failure
pytest tests/unit/ -x
```

### Test Categories

#### Database Tests (`test_database.py`)

Tests for core database operations:
- CRUD operations for games
- Platform, genre, tag management
- Bulk operations
- Collection management

**Example:**
```python
def test_create_game(self, session):
    ops = GameOperations(session)
    game = ops.create_game("Test Game")
    assert game.id is not None
    assert game.name == "Test Game"
```

#### Organisation Tests (`test_organisation.py`)

Tests for filtering, search, and collections:
- Game filtering by various criteria
- Search with fuzzy matching
- Smart collection creation and updates
- Bulk tag/category operations

**Example:**
```python
def test_filter_by_platform(self, session, sample_games):
    game_filter = GameFilter(session)
    results = game_filter.filter_games({'platforms': ['PC']})
    assert len(results) == 4
```

#### Controller Tests (`test_controller.py`)

Tests for controller input system:
- Controller detection (headless mode)
- Button mapping configuration
- Input event processing
- Controller simulation

**Example:**
```python
def test_init_headless(self):
    manager = ControllerManager(headless=True)
    assert manager.headless is True
    assert manager.initialized is False
```

#### Navigation Tests (`test_navigation.py`)

Tests for UI navigation state machine:
- Grid navigation
- List navigation
- State transitions
- Cursor movement

**Example:**
```python
def test_cursor_movement_grid(self):
    nav = NavigationStateMachine(UIState.GAME_GRID)
    nav.set_grid_layout(columns=4, rows=3)
    nav.handle_command(NavigationCommand.RIGHT)
    assert nav.get_cursor_position() == 1
```

### Writing Unit Tests

**Template:**
```python
import pytest
from playnite_py.database import GameOperations

class TestYourFeature:
    """Test your feature."""

    def test_basic_functionality(self, session):
        """Test basic functionality."""
        ops = GameOperations(session)
        # Your test code here
        assert result == expected
```

**Best Practices:**
1. Use descriptive test names
2. Test one thing per test
3. Use fixtures for setup
4. Clean up resources
5. Add docstrings

## Integration Tests

Integration tests verify end-to-end workflows using the CLI.

### Running Integration Tests

```bash
# Run all integration tests
pytest tests/integration/

# Run with output capture disabled (see CLI output)
pytest tests/integration/ -s
```

### CLI Workflow Tests

Test complete user workflows:
- Add games, search, filter
- Create smart collections
- Bulk operations
- View preset management

**Example:**
```python
def test_add_and_search_workflow(self, db_path):
    """Test adding a game and searching for it."""
    # Add game
    result = runner.invoke(cli, [
        '--db-path', db_path,
        'library', 'add', 'Test Game',
        '--platform', 'PC'
    ])
    assert result.exit_code == 0

    # Search for it
    result = runner.invoke(cli, [
        '--db-path', db_path,
        'library', 'search', 'Test'
    ])
    assert 'Test Game' in result.output
```

### Writing Integration Tests

Use Click's `CliRunner` for testing CLI commands:

```python
from click.testing import CliRunner
from playnite_py.cli.main import cli

def test_your_workflow():
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Your test code
        result = runner.invoke(cli, ['init', '--db-path', 'test.db'])
        assert result.exit_code == 0
```

## Benchmark Tests

Performance benchmarks measure operation speed on realistic datasets.

### Running Benchmarks

```bash
# Run all benchmarks
pytest tests/benchmarks/ --benchmark-only

# Run specific benchmark
pytest tests/benchmarks/test_database_perf.py --benchmark-only

# Save results
pytest tests/benchmarks/ --benchmark-only --benchmark-autosave

# Compare with previous run
pytest tests/benchmarks/ --benchmark-only --benchmark-compare

# Generate histogram
pytest tests/benchmarks/ --benchmark-only --benchmark-histogram
```

### Benchmark Fixtures

Pre-populated databases for consistent testing:
- `benchmark_db`: 1000 games
- `large_db`: 5000 games
- `benchmark_session`: Session for benchmark_db
- `large_session`: Session for large_db

### Writing Benchmarks

```python
@pytest.mark.benchmark
def test_your_operation(benchmark, benchmark_session):
    """Benchmark your operation."""
    ops = GameOperations(benchmark_session)

    def operation():
        return ops.your_operation()

    result = benchmark(operation)
    assert result is not None
```

**Benchmark Best Practices:**
1. Mark tests with `@pytest.mark.benchmark`
2. Use realistic data sizes
3. Test one operation per benchmark
4. Document expected performance

## Coverage Reports

Generate code coverage reports:

```bash
# Run tests with coverage
pytest --cov=playnite_py tests/

# Generate HTML report
pytest --cov=playnite_py --cov-report=html tests/

# Open coverage report
open htmlcov/index.html

# Show missing lines
pytest --cov=playnite_py --cov-report=term-missing tests/
```

**Current Coverage:**
- Total: 48%
- Database operations: 71%
- Models: 90%+
- Organisation: 68-86%

## Test Fixtures

### Common Fixtures

**Database Fixtures:**
```python
@pytest.fixture
def db_engine():
    """Create in-memory database."""
    engine = DatabaseEngine(db_path=None)
    engine.create_tables()
    return engine

@pytest.fixture
def session(db_engine):
    """Create database session."""
    return db_engine.get_session()
```

**Sample Data Fixtures:**
```python
@pytest.fixture
def sample_games(session):
    """Create sample games for testing."""
    ops = GameOperations(session)
    games = []
    for i in range(5):
        game = ops.create_game(f"Game {i}")
        games.append(game)
    return games
```

## Continuous Integration

Tests run automatically on commits:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    pip install -r requirements.txt
    pytest tests/ --cov=playnite_py
```

## Debugging Tests

### Run Failing Test

```bash
# Show full output
pytest tests/unit/test_database.py::test_name -vv

# Show print statements
pytest tests/unit/test_database.py::test_name -s

# Drop into debugger on failure
pytest tests/unit/test_database.py::test_name --pdb
```

### Common Issues

**Import Errors:**
```bash
# Install package in development mode
pip install -e .
```

**Database Errors:**
```bash
# Ensure tables are created
pytest tests/unit/ -v
# Check conftest.py fixtures
```

**Pygame Errors:**
```bash
# Run in headless mode
export SDL_VIDEODRIVER=dummy
pytest tests/unit/test_controller.py
```

## Test Data

### Generating Test Data

```python
from tests/benchmarks/fixtures/data_generator import GameDataGenerator

generator = GameDataGenerator(seed=42)
games = generator.generate_test_games(1000, session)
```

### Realistic Data

Test data mimics real-world distributions:
- Log-normal playtimes (most games <100 hours, some 1000+)
- Release dates spanning 20 years
- Multiple platforms, genres, tags per game
- 10% favorites, 5% hidden

## Performance Testing

See `tests/benchmarks/README.md` for detailed benchmark documentation.

**Quick Reference:**
```bash
# Benchmark database operations
pytest tests/benchmarks/test_database_perf.py --benchmark-only

# Benchmark search
pytest tests/benchmarks/test_search_perf.py --benchmark-only

# Benchmark filters
pytest tests/benchmarks/test_filter_perf.py --benchmark-only

# Benchmark bulk operations
pytest tests/benchmarks/test_bulk_perf.py --benchmark-only
```

## Contributing Tests

When adding new features:

1. **Add unit tests** for the feature
2. **Add integration tests** if it affects workflows
3. **Add benchmarks** if it's performance-critical
4. **Update documentation**
5. **Ensure tests pass** before submitting PR

**Test Coverage Goals:**
- Unit tests: >80% coverage
- Integration tests: Cover main workflows
- Benchmarks: Performance-critical paths

## Test Markers

Use pytest markers to organize tests:

```python
@pytest.mark.slow
def test_large_dataset():
    """Test with large dataset."""
    pass

@pytest.mark.integration
def test_workflow():
    """Integration test."""
    pass

@pytest.mark.benchmark
def test_performance(benchmark):
    """Performance benchmark."""
    pass
```

**Run specific markers:**
```bash
# Skip slow tests
pytest -m "not slow"

# Run only integration tests
pytest -m integration

# Run only benchmarks
pytest -m benchmark --benchmark-only
```

## Troubleshooting

### Tests Won't Run

1. Check Python version (requires 3.8+)
2. Install dependencies: `pip install -r requirements.txt`
3. Install in development mode: `pip install -e .`

### Import Errors

```bash
# Verify installation
python -c "import playnite_py; print(playnite_py.__file__)"

# Reinstall
pip uninstall playnite_py
pip install -e .
```

### Flaky Tests

Tests should be deterministic:
- Use fixed random seeds
- Use in-memory databases
- Clean up resources
- Avoid time-dependent tests

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-benchmark](https://pytest-benchmark.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [Testing Best Practices](https://docs.python-guide.org/writing/tests/)
