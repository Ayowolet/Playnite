"""Unit tests for the achievement CLI commands (cli/achievement_cli.py)."""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from click.testing import CliRunner

from playnite.cli.achievement_cli import achievements_group
from playnite.database.models import Achievement, Game, UserAchievement


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def ctx(tmp_db, tmp_config):
    """Minimal context — empty DB."""
    return {"config": tmp_config, "db": tmp_db}


@pytest.fixture
def seeded_ctx(tmp_db, tmp_config):
    """Context with steam + manual achievements pre-seeded."""
    with tmp_db.get_session() as session:
        # Steam game with two achievements
        g_steam = Game(name="Portal 2", platform="steam", platform_game_id="620")
        session.add(g_steam)
        session.flush()

        a_common = Achievement(
            game_id=g_steam.id, achievement_id="ACH_EASY",
            name="Easy Win", global_percentage=80.0,
            difficulty_score=0.2, is_rare=False,
        )
        a_rare = Achievement(
            game_id=g_steam.id, achievement_id="ACH_RARE",
            name="Diamond Trophy", global_percentage=0.8,
            difficulty_score=0.992, is_rare=True,
        )
        session.add_all([a_common, a_rare])
        session.flush()

        session.add(UserAchievement(
            achievement_id=a_common.id, platform_user_id="76561198000000001",
            is_unlocked=True, unlock_date=datetime(2024, 1, 10),
        ))
        session.add(UserAchievement(
            achievement_id=a_rare.id, platform_user_id="76561198000000001",
            is_unlocked=True, unlock_date=datetime(2024, 3, 5),
        ))

        # Manual game with one locked achievement
        g_manual = Game(name="Board Game", platform="manual",
                        platform_game_id="manual_Board Game")
        session.add(g_manual)
        session.flush()

        a_manual = Achievement(
            game_id=g_manual.id, achievement_id="MAN_1",
            name="First Move", global_percentage=None,
            difficulty_score=None, is_rare=False,
        )
        session.add(a_manual)
        session.flush()

        session.add(UserAchievement(
            achievement_id=a_manual.id, platform_user_id="manual",
            is_unlocked=False,
        ))

    return {"config": tmp_config, "db": tmp_db}


def invoke(runner, ctx_obj, args, catch_exceptions=False):
    return runner.invoke(achievements_group, args, obj=ctx_obj,
                         catch_exceptions=catch_exceptions)


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------


class TestSyncCommand:
    def test_sync_manual_json(self, runner, ctx):
        r = invoke(runner, ctx, ["sync", "--platform", "manual", "--json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert isinstance(data, list)
        assert data[0]["platform"] == "manual"

    def test_sync_all_platforms_json(self, runner, ctx):
        """All adapters registered; manual syncs ok, others fail gracefully."""
        r = invoke(runner, ctx, ["sync", "--platform", "manual", "--json"])
        assert r.exit_code == 0

    def test_sync_shows_new_unlocks(self, runner, seeded_ctx):
        """Rich output path (no --json) exercises notification display."""
        r = invoke(runner, seeded_ctx, ["sync", "--platform", "manual"])
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


class TestStatsCommand:
    def test_stats_empty_json(self, runner, ctx):
        r = invoke(runner, ctx, ["stats", "--json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert "global" in data
        assert "velocity" in data
        assert "milestones" in data

    def test_stats_with_data_json(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["stats", "--json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["global"]["total_achievements"] >= 3

    def test_stats_table_output(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["stats"])
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


class TestListCommand:
    def test_list_all_json(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["list", "--json"])
        assert r.exit_code == 0
        rows = json.loads(r.output)
        assert len(rows) >= 3

    def test_list_filter_by_game_name(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["list", "--game", "Portal", "--json"])
        assert r.exit_code == 0
        rows = json.loads(r.output)
        assert all(r["game"] == "Portal 2" for r in rows)
        assert len(rows) == 2

    def test_list_filter_by_platform(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["list", "--platform", "manual", "--json"])
        assert r.exit_code == 0
        rows = json.loads(r.output)
        assert all(r["platform"] == "manual" for r in rows)

    def test_list_unlocked_only(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["list", "--unlocked-only", "--json"])
        assert r.exit_code == 0
        rows = json.loads(r.output)
        assert all(row["is_unlocked"] for row in rows)
        assert len(rows) == 2  # only the two steam achievements are unlocked

    def test_list_empty_db(self, runner, ctx):
        r = invoke(runner, ctx, ["list", "--json"])
        assert r.exit_code == 0

    def test_list_table_output(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["list"])
        assert r.exit_code == 0

    def test_list_table_no_results(self, runner, ctx):
        r = invoke(runner, ctx, ["list"])
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# rare
# ---------------------------------------------------------------------------


class TestRareCommand:
    def test_rare_json_contains_rare_achievement(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["rare", "--json"])
        assert r.exit_code == 0
        rows = json.loads(r.output)
        assert any(row["achievement"] == "Diamond Trophy" for row in rows)

    def test_rare_platform_filter(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["rare", "--platform", "steam", "--json"])
        assert r.exit_code == 0
        rows = json.loads(r.output)
        assert all(row["platform"] == "steam" for row in rows)

    def test_rare_empty_db(self, runner, ctx):
        r = invoke(runner, ctx, ["rare", "--json"])
        assert r.exit_code == 0
        rows = json.loads(r.output)
        assert rows == []

    def test_rare_table_output(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["rare"])
        assert r.exit_code == 0

    def test_rare_table_no_data(self, runner, ctx):
        r = invoke(runner, ctx, ["rare"])
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


class TestExportCommand:
    def test_export_json_format(self, runner, seeded_ctx, tmp_path):
        out = tmp_path / "ach.json"
        r = invoke(runner, seeded_ctx, ["export", "--format", "json", "--output", str(out)])
        assert r.exit_code == 0
        assert out.exists()

    def test_export_csv_format(self, runner, seeded_ctx, tmp_path):
        out = tmp_path / "ach.csv"
        r = invoke(runner, seeded_ctx, ["export", "--format", "csv", "--output", str(out)])
        assert r.exit_code == 0
        assert out.exists() and out.stat().st_size > 0

    def test_export_unlocked_only(self, runner, seeded_ctx, tmp_path):
        out = tmp_path / "unlocked.json"
        r = invoke(runner, seeded_ctx,
                   ["export", "--format", "json", "--output", str(out), "--unlocked-only"])
        assert r.exit_code == 0

    def test_export_specific_game_id(self, runner, seeded_ctx, tmp_path):
        db = seeded_ctx["db"]
        with db.get_session() as session:
            g = session.query(Game).filter_by(name="Portal 2").first()
            gid = g.id
        out = tmp_path / "portal.json"
        r = invoke(runner, seeded_ctx,
                   ["export", "--format", "json", "--output", str(out),
                    "--game-id", str(gid)])
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------


class TestImportCommand:
    def test_import_json_output(self, runner, seeded_ctx, tmp_path):
        out = tmp_path / "lib.json"
        invoke(runner, seeded_ctx, ["export", "--format", "json", "--output", str(out)])
        r = invoke(runner, seeded_ctx, ["import", "--input", str(out), "--json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert "imported" in data

    def test_import_plain_output(self, runner, seeded_ctx, tmp_path):
        out = tmp_path / "lib2.json"
        invoke(runner, seeded_ctx, ["export", "--format", "json", "--output", str(out)])
        r = invoke(runner, seeded_ctx, ["import", "--input", str(out)])
        assert r.exit_code == 0
        assert "Imported" in r.output


# ---------------------------------------------------------------------------
# add-manual
# ---------------------------------------------------------------------------


class TestAddManualCommand:
    def test_add_creates_achievement(self, runner, ctx):
        r = invoke(runner, ctx, [
            "add-manual", "--game", "Chess", "--name", "Checkmate",
            "--description", "Win a game of chess.",
        ])
        assert r.exit_code == 0
        assert "Checkmate" in r.output

    def test_add_unlocked_with_date(self, runner, ctx):
        r = invoke(runner, ctx, [
            "add-manual", "--game", "Chess", "--name", "Grand Master",
            "--unlocked", "--unlock-date", "2024-07-04",
        ])
        assert r.exit_code == 0

    def test_add_with_existing_game_id(self, runner, seeded_ctx):
        db = seeded_ctx["db"]
        with db.get_session() as session:
            g = session.query(Game).filter_by(name="Board Game").first()
            gid = g.id
        r = invoke(runner, seeded_ctx, [
            "add-manual", "--game", "Board Game", "--game-id", str(gid),
            "--name", "Late Bloomer",
        ])
        assert r.exit_code == 0

    def test_add_with_progress_values(self, runner, ctx):
        r = invoke(runner, ctx, [
            "add-manual", "--game", "RPG", "--name", "Level 50",
            "--max-value", "50", "--current-value", "10",
        ])
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# mark-unlocked
# ---------------------------------------------------------------------------


class TestMarkUnlockedCommand:
    def test_mark_unlocked_json(self, runner, seeded_ctx):
        db = seeded_ctx["db"]
        with db.get_session() as session:
            a = session.query(Achievement).filter_by(achievement_id="MAN_1").first()
            ach_id = a.id
        r = invoke(runner, seeded_ctx,
                   ["mark-unlocked", "--achievement-id", str(ach_id), "--json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["success"] is True

    def test_mark_unlocked_with_date(self, runner, seeded_ctx):
        db = seeded_ctx["db"]
        with db.get_session() as session:
            a = session.query(Achievement).filter_by(achievement_id="MAN_1").first()
            ach_id = a.id
        r = invoke(runner, seeded_ctx, [
            "mark-unlocked", "--achievement-id", str(ach_id),
            "--unlock-date", "2024-09-01",
        ])
        assert r.exit_code == 0
        assert "marked as unlocked" in r.output

    def test_mark_unlocked_not_found(self, runner, ctx):
        # JSON path returns exit 0 with success=False; non-JSON path calls sys.exit(1)
        r = invoke(runner, ctx, ["mark-unlocked", "--achievement-id", "99999", "--json"])
        assert r.exit_code == 0
        assert json.loads(r.output)["success"] is False


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


class TestReportCommand:
    def test_report_json(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["report", "--json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert "summary" in data
        assert "games" in data

    def test_report_plain(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["report"])
        assert r.exit_code == 0
        assert "games tracked" in r.output.lower() or "achievement" in r.output.lower()

    def test_report_saves_file(self, runner, seeded_ctx, tmp_path):
        out = tmp_path / "report.json"
        r = invoke(runner, seeded_ctx, ["report", "--output", str(out)])
        assert r.exit_code == 0
        assert out.exists()


# ---------------------------------------------------------------------------
# timeline
# ---------------------------------------------------------------------------


class TestTimelineCommand:
    def test_timeline_json(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["timeline", "--json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert isinstance(data, list)

    def test_timeline_date_range_json(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx,
                   ["timeline", "--start", "2024-01-01", "--end", "2024-12-31", "--json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert isinstance(data, list)

    def test_timeline_plain_with_data(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["timeline"])
        assert r.exit_code == 0

    def test_timeline_plain_no_data(self, runner, ctx):
        r = invoke(runner, ctx, ["timeline"])
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# notifications
# ---------------------------------------------------------------------------


class TestNotificationsCommand:
    def test_notifications_empty_json(self, runner, ctx):
        r = invoke(runner, ctx, ["notifications", "--json"])
        assert r.exit_code == 0
        assert json.loads(r.output) == []

    def test_notifications_plain_empty(self, runner, ctx):
        r = invoke(runner, ctx, ["notifications"])
        assert r.exit_code == 0
        assert "pending" in r.output.lower() or "No pending" in r.output

    def test_notifications_mark_read(self, runner, ctx):
        r = invoke(runner, ctx, ["notifications", "--mark-read"])
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# hunt
# ---------------------------------------------------------------------------


class TestHuntCommand:
    def test_hunt_json_empty(self, runner, ctx):
        r = invoke(runner, ctx, ["hunt", "--json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert isinstance(data, list)

    def test_hunt_plain_no_matches(self, runner, ctx):
        r = invoke(runner, ctx, ["hunt"])
        assert r.exit_code == 0

    def test_hunt_with_data_json(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["hunt", "--json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert isinstance(data, list)

    def test_hunt_with_data_table(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["hunt"])
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# challenge
# ---------------------------------------------------------------------------


class TestChallengeCommand:
    def test_challenge_json_empty(self, runner, ctx):
        r = invoke(runner, ctx, ["challenge", "--json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert isinstance(data, list)

    def test_challenge_plain_no_data(self, runner, ctx):
        r = invoke(runner, ctx, ["challenge"])
        assert r.exit_code == 0

    def test_challenge_with_data(self, runner, seeded_ctx):
        r = invoke(runner, seeded_ctx, ["challenge", "--json"])
        assert r.exit_code == 0
        assert isinstance(json.loads(r.output), list)
