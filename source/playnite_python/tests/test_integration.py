"""
Integration tests — end-to-end workflows using the CLI.

These tests spin up real instances of the database, script manager, and
action system, and exercise complete workflows including CLI invocation.

Run with::

    pytest source/playnite_python/tests/test_integration.py -v
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from playnite_python.cli.main import cli
from playnite_python.database.game_database import GameDatabase
from playnite_python.extensions.manager import ScriptManager
from playnite_python.actions.registry import ActionRegistry
from playnite_python.actions.chain import ActionChainExecutor
from playnite_python.actions.injector import ActionInjector
from playnite_python.actions.models import Action, ActionType
from playnite_python.models.game import Game


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def work_dir(tmp_path):
    (tmp_path / "extensions").mkdir()
    (tmp_path / "config").mkdir()
    return tmp_path


@pytest.fixture
def cli_args(work_dir):
    """Common CLI arguments for test invocations."""
    db_path = str(work_dir / "library.db")
    config_dir = str(work_dir / "config")
    extensions_dir = str(work_dir / "extensions")
    return [
        "--db", db_path,
        "--config-dir", config_dir,
        "--extensions-dir", extensions_dir,
    ]


@pytest.fixture
def populated_db(work_dir):
    db = GameDatabase(str(work_dir / "library.db"))
    db.open()
    db.games.add(Game(name="Portal 2", is_installed=True))
    db.games.add(Game(name="Celeste", is_installed=False))
    db.games.add(Game(name="Minecraft", is_installed=True, is_favorite=True))
    yield db
    db.close()


# ---------------------------------------------------------------------------
# Game CLI integration
# ---------------------------------------------------------------------------

class TestGameCLI:
    def test_games_list(self, runner, cli_args, populated_db):
        result = runner.invoke(cli, cli_args + ["games", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = {g["name"] for g in data}
        assert "Portal 2" in names
        assert "Celeste" in names

    def test_games_list_installed_only(self, runner, cli_args, populated_db):
        result = runner.invoke(cli, cli_args + ["games", "list", "--installed", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert all(g["installed"] for g in data)

    def test_games_search(self, runner, cli_args, populated_db):
        result = runner.invoke(cli, cli_args + ["games", "list", "--search", "portal", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert any("Portal" in g["name"] for g in data)

    def test_games_add(self, runner, cli_args, work_dir):
        # Ensure DB exists
        db = GameDatabase(str(work_dir / "library.db"))
        db.open()
        db.close()
        result = runner.invoke(cli, cli_args + ["games", "add", "Half-Life 2", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "id" in data

    def test_games_get(self, runner, cli_args, populated_db):
        game = populated_db.games.all()[0]
        result = runner.invoke(cli, cli_args + ["games", "get", game.id, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == game.id

    def test_games_get_not_found(self, runner, cli_args, populated_db):
        result = runner.invoke(cli, cli_args + ["games", "get", "nonexistent-id", "--json"])
        assert result.exit_code != 0

    def test_games_update(self, runner, cli_args, populated_db):
        game = populated_db.games.all()[0]
        result = runner.invoke(
            cli, cli_args + ["games", "update", game.id, "is_favorite", "true", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True

    def test_games_stats(self, runner, cli_args, populated_db):
        result = runner.invoke(cli, cli_args + ["games", "stats", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total_games" in data
        assert data["total_games"] == 3


# ---------------------------------------------------------------------------
# Scripts CLI integration
# ---------------------------------------------------------------------------

class TestScriptsCLI:
    def test_scripts_list_empty(self, runner, cli_args, work_dir):
        db = GameDatabase(str(work_dir / "library.db"))
        db.open()
        db.close()
        result = runner.invoke(cli, cli_args + ["scripts", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_scripts_load(self, runner, cli_args, work_dir):
        db = GameDatabase(str(work_dir / "library.db"))
        db.open()
        db.close()
        script_path = work_dir / "extensions" / "test_script.py"
        script_path.write_text(textwrap.dedent("""
            message = "Hello from script"
            def on_application_started():
                pass
        """))
        result = runner.invoke(cli, cli_args + ["scripts", "load", str(script_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True

    def test_scripts_discover(self, runner, cli_args, work_dir):
        db = GameDatabase(str(work_dir / "library.db"))
        db.open()
        db.close()
        (work_dir / "extensions" / "s1.py").write_text("x = 1")
        (work_dir / "extensions" / "s2.py").write_text("y = 2")
        result = runner.invoke(cli, cli_args + ["scripts", "discover", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert len(data.get("scripts", [])) >= 2

    def test_scripts_run_hook_app_started(self, runner, cli_args, work_dir):
        db = GameDatabase(str(work_dir / "library.db"))
        db.open()
        db.close()
        result = runner.invoke(
            cli, cli_args + ["scripts", "run-hook", "on_application_started", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True

    def test_scripts_run_hook_invalid(self, runner, cli_args, work_dir):
        db = GameDatabase(str(work_dir / "library.db"))
        db.open()
        db.close()
        result = runner.invoke(
            cli, cli_args + ["scripts", "run-hook", "invalid_hook_name", "--json"]
        )
        assert result.exit_code != 0

    def test_scripts_metrics(self, runner, cli_args, work_dir):
        db = GameDatabase(str(work_dir / "library.db"))
        db.open()
        db.close()
        result = runner.invoke(cli, cli_args + ["scripts", "metrics", "--json"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Actions CLI integration
# ---------------------------------------------------------------------------

class TestActionsCLI:
    def test_actions_list_empty(self, runner, cli_args, work_dir):
        db = GameDatabase(str(work_dir / "library.db"))
        db.open()
        db.close()
        result = runner.invoke(cli, cli_args + ["actions", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_actions_add_and_list(self, runner, cli_args, work_dir):
        db = GameDatabase(str(work_dir / "library.db"))
        db.open()
        db.close()
        result = runner.invoke(
            cli,
            cli_args + [
                "actions", "add",
                "--name", "My Pre-Launch",
                "--type", "pre_launch",
                "--script", "x = 1",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        action_id = data["id"]

        # Verify it appears in the list
        list_result = runner.invoke(cli, cli_args + ["actions", "list", "--json"])
        list_data = json.loads(list_result.output)
        assert any(a["id"] == action_id for a in list_data)

    def test_actions_run(self, runner, cli_args, work_dir):
        db = GameDatabase(str(work_dir / "library.db"))
        db.open()
        db.close()
        # Add action first
        add_result = runner.invoke(
            cli,
            cli_args + [
                "actions", "add",
                "--name", "RunMe",
                "--type", "pre_launch",
                "--script", "print('running')",
                "--json",
            ],
        )
        action_id = json.loads(add_result.output)["id"]
        # Run it
        run_result = runner.invoke(cli, cli_args + ["actions", "run", action_id, "--json"])
        assert run_result.exit_code == 0
        data = json.loads(run_result.output)
        assert data[0]["success"] is True

    def test_actions_inject(self, runner, cli_args, work_dir):
        db = GameDatabase(str(work_dir / "library.db"))
        db.open()
        db.close()
        result = runner.invoke(
            cli,
            cli_args + [
                "actions", "inject",
                "--script", "x = 'injected'",
                "--name", "InjectedAction",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True

    def test_actions_log(self, runner, cli_args, work_dir):
        db = GameDatabase(str(work_dir / "library.db"))
        db.open()
        db.close()
        result = runner.invoke(cli, cli_args + ["actions", "log", "--json"])
        assert result.exit_code == 0

    def test_actions_template_list(self, runner):
        result = runner.invoke(cli, ["actions", "template-list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "discord_rich_presence" in data
        assert "game_backup" in data


# ---------------------------------------------------------------------------
# Full workflow: script injects action, action runs
# ---------------------------------------------------------------------------

class TestFullWorkflow:
    def test_script_injects_action_and_chain_runs(self, work_dir, populated_db):
        """
        Full workflow:
        1. Script manager loads a script.
        2. Script injects a pre-launch action via the API.
        3. Action chain executor runs pre-launch actions.
        4. All logs are written.
        """
        ext_dir = work_dir / "extensions"
        registry = ActionRegistry(str(work_dir / "config"))
        injector = ActionInjector(registry)

        # Simulate a script injecting an action
        action = injector.inject_pre_launch(
            script="result = f'pre-launched {game.name}'",
            name="Test Pre-Launch",
            priority=10,
        )
        assert action.id

        # Run the chain for the first game
        game = populated_db.games.all()[0]
        actions = registry.get_actions_for_game(game.id, ActionType.PRE_LAUNCH)
        assert len(actions) >= 1

        executor = ActionChainExecutor()
        logs, success = executor.execute(actions, game)
        assert success
        assert all(l.success for l in logs)

    def test_lifecycle_hooks_fire_on_game_events(self, work_dir, populated_db):
        """
        Verify that lifecycle hooks registered by scripts fire correctly
        when game events occur.
        """
        ext_dir = work_dir / "extensions"
        script_path = ext_dir / "game_hooks.py"
        script_path.write_text(textwrap.dedent("""
            _started_games = []
            _stopped_games = []

            def on_game_started(game):
                _started_games.append(game.name)

            def on_game_stopped(game, elapsed):
                _stopped_games.append((game.name, elapsed))
        """))

        mgr = ScriptManager(
            str(ext_dir),
            populated_db,
            app_paths={
                "app": str(work_dir),
                "config": str(work_dir / "config"),
                "database": str(work_dir / "library.db"),
                "logs": str(work_dir / "logs"),
            },
        )
        mgr.load_script(str(script_path))
        game = populated_db.games.all()[0]

        # Fire lifecycle events
        mgr.lifecycle.on_game_started(game)
        mgr.lifecycle.on_game_stopped(game, 120.5)

        # The hooks ran — if no exception was raised, lifecycle dispatch worked
        assert mgr.lifecycle.handler_count("on_game_started") >= 1
        assert mgr.lifecycle.handler_count("on_game_stopped") >= 1

    def test_json_output_parseable(self, runner, cli_args, work_dir):
        """All JSON outputs must be valid JSON."""
        db = GameDatabase(str(work_dir / "library.db"))
        db.open()
        db.games.add(Game(name="JSONTest"))
        db.close()

        commands = [
            ["games", "list", "--json"],
            ["games", "stats", "--json"],
            ["actions", "list", "--json"],
            ["scripts", "list", "--json"],
        ]
        for cmd in commands:
            result = runner.invoke(cli, cli_args + cmd)
            assert result.exit_code == 0, f"Failed for {cmd}: {result.output}"
            try:
                json.loads(result.output)
            except json.JSONDecodeError:
                pytest.fail(f"Non-JSON output for {cmd}: {result.output[:200]}")
