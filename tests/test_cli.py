"""Tests for CLI commands with JSON output."""

import json
import os
import tempfile

import pytest

from playnite_py.cli import main, build_parser


class TestCLI:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()

    def _run(self, *args):
        """Run a CLI command and capture output."""
        import io
        import sys
        old_stdout = sys.stdout
        sys.stdout = buf = io.StringIO()
        try:
            ret = main(["--data-dir", self._tmpdir, "--json"] + list(args))
            output = buf.getvalue()
        finally:
            sys.stdout = old_stdout
        return ret, output

    def _run_json(self, *args):
        ret, output = self._run(*args)
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            data = output
        return ret, data

    def test_db_stats_empty(self):
        ret, data = self._run_json("db-stats")
        assert ret == 0
        assert data["total_games"] == 0

    def test_game_add_and_list(self):
        ret, data = self._run_json("game-add", "Test Game", "--source", "Steam")
        assert ret == 0
        assert data["name"] == "Test Game"
        game_id = data["id"]

        ret, data = self._run_json("game-list")
        assert ret == 0
        assert len(data) == 1
        assert data[0]["name"] == "Test Game"

        ret, data = self._run_json("game-show", game_id)
        assert ret == 0
        assert data["name"] == "Test Game"
        assert data["source"] == "Steam"

    def test_game_update(self):
        ret, data = self._run_json("game-add", "Original Name")
        game_id = data["id"]

        ret, data = self._run_json("game-update", game_id, "--name", "New Name")
        assert ret == 0

        ret, data = self._run_json("game-show", game_id)
        assert data["name"] == "New Name"

    def test_game_remove(self):
        ret, data = self._run_json("game-add", "To Remove")
        game_id = data["id"]

        ret, data = self._run_json("game-remove", game_id)
        assert ret == 0

        ret, data = self._run_json("game-list")
        assert len(data) == 0

    def test_action_inject_and_list(self):
        # Add a game first
        ret, data = self._run_json("game-add", "Action Game")
        game_id = data["id"]

        # Inject action
        ret, data = self._run_json(
            "action-inject", "Test Action",
            "--script", "print('hello')",
            "--game-id", game_id,
            "--phase", "pre_launch",
        )
        assert ret == 0
        action_id = data["id"]

        # List actions
        ret, data = self._run_json("action-list")
        assert ret == 0
        assert len(data) == 1

    def test_action_execute(self):
        ret, data = self._run_json("game-add", "Execute Game")
        game_id = data["id"]

        self._run_json(
            "action-inject", "Execute Test",
            "--script", "print('executed')",
            "--game-id", game_id,
        )

        ret, data = self._run_json("action-execute", game_id, "pre_launch")
        assert ret == 0
        assert data["all_succeeded"] is True
        assert len(data["results"]) == 1

    def test_action_templates(self):
        ret, data = self._run_json("action-templates")
        assert ret == 0
        assert len(data) > 0
        names = [t["name"] for t in data]
        assert "Close Background Apps" in names

    def test_script_list_empty(self):
        ret, data = self._run_json("script-list")
        assert ret == 0
        assert len(data) == 0

    def test_script_load_with_example(self):
        # Copy example script to data dir
        import shutil
        ext_dir = os.path.join(self._tmpdir, "extensions")
        example_src = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "extensions", "examples", "playtime_tracker",
        )
        if os.path.exists(example_src):
            shutil.copytree(example_src, os.path.join(ext_dir, "playtime_tracker"))

            ret, data = self._run_json("script-list")
            assert ret == 0
            assert len(data) >= 1
            assert any(s["name"] == "Playtime Tracker" for s in data)

    def test_profile_commands(self):
        ret, data = self._run_json("profile-list")
        assert ret == 0
        assert len(data) == 0

    def test_monitor_status(self):
        ret, data = self._run_json("monitor-status")
        assert ret == 0

    def test_no_command_shows_help(self):
        import io
        import sys
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            ret = main(["--data-dir", self._tmpdir])
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
        assert ret == 0

    def test_json_error_output(self):
        ret, data = self._run_json("game-show", "nonexistent-id")
        assert ret == 0  # Command doesn't crash
        assert "error" in data
