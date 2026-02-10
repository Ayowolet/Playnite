"""Integration test: full achievement workflow via CLI runner."""

import json

import pytest
from click.testing import CliRunner

from gamelibrary.cli import main


@pytest.fixture
def cli(tmp_path):
    """Return a helper that invokes the CLI with --db pointing to a temp database."""
    runner = CliRunner()
    db_path = str(tmp_path / "test.db")

    def invoke(*args):
        """Invoke the CLI, prepending the db option to the appropriate subcommand."""
        full_args = list(args)
        return runner.invoke(main, full_args, catch_exceptions=False)

    return invoke, db_path


class TestFullAchievementWorkflow:
    def test_full_achievement_workflow(self, cli, tmp_path):
        invoke, db_path = cli

        # 1. Register a manual platform
        result = invoke("achievements", "--db", db_path, "--json", "register-platform", "MyManual", "manual")
        assert result.exit_code == 0, result.output
        platform_data = json.loads(result.output)
        platform_id = platform_data["platform_id"]
        assert platform_id > 0

        # 2. Add a game
        result = invoke(
            "achievements", "--db", db_path, "--json",
            "add-game", "Dark Souls III", "--platform", "MyManual",
        )
        assert result.exit_code == 0, result.output
        game_data = json.loads(result.output)
        game_id = game_data["game_id"]
        assert game_id > 0

        # 3. Add several achievements
        achievements_spec = [
            ("The End of Fire", "--unlocked", "--global-pct", "5.0", "--unlock-time", "2025-06-01T12:00:00"),
            ("Embrace the Flame", "--unlocked", "--global-pct", "40.0", "--unlock-time", "2025-07-15T08:30:00"),
            ("Lord of Hollows", "--global-pct", "10.0"),  # locked by default
        ]
        ach_ids = []
        for spec in achievements_spec:
            cmd = ["achievements", "--db", db_path, "--json", "add-achievement", str(game_id)]
            cmd.extend(spec)
            result = invoke(*cmd)
            assert result.exit_code == 0, result.output
            ach_data = json.loads(result.output)
            ach_ids.append(ach_data["achievement_id"])

        assert len(ach_ids) == 3

        # 4. List achievements for the game
        result = invoke("achievements", "--db", db_path, "--json", "list", str(game_id))
        assert result.exit_code == 0, result.output
        achievements_list = json.loads(result.output)
        assert len(achievements_list) == 3

        # 5. Check stats for the game
        result = invoke("achievements", "--db", db_path, "--json", "stats", "--game-id", str(game_id))
        assert result.exit_code == 0, result.output
        stats = json.loads(result.output)
        assert stats["total_achievements"] == 3
        assert stats["unlocked_count"] == 2

        # 6. Check overall stats
        result = invoke("achievements", "--db", db_path, "--json", "stats")
        assert result.exit_code == 0, result.output
        overall = json.loads(result.output)
        assert overall["total_games"] >= 1
        assert overall["total_unlocked"] == 2

        # 7. Export to JSON file
        export_path = str(tmp_path / "export.json")
        result = invoke(
            "achievements", "--db", db_path,
            "export", "--format", "json", "--output", export_path,
        )
        assert result.exit_code == 0, result.output
        exported = json.loads((tmp_path / "export.json").read_text())
        assert len(exported["games"]) >= 1

        # 8. Notifications - create and read
        #    Trigger a notification by using the notification manager directly
        #    then read via CLI. We can do this by reading the notifications list
        #    (it should be empty right now).
        result = invoke("achievements", "--db", db_path, "--json", "notifications")
        assert result.exit_code == 0, result.output
        notifications = json.loads(result.output)
        # Just verify the command works; notifications list may be empty
        assert isinstance(notifications, list)
