"""
Integration tests for CLI commands.

Tests the CLI commands using Click's test runner.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from playnite_py.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory."""
    return tmp_path / "playnite_data"


class TestCLIVersion:
    """Tests for version command."""

    def test_version_command(self, runner: CliRunner):
        """Test version command."""
        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "version" in result.output.lower()

    def test_version_json(self, runner: CliRunner):
        """Test version command with JSON output."""
        result = runner.invoke(cli, ["--json", "version"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "version" in data


class TestCLIStatus:
    """Tests for status command."""

    def test_status_command(self, runner: CliRunner, temp_data_dir: Path):
        """Test status command."""
        result = runner.invoke(cli, ["--data-dir", str(temp_data_dir), "status"])
        assert result.exit_code == 0
        assert "Platform" in result.output or "platform" in result.output.lower()

    def test_status_json(self, runner: CliRunner, temp_data_dir: Path):
        """Test status command with JSON output."""
        result = runner.invoke(
            cli, ["--data-dir", str(temp_data_dir), "--json", "status"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "platform" in data


class TestCLIProfile:
    """Tests for profile commands."""

    def test_profile_create(self, runner: CliRunner, temp_data_dir: Path):
        """Test profile create command."""
        result = runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "create", "Test Profile"],
        )
        assert result.exit_code == 0
        assert "Test Profile" in result.output

    def test_profile_create_json(self, runner: CliRunner, temp_data_dir: Path):
        """Test profile create command with JSON output."""
        result = runner.invoke(
            cli,
            [
                "--data-dir", str(temp_data_dir),
                "--json",
                "profile", "create", "Test Profile",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert data["profile"]["name"] == "Test Profile"

    def test_profile_create_with_template(self, runner: CliRunner, temp_data_dir: Path):
        """Test profile create with template."""
        result = runner.invoke(
            cli,
            [
                "--data-dir", str(temp_data_dir),
                "profile", "create", "Kids Profile",
                "--template", "Kids",
            ],
        )
        assert result.exit_code == 0
        assert "Kids Profile" in result.output

    def test_profile_list(self, runner: CliRunner, temp_data_dir: Path):
        """Test profile list command."""
        # Create profiles first
        runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "create", "Profile 1"],
        )
        runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "create", "Profile 2"],
        )

        result = runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "list"],
        )
        assert result.exit_code == 0
        assert "Profile 1" in result.output
        assert "Profile 2" in result.output

    def test_profile_list_json(self, runner: CliRunner, temp_data_dir: Path):
        """Test profile list with JSON output."""
        runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "create", "Test"],
        )

        result = runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "--json", "profile", "list"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["name"] == "Test"

    def test_profile_info(self, runner: CliRunner, temp_data_dir: Path):
        """Test profile info command."""
        runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "create", "Test"],
        )

        result = runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "info", "Test"],
        )
        assert result.exit_code == 0
        assert "Test" in result.output

    def test_profile_switch(self, runner: CliRunner, temp_data_dir: Path):
        """Test profile switch command."""
        runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "create", "Test"],
        )

        result = runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "switch", "Test"],
        )
        assert result.exit_code == 0
        assert "Test" in result.output

    def test_profile_delete(self, runner: CliRunner, temp_data_dir: Path):
        """Test profile delete command."""
        runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "create", "Test"],
        )

        result = runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "delete", "Test", "--yes"],
        )
        assert result.exit_code == 0
        assert "Deleted" in result.output or "deleted" in result.output.lower()

    def test_profile_templates(self, runner: CliRunner, temp_data_dir: Path):
        """Test profile templates command."""
        result = runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "templates"],
        )
        assert result.exit_code == 0
        # Should show builtin templates
        assert "Default" in result.output or "default" in result.output.lower()

    def test_profile_set_default(self, runner: CliRunner, temp_data_dir: Path):
        """Test profile set-default command."""
        runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "create", "Test"],
        )

        result = runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "set-default", "Test"],
        )
        assert result.exit_code == 0


class TestCLIConfig:
    """Tests for configuration commands."""

    def test_config_detect(self, runner: CliRunner, temp_data_dir: Path):
        """Test config detect command."""
        result = runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "config", "detect"],
        )
        assert result.exit_code == 0
        assert "Platform" in result.output or "platform" in result.output.lower()

    def test_config_detect_json(self, runner: CliRunner, temp_data_dir: Path):
        """Test config detect with JSON output."""
        result = runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "--json", "config", "detect"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "platform" in data
        assert "os" in data

    def test_config_templates(self, runner: CliRunner, temp_data_dir: Path):
        """Test config templates command."""
        # Need active profile for config commands
        runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "create", "Test"],
        )
        runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "switch", "Test"],
        )

        result = runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "config", "templates"],
        )
        assert result.exit_code == 0
        # Should show builtin templates
        assert "Performance" in result.output or "performance" in result.output.lower()


class TestCLIGame:
    """Tests for game commands."""

    @pytest.fixture
    def active_profile(self, runner: CliRunner, temp_data_dir: Path):
        """Create and switch to a profile."""
        runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "create", "Test"],
        )
        runner.invoke(
            cli,
            ["--data-dir", str(temp_data_dir), "profile", "switch", "Test"],
        )
        return temp_data_dir

    def test_game_list_empty(self, runner: CliRunner, active_profile: Path):
        """Test game list command with no games."""
        result = runner.invoke(
            cli,
            ["--data-dir", str(active_profile), "game", "list"],
        )
        assert result.exit_code == 0
        assert "No games" in result.output or result.output.strip() == ""

    def test_game_add(self, runner: CliRunner, active_profile: Path, tmp_path: Path):
        """Test game add command."""
        # Create a fake executable
        exe_path = tmp_path / "game.exe"
        exe_path.touch()

        result = runner.invoke(
            cli,
            [
                "--data-dir", str(active_profile),
                "game", "add", "Test Game",
                "--path", str(exe_path),
            ],
        )
        assert result.exit_code == 0
        assert "Test Game" in result.output

    def test_game_add_json(self, runner: CliRunner, active_profile: Path, tmp_path: Path):
        """Test game add with JSON output."""
        exe_path = tmp_path / "game.exe"
        exe_path.touch()

        result = runner.invoke(
            cli,
            [
                "--data-dir", str(active_profile),
                "--json",
                "game", "add", "Test Game",
                "--path", str(exe_path),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert data["game"]["name"] == "Test Game"


class TestCLIHelp:
    """Tests for help output."""

    def test_main_help(self, runner: CliRunner):
        """Test main help command."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Playnite-Py" in result.output
        assert "profile" in result.output
        assert "config" in result.output

    def test_profile_help(self, runner: CliRunner):
        """Test profile help command."""
        result = runner.invoke(cli, ["profile", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output
        assert "list" in result.output
        assert "switch" in result.output

    def test_config_help(self, runner: CliRunner):
        """Test config help command."""
        result = runner.invoke(cli, ["config", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output
        assert "detect" in result.output

    def test_game_help(self, runner: CliRunner):
        """Test game help command."""
        result = runner.invoke(cli, ["game", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "add" in result.output
        assert "launch" in result.output
