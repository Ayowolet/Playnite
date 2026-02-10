"""Tests for achievement CLI operations.

Covers 10 checklist items:
  1. Import achievements via CLI
  2. List all achievements via CLI
  3. Filter achievements by game via CLI
  4. View completion statistics via CLI
  5. Identify rare achievements via CLI
  6. Add manual achievement via CLI
  7. Mark achievement as unlocked via CLI
  8. Export achievement data via CLI
  9. Sync achievements via CLI
  10. View achievement timeline via CLI
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from gamelibrary.database import Database
from gamelibrary.achievements.cli import achievements_cli
from gamelibrary.achievements.tracker import AchievementTracker
from gamelibrary.achievements.platforms.base import PlatformGame, PlatformAchievement


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _invoke(runner: CliRunner, db_path: str, args: list[str], as_json: bool = True):
    """Invoke a CLI command with --db and optionally --json."""
    base = ["--db", db_path]
    if as_json:
        base.append("--json")
    return runner.invoke(achievements_cli, base + args, catch_exceptions=False)


def _seed_platform_and_game(db: Database) -> tuple[int, int]:
    """Register a manual platform and add a game. Returns (platform_id, game_id)."""
    tracker = AchievementTracker(db)
    pid = tracker.register_platform("TestManual", "manual", {"platform_label": "TestManual"})
    gid = tracker.add_manual_game("TestManual", "Test Game")
    return pid, gid


def _seed_achievements(db: Database, game_id: int) -> list[int]:
    """Add a spread of achievements (3 unlocked, 2 locked). Returns achievement IDs."""
    tracker = AchievementTracker(db)
    ids = []
    # Ultra rare, unlocked
    ids.append(tracker.add_manual_achievement(
        game_id, "Ultra Rare Trophy", "Only 5% earned this",
        unlocked=True, unlock_time="2025-06-01T12:00:00", global_pct=5.0,
    ))
    # Rare, unlocked
    ids.append(tracker.add_manual_achievement(
        game_id, "Rare Trophy", "Only 15% earned this",
        unlocked=True, unlock_time="2025-07-15T08:30:00", global_pct=15.0,
    ))
    # Uncommon, unlocked
    ids.append(tracker.add_manual_achievement(
        game_id, "Uncommon Trophy", "45% earned this",
        unlocked=True, unlock_time="2025-08-20T18:00:00", global_pct=45.0,
    ))
    # Common, locked
    ids.append(tracker.add_manual_achievement(
        game_id, "Common Trophy", "75% earned this",
        unlocked=False, global_pct=75.0,
    ))
    # Very common, locked
    ids.append(tracker.add_manual_achievement(
        game_id, "Very Common Trophy", "95% earned this",
        unlocked=False, global_pct=95.0,
    ))
    return ids


@pytest.fixture
def cli_env(tmp_path):
    """Create a temporary database with seeded data and return (runner, db_path, platform_id, game_id, ach_ids)."""
    db_path = str(tmp_path / "test.db")
    db = Database(db_path)
    pid, gid = _seed_platform_and_game(db)
    ach_ids = _seed_achievements(db, gid)
    runner = CliRunner()
    return runner, db_path, pid, gid, ach_ids


# ===========================================================================
# 1. Import achievements via CLI
# ===========================================================================

class TestImportAchievementsViaCLI:
    """CLI: achievements import <platform_id>"""

    def test_import_runs_successfully(self, cli_env, monkeypatch):
        """Import command completes and returns sync summary."""
        runner, db_path, pid, gid, _ = cli_env

        # Monkeypatch ManualProvider to return simulated game + achievements
        from gamelibrary.achievements.platforms import manual as manual_mod

        _orig_get_games = manual_mod.ManualProvider.get_games
        _orig_get_achievements = manual_mod.ManualProvider.get_achievements

        def fake_get_games(self):
            return [PlatformGame(external_id="sim_001", name="Simulated Game", total_achievements=2)]

        def fake_get_achievements(self, game_external_id):
            return [
                PlatformAchievement(
                    external_id="ach_a", name="First Blood",
                    description="Win your first match",
                    global_completion_pct=80.0, unlocked=True,
                    unlock_time="2025-09-01T10:00:00",
                ),
                PlatformAchievement(
                    external_id="ach_b", name="Sharpshooter",
                    description="Get 100 headshots",
                    global_completion_pct=12.0, unlocked=False,
                ),
            ]

        monkeypatch.setattr(manual_mod.ManualProvider, "get_games", fake_get_games)
        monkeypatch.setattr(manual_mod.ManualProvider, "get_achievements", fake_get_achievements)

        result = _invoke(runner, db_path, ["import", str(pid)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "completed"
        assert data["achievements_found"] == 2
        assert data["games_processed"] == 1

    def test_import_records_new_unlocks(self, cli_env, monkeypatch):
        """Import detects newly unlocked achievements."""
        runner, db_path, pid, gid, _ = cli_env

        from gamelibrary.achievements.platforms import manual as manual_mod

        def fake_get_games(self):
            return [PlatformGame(external_id="sim_002", name="Another Game", total_achievements=1)]

        def fake_get_achievements(self, game_external_id):
            return [
                PlatformAchievement(
                    external_id="ach_x", name="Newcomer",
                    global_completion_pct=90.0, unlocked=True,
                    unlock_time="2025-10-01T00:00:00",
                ),
            ]

        monkeypatch.setattr(manual_mod.ManualProvider, "get_games", fake_get_games)
        monkeypatch.setattr(manual_mod.ManualProvider, "get_achievements", fake_get_achievements)

        result = _invoke(runner, db_path, ["import", str(pid)])
        data = json.loads(result.output)
        assert data["new_unlocks"] >= 1

    def test_import_single_game(self, cli_env, monkeypatch):
        """Import with --game-id imports a single game."""
        runner, db_path, pid, gid, _ = cli_env

        from gamelibrary.achievements.platforms import manual as manual_mod

        def fake_get_games(self):
            return [PlatformGame(external_id="sg_001", name="Single Game")]

        def fake_get_achievements(self, game_external_id):
            return [
                PlatformAchievement(
                    external_id="sg_ach_1", name="Solo Victory",
                    global_completion_pct=50.0, unlocked=True,
                    unlock_time="2025-11-01T00:00:00",
                ),
            ]

        monkeypatch.setattr(manual_mod.ManualProvider, "get_games", fake_get_games)
        monkeypatch.setattr(manual_mod.ManualProvider, "get_achievements", fake_get_achievements)

        result = _invoke(runner, db_path, ["import", str(pid), "--game-id", "sg_001"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["achievements_found"] == 1
        assert data["game_name"] == "Single Game"


# ===========================================================================
# 2. List all achievements via CLI
# ===========================================================================

class TestListAchievementsViaCLI:
    """CLI: achievements list <game_id>"""

    def test_list_all_achievements(self, cli_env):
        """List command returns all achievements for a game."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["list", str(gid)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 5

    def test_list_shows_achievement_names(self, cli_env):
        """Each achievement entry includes its name."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["list", str(gid)])
        data = json.loads(result.output)
        names = {a["name"] for a in data}
        assert "Ultra Rare Trophy" in names
        assert "Common Trophy" in names

    def test_list_includes_unlock_status(self, cli_env):
        """Each achievement shows whether it's unlocked."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["list", str(gid)])
        data = json.loads(result.output)
        unlocked_count = sum(1 for a in data if a.get("unlocked"))
        assert unlocked_count == 3


# ===========================================================================
# 3. Filter achievements by game via CLI
# ===========================================================================

class TestFilterAchievementsByGameViaCLI:
    """CLI: achievements list <game_id> --unlocked-only and per-game filtering."""

    def test_unlocked_only_filter(self, cli_env):
        """--unlocked-only returns only unlocked achievements."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["list", str(gid), "--unlocked-only"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 3
        assert all(a["unlocked"] for a in data)

    def test_filter_by_different_game(self, cli_env):
        """Listing achievements for a different game returns its own achievements."""
        runner, db_path, pid, gid, ach_ids = cli_env
        # Add a second game with 1 achievement
        db = Database(db_path)
        tracker = AchievementTracker(db)
        gid2 = tracker.add_manual_game("TestManual", "Second Game")
        tracker.add_manual_achievement(gid2, "Only One", global_pct=50.0)

        result = _invoke(runner, db_path, ["list", str(gid2)])
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "Only One"

    def test_games_command_lists_tracked_games(self, cli_env):
        """The games command lists all tracked games."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["games"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) >= 1
        assert any(g["name"] == "Test Game" for g in data)


# ===========================================================================
# 4. View completion statistics via CLI
# ===========================================================================

class TestViewCompletionStatsViaCLI:
    """CLI: achievements stats [--game-id <id>]"""

    def test_game_stats(self, cli_env):
        """Per-game stats show completion percentage."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["stats", "--game-id", str(gid)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["completion_pct"] == 60.0  # 3/5
        assert data["total_achievements"] == 5
        assert data["unlocked_count"] == 3

    def test_overall_stats(self, cli_env):
        """Overall stats aggregate across all games."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["stats"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_achievements"] == 5
        assert data["total_unlocked"] == 3
        assert "overall_completion_pct" in data

    def test_velocity_command(self, cli_env):
        """Velocity command returns unlock rate periods."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["velocity"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "last_30_days" in data

    def test_difficulty_distribution(self, cli_env):
        """Difficulty command returns distribution by tier."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["difficulty"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Keys are lowercase tier names from DifficultyTier enum values
        assert "common" in data or "ultra_rare" in data


# ===========================================================================
# 5. Identify rare achievements via CLI
# ===========================================================================

class TestIdentifyRareAchievementsViaCLI:
    """CLI: achievements hunt-rare [--threshold] [--unlocked-only]"""

    def test_hunt_rare_default_threshold(self, cli_env):
        """hunt-rare with default threshold (10%) finds ultra-rare achievements."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["hunt-rare"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Only the 5% achievement is below 10%
        assert len(data) == 1
        assert data[0]["name"] == "Ultra Rare Trophy"
        assert data[0]["global_completion_pct"] == 5.0

    def test_hunt_rare_custom_threshold(self, cli_env):
        """hunt-rare with raised threshold finds more achievements."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["hunt-rare", "--threshold", "20.0"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # 5% and 15% are both below 20%
        assert len(data) == 2
        names = {a["name"] for a in data}
        assert "Ultra Rare Trophy" in names
        assert "Rare Trophy" in names

    def test_hunt_rare_unlocked_only(self, cli_env):
        """hunt-rare --unlocked-only only shows rare achievements the user has earned."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["hunt-rare", "--threshold", "50.0", "--unlocked-only"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert all(a["unlocked"] for a in data)
        # Ultra Rare (5%), Rare (15%), Uncommon (45%) are all < 50% and unlocked
        assert len(data) == 3

    def test_hunt_rare_shows_game_and_platform(self, cli_env):
        """Rare achievement results include game and platform names."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["hunt-rare"])
        data = json.loads(result.output)
        assert data[0]["game_name"] == "Test Game"
        assert data[0]["platform"] == "TestManual"


# ===========================================================================
# 6. Add manual achievement via CLI
# ===========================================================================

class TestAddManualAchievementViaCLI:
    """CLI: achievements add-game + achievements add-achievement"""

    def test_add_game_via_cli(self, tmp_path):
        """add-game creates a new game entry."""
        db_path = str(tmp_path / "test.db")
        Database(db_path)  # initialize schema
        runner = CliRunner()

        result = _invoke(runner, db_path, ["add-game", "My Switch Game", "--platform", "Nintendo Switch"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "My Switch Game"
        assert data["platform"] == "Nintendo Switch"
        assert "game_id" in data

    def test_add_achievement_via_cli(self, tmp_path):
        """add-achievement creates a new achievement for a game."""
        db_path = str(tmp_path / "test.db")
        db = Database(db_path)
        _, gid = _seed_platform_and_game(db)
        runner = CliRunner()

        result = _invoke(runner, db_path, [
            "add-achievement", str(gid), "Speedrunner",
            "--description", "Beat the game in under 2 hours",
            "--global-pct", "8.5",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "Speedrunner"
        assert data["game_id"] == gid

    def test_add_achievement_unlocked(self, tmp_path):
        """add-achievement with --unlocked creates an already-unlocked achievement."""
        db_path = str(tmp_path / "test.db")
        db = Database(db_path)
        _, gid = _seed_platform_and_game(db)
        runner = CliRunner()

        result = _invoke(runner, db_path, [
            "add-achievement", str(gid), "Completionist",
            "--unlocked",
            "--unlock-time", "2025-12-25T00:00:00",
            "--global-pct", "3.0",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["achievement_id"] > 0

        # Verify it's actually unlocked in the DB
        result2 = _invoke(runner, db_path, ["list", str(gid), "--unlocked-only"])
        unlocked = json.loads(result2.output)
        assert any(a["name"] == "Completionist" for a in unlocked)

    def test_add_achievement_with_progress(self, tmp_path):
        """add-achievement with progress tracking fields."""
        db_path = str(tmp_path / "test.db")
        db = Database(db_path)
        _, gid = _seed_platform_and_game(db)
        runner = CliRunner()

        result = _invoke(runner, db_path, [
            "add-achievement", str(gid), "Collector",
            "--max-progress", "100",
            "--current-progress", "42",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["achievement_id"] > 0


# ===========================================================================
# 7. Mark achievement as unlocked via CLI
# ===========================================================================

class TestMarkAchievementUnlockedViaCLI:
    """CLI: achievements update-achievement <id> --unlocked"""

    def test_mark_locked_achievement_as_unlocked(self, cli_env):
        """update-achievement --unlocked marks a locked achievement as unlocked."""
        runner, db_path, pid, gid, ach_ids = cli_env
        locked_id = ach_ids[3]  # Common Trophy, locked

        result = _invoke(runner, db_path, [
            "update-achievement", str(locked_id),
            "--unlocked",
            "--unlock-time", "2025-12-01T15:00:00",
        ], as_json=False)
        assert result.exit_code == 0
        assert "updated" in result.output.lower()

        # Verify the achievement is now unlocked
        list_result = _invoke(runner, db_path, ["list", str(gid), "--unlocked-only"])
        unlocked = json.loads(list_result.output)
        assert any(a["name"] == "Common Trophy" for a in unlocked)

    def test_relock_achievement(self, cli_env):
        """update-achievement --locked re-locks an unlocked achievement."""
        runner, db_path, pid, gid, ach_ids = cli_env
        unlocked_id = ach_ids[0]  # Ultra Rare Trophy, unlocked

        result = _invoke(runner, db_path, [
            "update-achievement", str(unlocked_id), "--locked",
        ], as_json=False)
        assert result.exit_code == 0

        # Verify it's no longer in unlocked list
        list_result = _invoke(runner, db_path, ["list", str(gid), "--unlocked-only"])
        unlocked = json.loads(list_result.output)
        assert not any(a["name"] == "Ultra Rare Trophy" for a in unlocked)

    def test_update_progress_via_cli(self, cli_env):
        """update-achievement --progress updates the current progress."""
        runner, db_path, pid, gid, ach_ids = cli_env

        # First add a progress-tracked achievement
        db = Database(db_path)
        tracker = AchievementTracker(db)
        prog_id = tracker.add_manual_achievement(
            gid, "Kill Count", max_progress=500, current_progress=100, global_pct=30.0,
        )

        result = _invoke(runner, db_path, [
            "update-achievement", str(prog_id), "--progress", "250",
        ], as_json=False)
        assert result.exit_code == 0

        # Verify progress updated
        list_result = _invoke(runner, db_path, ["list", str(gid)])
        data = json.loads(list_result.output)
        ach = next(a for a in data if a["name"] == "Kill Count")
        assert ach["current_progress"] == 250

    def test_update_name_and_description(self, cli_env):
        """update-achievement --name/--description edits definition fields."""
        runner, db_path, pid, gid, ach_ids = cli_env
        target_id = ach_ids[4]  # Very Common Trophy

        result = _invoke(runner, db_path, [
            "update-achievement", str(target_id),
            "--name", "Renamed Trophy",
            "--description", "Updated description",
        ], as_json=False)
        assert result.exit_code == 0

        list_result = _invoke(runner, db_path, ["list", str(gid)])
        data = json.loads(list_result.output)
        ach = next(a for a in data if a["id"] == target_id)
        assert ach["name"] == "Renamed Trophy"
        assert ach["description"] == "Updated description"


# ===========================================================================
# 8. Export achievement data via CLI
# ===========================================================================

class TestExportAchievementDataViaCLI:
    """CLI: achievements export --format json/csv [--output <path>] [--game-id <id>]"""

    def test_export_json_to_stdout(self, cli_env):
        """Export JSON without --output prints to stdout."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["export", "--format", "json"], as_json=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "games" in data
        assert len(data["games"]) >= 1
        assert len(data["games"][0]["achievements"]) == 5

    def test_export_csv_to_stdout(self, cli_env):
        """Export CSV without --output prints to stdout."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["export", "--format", "csv"], as_json=False)
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert len(lines) >= 6  # header + 5 achievements
        assert "game_name" in lines[0]  # CSV header

    def test_export_json_to_file(self, cli_env, tmp_path):
        """Export JSON to a file creates the file with valid JSON."""
        runner, db_path, pid, gid, ach_ids = cli_env
        out = str(tmp_path / "export.json")
        result = _invoke(runner, db_path, ["export", "--format", "json", "--output", out], as_json=False)
        assert result.exit_code == 0
        assert "Exported to" in result.output

        from pathlib import Path
        content = json.loads(Path(out).read_text())
        assert "exported_at" in content
        assert len(content["games"]) >= 1

    def test_export_csv_to_file(self, cli_env, tmp_path):
        """Export CSV to a file creates a valid CSV."""
        runner, db_path, pid, gid, ach_ids = cli_env
        out = str(tmp_path / "export.csv")
        result = _invoke(runner, db_path, ["export", "--format", "csv", "--output", out], as_json=False)
        assert result.exit_code == 0

        from pathlib import Path
        content = Path(out).read_text()
        lines = content.strip().split("\n")
        assert len(lines) >= 6

    def test_export_filtered_by_game(self, cli_env):
        """Export with --game-id only includes that game's achievements."""
        runner, db_path, pid, gid, ach_ids = cli_env

        # Add a second game with different achievements
        db = Database(db_path)
        tracker = AchievementTracker(db)
        gid2 = tracker.add_manual_game("TestManual", "Other Game")
        tracker.add_manual_achievement(gid2, "Other Achievement")

        result = _invoke(runner, db_path, ["export", "--format", "json", "--game-id", str(gid)], as_json=False)
        data = json.loads(result.output)
        assert len(data["games"]) == 1
        assert data["games"][0]["name"] == "Test Game"


# ===========================================================================
# 9. Sync achievements via CLI
# ===========================================================================

class TestSyncAchievementsViaCLI:
    """CLI: achievements sync [--platform-id <id>]"""

    def test_sync_all_runs(self, cli_env, monkeypatch):
        """sync command without --platform-id syncs all non-manual platforms."""
        runner, db_path, pid, gid, ach_ids = cli_env

        # Register a second (non-manual) platform that we monkeypatch
        db = Database(db_path)
        tracker = AchievementTracker(db)
        tracker.register_platform(
            "MySteam", "steam", {"api_key": "fake", "steam_id": "12345"},
        )

        from gamelibrary.achievements.platforms import steam as steam_mod

        def fake_get_games(self):
            return [PlatformGame(external_id="app_100", name="Steam Game", total_achievements=1)]

        def fake_get_achievements(self, game_external_id):
            return [
                PlatformAchievement(
                    external_id="steam_ach_1", name="Steam Win",
                    global_completion_pct=60.0, unlocked=True,
                    unlock_time="2025-11-15T00:00:00",
                ),
            ]

        monkeypatch.setattr(steam_mod.SteamProvider, "get_games", fake_get_games)
        monkeypatch.setattr(steam_mod.SteamProvider, "get_achievements", fake_get_achievements)

        result = _invoke(runner, db_path, ["sync"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # sync_all skips manual platforms, so only Steam is synced
        assert len(data) == 1
        assert data[0]["status"] == "completed"
        assert data[0]["platform"] == "MySteam"

    def test_sync_specific_platform(self, cli_env, monkeypatch):
        """sync --platform-id syncs a single platform."""
        runner, db_path, pid, gid, ach_ids = cli_env

        from gamelibrary.achievements.platforms import manual as manual_mod

        def fake_get_games(self):
            return [PlatformGame(external_id="sync_g1", name="Sync Game")]

        def fake_get_achievements(self, game_external_id):
            return [
                PlatformAchievement(
                    external_id="sync_a1", name="Synced Trophy",
                    global_completion_pct=40.0, unlocked=True,
                    unlock_time="2025-12-01T00:00:00",
                ),
            ]

        monkeypatch.setattr(manual_mod.ManualProvider, "get_games", fake_get_games)
        monkeypatch.setattr(manual_mod.ManualProvider, "get_achievements", fake_get_achievements)

        result = _invoke(runner, db_path, ["sync", "--platform-id", str(pid)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "completed"
        assert data["achievements_found"] == 1

    def test_sync_history_recorded(self, cli_env, monkeypatch):
        """After sync, sync-history shows the record."""
        runner, db_path, pid, gid, ach_ids = cli_env

        from gamelibrary.achievements.platforms import manual as manual_mod

        def fake_get_games(self):
            return [PlatformGame(external_id="hist_g", name="History Game")]

        def fake_get_achievements(self, game_external_id):
            return []

        monkeypatch.setattr(manual_mod.ManualProvider, "get_games", fake_get_games)
        monkeypatch.setattr(manual_mod.ManualProvider, "get_achievements", fake_get_achievements)

        _invoke(runner, db_path, ["sync", "--platform-id", str(pid)])

        result = _invoke(runner, db_path, ["sync-history", "--limit", "5"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) >= 1
        assert data[0]["status"] == "completed"


# ===========================================================================
# 10. View achievement timeline via CLI
# ===========================================================================

class TestViewAchievementTimelineViaCLI:
    """CLI: achievements timeline [--days <n>]"""

    def test_timeline_returns_data(self, cli_env):
        """Timeline command returns daily unlock counts."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["timeline", "--days", "365"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # We have 3 unlocked achievements on 3 different dates
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_timeline_entries_have_date_and_count(self, cli_env):
        """Each timeline entry has a date and count field."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["timeline", "--days", "365"])
        data = json.loads(result.output)
        for entry in data:
            assert "date" in entry
            assert "count" in entry
            assert entry["count"] > 0

    def test_timeline_dates_are_distinct(self, cli_env):
        """Timeline groups by day — dates should be unique."""
        runner, db_path, pid, gid, ach_ids = cli_env
        result = _invoke(runner, db_path, ["timeline", "--days", "365"])
        data = json.loads(result.output)
        dates = [e["date"] for e in data]
        assert len(dates) == len(set(dates))

    def test_timeline_narrow_window(self, cli_env):
        """Timeline with small --days window may filter out older unlocks."""
        runner, db_path, pid, gid, ach_ids = cli_env
        # Our unlocks are from 2025-06 to 2025-08; if now is 2026, --days=30 returns nothing
        result = _invoke(runner, db_path, ["timeline", "--days", "30"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Should be empty or have fewer entries than the full year
        full_result = _invoke(runner, db_path, ["timeline", "--days", "3650"])
        full_data = json.loads(full_result.output)
        assert len(data) <= len(full_data)
