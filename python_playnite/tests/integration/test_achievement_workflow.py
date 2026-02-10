"""Integration tests for the complete achievement sync workflow.

All platform API calls are mocked so no live credentials are required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from playnite.achievements.exporter import AchievementExporter
from playnite.achievements.hunting import AchievementHunter
from playnite.achievements.platforms.manual import ManualAdapter
from playnite.achievements.platforms.steam import SteamAdapter
from playnite.achievements.tracker import AchievementTracker
from playnite.database.models import Achievement, Game, UserAchievement


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_steam_adapter(config, schema, player_data, global_pcts):
    """Return a SteamAdapter backed by mocked HTTP responses."""
    adapter = SteamAdapter(config.steam)
    adapter._get_owned_games = MagicMock(
        return_value=[{"appid": 570, "name": "Test Game", "img_icon_url": ""}]
    )
    adapter._get_schema = MagicMock(return_value=schema)
    adapter._get_player_achievements = MagicMock(return_value=player_data)
    adapter._get_global_percentages = MagicMock(return_value=global_pcts)
    return adapter


# ---------------------------------------------------------------------------
# Full sync workflow
# ---------------------------------------------------------------------------


class TestSteamSyncWorkflow:
    def test_sync_creates_games_and_achievements(
        self, tmp_db, tmp_config, sample_schema, sample_steam_response, sample_global_percentages
    ):
        player_achs = sample_steam_response["playerstats"]["achievements"]
        global_pcts = sample_global_percentages["achievementpercentages"]["achievements"]

        adapter = _mock_steam_adapter(tmp_config, sample_schema["game"]["availableGameStats"]["achievements"], player_achs, global_pcts)

        tracker = AchievementTracker(tmp_config, tmp_db)
        tracker.register_adapter(adapter)
        results = tracker.sync("steam")

        assert len(results) == 1
        r = results[0]
        assert r.platform == "steam"
        assert r.games_synced == 1
        assert r.achievements_found == 2
        assert r.achievements_unlocked == 1
        assert r.new_unlocks == 1

        with tmp_db.get_session() as session:
            games = session.query(Game).all()
            assert len(games) == 1
            assert games[0].name == "Test Game"
            achs = session.query(Achievement).all()
            assert len(achs) == 2
            uas = session.query(UserAchievement).filter_by(is_unlocked=True).all()
            assert len(uas) == 1

    def test_sync_idempotent(
        self, tmp_db, tmp_config, sample_schema, sample_steam_response, sample_global_percentages
    ):
        player_achs = sample_steam_response["playerstats"]["achievements"]
        global_pcts = sample_global_percentages["achievementpercentages"]["achievements"]
        adapter = _mock_steam_adapter(tmp_config, sample_schema["game"]["availableGameStats"]["achievements"], player_achs, global_pcts)

        tracker = AchievementTracker(tmp_config, tmp_db)
        tracker.register_adapter(adapter)
        tracker.sync("steam")
        tracker.sync("steam")  # Second sync should not duplicate

        with tmp_db.get_session() as session:
            count = session.query(Achievement).count()
            assert count == 2

    def test_sync_detects_new_unlock(
        self, tmp_db, tmp_config, sample_schema, sample_steam_response, sample_global_percentages
    ):
        schema = sample_schema["game"]["availableGameStats"]["achievements"]
        global_pcts = sample_global_percentages["achievementpercentages"]["achievements"]

        # First sync: no unlocks
        no_unlocks = [
            {**a, "achieved": 0, "unlocktime": 0}
            for a in sample_steam_response["playerstats"]["achievements"]
        ]
        adapter = _mock_steam_adapter(tmp_config, schema, no_unlocks, global_pcts)
        tracker = AchievementTracker(tmp_config, tmp_db)
        tracker.register_adapter(adapter)
        r1 = tracker.sync("steam")
        assert r1[0].new_unlocks == 0

        # Second sync: one unlock
        one_unlock = list(no_unlocks)
        one_unlock[0] = {**one_unlock[0], "achieved": 1, "unlocktime": 1700000000}
        adapter._get_player_achievements = MagicMock(return_value=one_unlock)
        r2 = tracker.sync("steam")
        assert r2[0].new_unlocks == 1

    def test_difficulty_scores_calculated(
        self, tmp_db, tmp_config, sample_schema, sample_steam_response, sample_global_percentages
    ):
        schema = sample_schema["game"]["availableGameStats"]["achievements"]
        player_achs = sample_steam_response["playerstats"]["achievements"]
        global_pcts = sample_global_percentages["achievementpercentages"]["achievements"]
        adapter = _mock_steam_adapter(tmp_config, schema, player_achs, global_pcts)

        tracker = AchievementTracker(tmp_config, tmp_db)
        tracker.register_adapter(adapter)
        tracker.sync("steam")

        with tmp_db.get_session() as session:
            # ACH_FIRST_BLOOD: 72.3% global → difficulty ≈ 0.277
            ach = session.query(Achievement).filter_by(achievement_id="ACH_FIRST_BLOOD").first()
            assert ach is not None
            assert ach.difficulty_score == pytest.approx(0.277, abs=0.001)
            # ACH_LEGEND: 3.1% global → is_rare = True
            rare = session.query(Achievement).filter_by(achievement_id="ACH_LEGEND").first()
            assert rare.is_rare is True

    def test_notifications_created_for_new_unlocks(
        self, tmp_db, tmp_config, sample_schema, sample_steam_response, sample_global_percentages
    ):
        schema = sample_schema["game"]["availableGameStats"]["achievements"]
        player_achs = sample_steam_response["playerstats"]["achievements"]
        global_pcts = sample_global_percentages["achievementpercentages"]["achievements"]
        adapter = _mock_steam_adapter(tmp_config, schema, player_achs, global_pcts)

        tracker = AchievementTracker(tmp_config, tmp_db)
        tracker.register_adapter(adapter)
        tracker.sync("steam")

        notifications = tracker.get_pending_notifications()
        assert len(notifications) == 1
        assert notifications[0]["achievement"] == "First Blood"


# ---------------------------------------------------------------------------
# Manual achievement workflow
# ---------------------------------------------------------------------------


class TestManualWorkflow:
    def test_full_manual_workflow(self, tmp_db, tmp_config):
        manual = ManualAdapter(tmp_db)
        game_id = manual.add_game("My Indie Game")

        ach_id = manual.add_achievement(
            game_id=game_id,
            achievement_id="MANUAL_001",
            name="First Step",
            description="Start the game",
            is_unlocked=False,
            max_value=1.0,
            current_value=0.0,
        )

        # Verify locked
        with tmp_db.get_session() as session:
            ua = session.query(UserAchievement).filter_by(achievement_id=ach_id).first()
            assert ua.is_unlocked is False

        # Mark as unlocked
        manual.mark_unlocked(ach_id)

        with tmp_db.get_session() as session:
            ua = session.query(UserAchievement).filter_by(achievement_id=ach_id).first()
            assert ua.is_unlocked is True
            assert ua.unlock_date is not None

    def test_progress_update(self, tmp_db, tmp_config):
        manual = ManualAdapter(tmp_db)
        gid = manual.add_game("Progress Game")
        aid = manual.add_achievement(
            game_id=gid,
            achievement_id="PROG_001",
            name="Collector",
            max_value=100.0,
            current_value=0.0,
        )
        manual.update_progress(aid, current_value=50.0, max_value=100.0)

        with tmp_db.get_session() as session:
            ach = session.get(Achievement, aid)
            assert ach.current_value == 50.0


# ---------------------------------------------------------------------------
# Achievement hunting workflow
# ---------------------------------------------------------------------------


class TestHuntingWorkflow:
    def _populate(self, db):
        with db.get_session() as session:
            game = Game(name="Completable", platform="steam", platform_game_id="hunt1",
                        total_achievements=10)
            session.add(game)
            session.flush()
            for i in range(10):
                difficulty = 0.2 if i < 7 else 0.9  # 7 easy, 3 hard
                ach = Achievement(
                    game_id=game.id,
                    achievement_id=f"H{i}",
                    name=f"H{i}",
                    global_percentage=(1 - difficulty) * 100,
                    difficulty_score=difficulty,
                    is_rare=(difficulty > 0.8),
                )
                session.add(ach)
                session.flush()
                if i < 5:  # 5 already unlocked
                    session.add(UserAchievement(
                        achievement_id=ach.id,
                        platform_user_id="steam",
                        is_unlocked=True,
                    ))

    def test_hunt_finds_completable_game(self, tmp_db, tmp_config):
        self._populate(tmp_db)
        hunter = AchievementHunter(tmp_db)
        targets = hunter.find_targets(max_difficulty=0.5, max_remaining=10, limit=5)
        assert len(targets) >= 1
        assert targets[0].game_name == "Completable"

    def test_challenge_suggests_game(self, tmp_db, tmp_config):
        self._populate(tmp_db)
        hunter = AchievementHunter(tmp_db)
        challenge = hunter.create_challenge(max_difficulty=0.5, max_hours=5.0, count=3)
        assert len(challenge) >= 1


# ---------------------------------------------------------------------------
# Export workflow
# ---------------------------------------------------------------------------


class TestExportWorkflow:
    def _populate(self, db):
        with db.get_session() as session:
            game = Game(name="Export Game", platform="steam", platform_game_id="exp1")
            session.add(game)
            session.flush()
            for i in range(3):
                ach = Achievement(
                    game_id=game.id,
                    achievement_id=f"E{i}",
                    name=f"E{i}",
                    global_percentage=50.0,
                )
                session.add(ach)
                session.flush()
                session.add(UserAchievement(
                    achievement_id=ach.id,
                    platform_user_id="steam",
                    is_unlocked=(i < 2),
                ))

    def test_json_export(self, tmp_db, tmp_config, tmp_path):
        import json
        self._populate(tmp_db)
        exporter = AchievementExporter(tmp_db)
        out = tmp_path / "export.json"
        count = exporter.export_to_json(out)
        assert count == 3
        data = json.loads(out.read_text())
        assert data["total"] == 3

    def test_csv_export(self, tmp_db, tmp_config, tmp_path):
        import csv
        self._populate(tmp_db)
        exporter = AchievementExporter(tmp_db)
        out = tmp_path / "export.csv"
        count = exporter.export_to_csv(out)
        assert count == 3
        rows = list(csv.DictReader(out.open()))
        assert len(rows) == 3
        assert "game_name" in rows[0]
        assert "achievement_name" in rows[0]

    def test_export_unlocked_only(self, tmp_db, tmp_config, tmp_path):
        self._populate(tmp_db)
        exporter = AchievementExporter(tmp_db)
        out = tmp_path / "unlocked.json"
        count = exporter.export_to_json(out, include_locked=False)
        assert count == 2  # Only 2 were unlocked
