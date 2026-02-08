"""Integration tests for CLI workflows."""

import pytest
import tempfile
from pathlib import Path
from click.testing import CliRunner

from playnite_py.cli.main import cli
from playnite_py.database import init_database, get_session, GameOperations


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield str(db_path)


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


class TestLibraryWorkflow:
    """Test complete library management workflow."""

    def test_init_and_add_games(self, runner, temp_db):
        """Test initializing database and adding games."""
        # Initialize database
        result = runner.invoke(cli, ['--db-path', temp_db, 'init'])
        assert result.exit_code == 0

        # Add games
        result = runner.invoke(cli, [
            '--db-path', temp_db,
            'library', 'add', 'The Witcher 3',
            '--platform', 'PC',
            '--genre', 'RPG',
            '--release-date', '2015-05-19'
        ])
        assert result.exit_code == 0
        assert 'The Witcher 3' in result.output

        result = runner.invoke(cli, [
            '--db-path', temp_db,
            'library', 'add', 'Portal 2',
            '--platform', 'PC',
            '--genre', 'Puzzle'
        ])
        assert result.exit_code == 0

    def test_list_and_filter(self, runner, temp_db):
        """Test listing and filtering games."""
        # Setup
        runner.invoke(cli, ['--db-path', temp_db, 'init'])
        runner.invoke(cli, [
            '--db-path', temp_db,
            'library', 'add', 'Game 1',
            '--platform', 'PC', '--genre', 'RPG'
        ])
        runner.invoke(cli, [
            '--db-path', temp_db,
            'library', 'add', 'Game 2',
            '--platform', 'PS5', '--genre', 'Action'
        ])

        # List all games
        result = runner.invoke(cli, ['--db-path', temp_db, 'library', 'list'])
        assert result.exit_code == 0
        assert 'Game 1' in result.output
        assert 'Game 2' in result.output

        # Filter by platform
        result = runner.invoke(cli, [
            '--db-path', temp_db,
            'library', 'filter',
            '--platform', 'PC'
        ])
        assert result.exit_code == 0
        assert 'Game 1' in result.output

    def test_search(self, runner, temp_db):
        """Test searching games."""
        # Setup
        runner.invoke(cli, ['--db-path', temp_db, 'init'])
        runner.invoke(cli, [
            '--db-path', temp_db,
            'library', 'add', 'The Witcher 3'
        ])

        # Search
        result = runner.invoke(cli, [
            '--db-path', temp_db,
            'library', 'search', 'Witcher'
        ])
        assert result.exit_code == 0
        assert 'Witcher' in result.output

    def test_bulk_operations(self, runner, temp_db):
        """Test bulk editing games."""
        # Setup
        runner.invoke(cli, ['--db-path', temp_db, 'init'])

        # Add multiple games
        for i in range(3):
            runner.invoke(cli, [
                '--db-path', temp_db,
                'library', 'add', f'Game {i}'
            ])

        # Bulk edit (add tags)
        result = runner.invoke(cli, [
            '--db-path', temp_db,
            'library', 'bulk-edit', '1', '2', '3',
            '--tag', 'test-tag'
        ])
        assert result.exit_code == 0

    def test_smart_collection(self, runner, temp_db):
        """Test creating smart collection."""
        # Setup
        runner.invoke(cli, ['--db-path', temp_db, 'init'])
        runner.invoke(cli, [
            '--db-path', temp_db,
            'library', 'add', 'RPG Game',
            '--genre', 'RPG'
        ])

        # Create smart collection
        result = runner.invoke(cli, [
            '--db-path', temp_db,
            'library', 'create-smart-collection', 'RPG Collection',
            '--genre', 'RPG'
        ])
        assert result.exit_code == 0
        assert 'RPG Collection' in result.output

    def test_stats(self, runner, temp_db):
        """Test library statistics."""
        # Setup
        runner.invoke(cli, ['--db-path', temp_db, 'init'])
        runner.invoke(cli, [
            '--db-path', temp_db,
            'library', 'add', 'Test Game'
        ])

        # Get stats
        result = runner.invoke(cli, [
            '--db-path', temp_db,
            'library', 'stats'
        ])
        assert result.exit_code == 0
        assert 'Total Games' in result.output

    def test_json_output(self, runner, temp_db):
        """Test JSON output mode."""
        # Setup
        runner.invoke(cli, ['--db-path', temp_db, 'init'])
        runner.invoke(cli, [
            '--db-path', temp_db,
            'library', 'add', 'Test Game'
        ])

        # Get JSON output
        result = runner.invoke(cli, [
            '--db-path', temp_db,
            '--json-output',
            'library', 'list'
        ])
        assert result.exit_code == 0
        assert '{' in result.output  # JSON format


class TestControllerWorkflow:
    """Test controller system workflow."""

    def test_export_mappings(self, runner):
        """Test exporting controller mappings."""
        result = runner.invoke(cli, [
            'controller', 'export-mappings',
            '--format', 'json'
        ])
        assert result.exit_code == 0
        assert 'xbox' in result.output


class TestNavigationWorkflow:
    """Test navigation system workflow."""

    def test_init_navigation(self, runner):
        """Test initializing navigation."""
        result = runner.invoke(cli, [
            'navigation', 'init-state',
            '--state', 'game_grid'
        ])
        assert result.exit_code == 0

    def test_navigation_commands(self, runner):
        """Test executing navigation commands."""
        result = runner.invoke(cli, [
            'navigation', 'test-navigation',
            '--columns', '4',
            '--rows', '3',
            '--total-items', '20',
            '--command', 'right',
            '--command', 'down'
        ])
        assert result.exit_code == 0

    def test_show_states(self, runner):
        """Test showing available states."""
        result = runner.invoke(cli, [
            'navigation', 'show-states'
        ])
        assert result.exit_code == 0
        assert 'game_grid' in result.output

    def test_show_commands(self, runner):
        """Test showing available commands."""
        result = runner.invoke(cli, [
            'navigation', 'show-commands'
        ])
        assert result.exit_code == 0
        assert 'up' in result.output or 'down' in result.output
