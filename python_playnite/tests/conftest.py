"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from playnite.config import AchievementConfig, BackupConfig, Config, GOGConfig, PSNConfig, SteamConfig, XboxConfig
from playnite.database.connection import DatabaseManager


@pytest.fixture
def tmp_db(tmp_path):
    """Return an in-memory (tmp file) DatabaseManager with schema initialised."""
    db_path = str(tmp_path / "test.db")
    db = DatabaseManager(db_path)
    db.init_db()
    yield db
    db.drop_all()


@pytest.fixture
def tmp_config(tmp_path):
    """Return a Config pointing at a temp directory."""
    data_dir = str(tmp_path / "playnite_data")
    cfg = Config(
        data_dir=data_dir,
        database_path=str(tmp_path / "playnite_data" / "playnite.db"),
        steam=SteamConfig(api_key="test_key", steam_id="76561198000000001", enabled=True),
        xbox=XboxConfig(api_key="xbox_key", xuid="xuid123", enabled=True),
        psn=PSNConfig(npsso_token="npsso_token", enabled=True),
        gog=GOGConfig(access_token="gog_token", enabled=True),
        backup=BackupConfig(
            default_destination=str(tmp_path / "backups"),
            max_backups=5,
            retention_days=7,
        ),
        achievements=AchievementConfig(
            auto_sync_enabled=False,
            rare_threshold=10.0,
            notify_on_unlock=True,
        ),
    )
    cfg.ensure_dirs()
    return cfg


@pytest.fixture
def sample_steam_response():
    """Minimal mocked Steam API response for GetPlayerAchievements."""
    return {
        "playerstats": {
            "steamID": "76561198000000001",
            "gameName": "Test Game",
            "achievements": [
                {
                    "apiname": "ACH_FIRST_BLOOD",
                    "achieved": 1,
                    "unlocktime": 1700000000,
                    "name": "First Blood",
                    "description": "Kill your first enemy.",
                },
                {
                    "apiname": "ACH_LEGEND",
                    "achieved": 0,
                    "unlocktime": 0,
                    "name": "Legend",
                    "description": "Complete the game on max difficulty.",
                },
            ],
            "success": True,
        }
    }


@pytest.fixture
def sample_global_percentages():
    return {
        "achievementpercentages": {
            "achievements": [
                {"name": "ACH_FIRST_BLOOD", "percent": 72.3},
                {"name": "ACH_LEGEND", "percent": 3.1},
            ]
        }
    }


@pytest.fixture
def sample_schema():
    return {
        "game": {
            "availableGameStats": {
                "achievements": [
                    {
                        "name": "ACH_FIRST_BLOOD",
                        "displayName": "First Blood",
                        "description": "Kill your first enemy.",
                        "hidden": 0,
                        "icon": "https://cdn.example.com/icon1.jpg",
                        "icongray": "https://cdn.example.com/icon1_gray.jpg",
                    },
                    {
                        "name": "ACH_LEGEND",
                        "displayName": "Legend",
                        "description": "Complete the game on max difficulty.",
                        "hidden": 0,
                        "icon": "https://cdn.example.com/icon2.jpg",
                        "icongray": "https://cdn.example.com/icon2_gray.jpg",
                    },
                ]
            }
        }
    }
