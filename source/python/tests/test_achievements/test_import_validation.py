"""Validation tests for achievement import scenarios.

Covers: Steam import path, second platform (Xbox) import path,
icon URL storage, 0%/100%/partial completion games, name/description accuracy,
unlock status, timestamps, and global completion percentages.
"""

import responses

import pytest

from gamelibrary.database import Database
from gamelibrary.achievements.tracker import AchievementTracker
from gamelibrary.achievements.stats import AchievementStats
from gamelibrary.achievements.platforms.steam import STEAM_API_BASE
from gamelibrary.achievements.platforms.xbox import XBOX_API_BASE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "validation.db")


@pytest.fixture
def tracker(db):
    return AchievementTracker(db)


@pytest.fixture
def stats(db):
    return AchievementStats(db)


# ---------------------------------------------------------------------------
# Mock Steam API responses
# ---------------------------------------------------------------------------

STEAM_OWNED_GAMES = {
    "response": {
        "game_count": 1,
        "games": [
            {
                "appid": 570,
                "name": "Dota 2",
                "img_icon_url": "d8696af83f3cec43a5ff37420b4d3b06086e5684",
            }
        ],
    }
}

STEAM_SCHEMA = {
    "game": {
        "gameName": "Dota 2",
        "availableGameStats": {
            "achievements": [
                {
                    "name": "ACH_WIN_FIRST",
                    "displayName": "First Win",
                    "description": "Win your first match of Dota 2.",
                    "icon": "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/570/ach_win.jpg",
                    "icongray": "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/570/ach_win_gray.jpg",
                    "hidden": 0,
                },
                {
                    "name": "ACH_PLAY_100",
                    "displayName": "Veteran",
                    "description": "Play 100 matches.",
                    "icon": "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/570/ach_play100.jpg",
                    "icongray": "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/570/ach_play100_gray.jpg",
                    "hidden": 0,
                },
                {
                    "name": "ACH_SECRET",
                    "displayName": "The Hidden One",
                    "description": "",
                    "icon": "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/570/secret.jpg",
                    "icongray": "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/570/secret_gray.jpg",
                    "hidden": 1,
                },
            ]
        },
    }
}

STEAM_PLAYER_ACHIEVEMENTS = {
    "playerstats": {
        "steamID": "76561198000000000",
        "gameName": "Dota 2",
        "achievements": [
            {"apiname": "ACH_WIN_FIRST", "achieved": 1, "unlocktime": 1700000000},
            {"apiname": "ACH_PLAY_100", "achieved": 0, "unlocktime": 0},
            {"apiname": "ACH_SECRET", "achieved": 1, "unlocktime": 1710000000},
        ],
    }
}

STEAM_GLOBAL_STATS = {
    "achievementpercentages": {
        "achievements": [
            {"name": "ACH_WIN_FIRST", "percent": 72.5},
            {"name": "ACH_PLAY_100", "percent": 15.3},
            {"name": "ACH_SECRET", "percent": 3.7},
        ]
    }
}


# ---------------------------------------------------------------------------
# Mock Xbox API responses
# ---------------------------------------------------------------------------

XBOX_ACHIEVEMENTS_TITLES = {
    "titles": [
        {
            "titleId": 1234567,
            "name": "Halo Infinite",
            "displayImage": "https://store-images.s-microsoft.com/image/apps.halo.jpg",
            "achievement": {"totalGamerscore": 1000},
        }
    ]
}

XBOX_ACHIEVEMENTS_LIST = {
    "achievements": [
        {
            "id": "1",
            "name": "Banished",
            "description": "Complete the campaign on any difficulty.",
            "isSecret": False,
            "progression": {
                "requirements": [{"current": "1", "target": "1"}],
                "timeUnlocked": "2024-12-01T10:30:00.0000000Z",
            },
            "rarity": {"currentPercentage": 28.5},
            "mediaAssets": [{"url": "https://xbox-images.com/banished.png"}],
        },
        {
            "id": "2",
            "name": "LASO Master",
            "description": "Complete the campaign on Legendary with all skulls.",
            "isSecret": True,
            "progression": {
                "requirements": [{"current": "0", "target": "1"}],
                "timeUnlocked": "0001-01-01T00:00:00.0000000Z",
            },
            "rarity": {"currentPercentage": 0.8},
            "mediaAssets": [{"url": "https://xbox-images.com/laso.png"}],
        },
    ]
}


# ===================================================================
# Steam Import Tests
# ===================================================================

class TestSteamImport:
    """Validate that Steam achievements are imported correctly."""

    @responses.activate
    def test_import_achievements_from_steam(self, tracker, db):
        """Import achievements from a mocked Steam account and verify the result."""
        self._register_steam_mocks()

        pid = tracker.register_platform(
            "Steam", "steam", {"api_key": "FAKEKEY", "steam_id": "76561198000000000"}
        )
        result = tracker.import_achievements(pid)

        assert result["status"] == "completed"
        assert result["platform"] == "Steam"
        assert result["games_processed"] == 1
        assert result["achievements_found"] == 3

    @responses.activate
    def test_all_achievements_for_game_imported(self, tracker, db):
        """Verify all 3 achievements for the game are stored."""
        self._register_steam_mocks()
        pid = tracker.register_platform(
            "Steam", "steam", {"api_key": "FAKEKEY", "steam_id": "76561198000000000"}
        )
        tracker.import_achievements(pid)

        games = tracker.get_games(pid)
        assert len(games) == 1
        assert games[0].name == "Dota 2"

        achs = tracker.get_achievements(games[0].id)
        assert len(achs) == 3

    @responses.activate
    def test_achievement_names_accurate(self, tracker, db):
        """Verify achievement names match the Steam schema displayName."""
        self._register_steam_mocks()
        pid = tracker.register_platform(
            "Steam", "steam", {"api_key": "FAKEKEY", "steam_id": "76561198000000000"}
        )
        tracker.import_achievements(pid)

        games = tracker.get_games(pid)
        achs = tracker.get_achievements(games[0].id)
        names = {a.name for a in achs}
        assert names == {"First Win", "Veteran", "The Hidden One"}

    @responses.activate
    def test_achievement_descriptions_complete(self, tracker, db):
        """Verify descriptions are imported. Hidden achievement may have empty description."""
        self._register_steam_mocks()
        pid = tracker.register_platform(
            "Steam", "steam", {"api_key": "FAKEKEY", "steam_id": "76561198000000000"}
        )
        tracker.import_achievements(pid)

        games = tracker.get_games(pid)
        achs = tracker.get_achievements(games[0].id)
        by_name = {a.name: a for a in achs}
        assert by_name["First Win"].description == "Win your first match of Dota 2."
        assert by_name["Veteran"].description == "Play 100 matches."
        # Hidden achievement has empty description in schema
        assert by_name["The Hidden One"].description == ""

    @responses.activate
    def test_achievement_icon_urls_stored(self, tracker, db):
        """Verify icon URLs are stored (not downloaded, but available for display)."""
        self._register_steam_mocks()
        pid = tracker.register_platform(
            "Steam", "steam", {"api_key": "FAKEKEY", "steam_id": "76561198000000000"}
        )
        tracker.import_achievements(pid)

        games = tracker.get_games(pid)
        achs = tracker.get_achievements(games[0].id)
        by_name = {a.name: a for a in achs}

        assert by_name["First Win"].icon_url.startswith("https://")
        assert "ach_win.jpg" in by_name["First Win"].icon_url
        assert by_name["First Win"].locked_icon_url.startswith("https://")
        assert "ach_win_gray.jpg" in by_name["First Win"].locked_icon_url

    @responses.activate
    def test_unlock_status_correct(self, tracker, db):
        """Verify locked vs unlocked status matches the player data."""
        self._register_steam_mocks()
        pid = tracker.register_platform(
            "Steam", "steam", {"api_key": "FAKEKEY", "steam_id": "76561198000000000"}
        )
        tracker.import_achievements(pid)

        games = tracker.get_games(pid)
        achs = tracker.get_achievements(games[0].id)
        by_name = {a.name: a for a in achs}

        assert by_name["First Win"].unlocked is True
        assert by_name["Veteran"].unlocked is False
        assert by_name["The Hidden One"].unlocked is True

    @responses.activate
    def test_unlock_timestamps_accurate(self, tracker, db):
        """Verify unlock timestamps are converted from epoch to ISO format."""
        self._register_steam_mocks()
        pid = tracker.register_platform(
            "Steam", "steam", {"api_key": "FAKEKEY", "steam_id": "76561198000000000"}
        )
        tracker.import_achievements(pid)

        games = tracker.get_games(pid)
        achs = tracker.get_achievements(games[0].id)
        by_name = {a.name: a for a in achs}

        # Unlocked achievements should have ISO timestamps
        assert by_name["First Win"].unlock_date is not None
        assert "2023-11-14" in by_name["First Win"].unlock_date  # epoch 1700000000
        assert by_name["The Hidden One"].unlock_date is not None
        # Locked achievement should have no unlock date
        assert by_name["Veteran"].unlock_date is None

    @responses.activate
    def test_global_completion_percentages_imported(self, tracker, db):
        """Verify global completion percentages are stored accurately."""
        self._register_steam_mocks()
        pid = tracker.register_platform(
            "Steam", "steam", {"api_key": "FAKEKEY", "steam_id": "76561198000000000"}
        )
        tracker.import_achievements(pid)

        games = tracker.get_games(pid)
        achs = tracker.get_achievements(games[0].id)
        by_name = {a.name: a for a in achs}

        assert by_name["First Win"].global_completion_pct == 72.5
        assert by_name["Veteran"].global_completion_pct == 15.3
        assert by_name["The Hidden One"].global_completion_pct == 3.7

    @staticmethod
    def _register_steam_mocks():
        responses.add(
            responses.GET,
            f"{STEAM_API_BASE}/IPlayerService/GetOwnedGames/v1/",
            json=STEAM_OWNED_GAMES,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{STEAM_API_BASE}/ISteamUserStats/GetSchemaForGame/v2/",
            json=STEAM_SCHEMA,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{STEAM_API_BASE}/ISteamUserStats/GetPlayerAchievements/v1/",
            json=STEAM_PLAYER_ACHIEVEMENTS,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{STEAM_API_BASE}/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/",
            json=STEAM_GLOBAL_STATS,
            status=200,
        )


# ===================================================================
# Xbox Import Tests (second platform)
# ===================================================================

class TestXboxImport:
    """Validate that Xbox Live achievements are imported correctly."""

    @responses.activate
    def test_import_achievements_from_xbox(self, tracker, db):
        """Import achievements from a mocked Xbox account."""
        self._register_xbox_mocks()

        pid = tracker.register_platform(
            "Xbox", "xbox", {"api_key": "FAKEKEY", "xuid": "1234567890"}
        )
        result = tracker.import_achievements(pid)

        assert result["status"] == "completed"
        assert result["platform"] == "Xbox"
        assert result["achievements_found"] == 2

    @responses.activate
    def test_xbox_achievement_names_and_descriptions(self, tracker, db):
        """Verify Xbox achievement names and descriptions are correct."""
        self._register_xbox_mocks()
        pid = tracker.register_platform(
            "Xbox", "xbox", {"api_key": "FAKEKEY", "xuid": "1234567890"}
        )
        tracker.import_achievements(pid)

        games = tracker.get_games(pid)
        assert len(games) == 1
        assert games[0].name == "Halo Infinite"

        achs = tracker.get_achievements(games[0].id)
        by_name = {a.name: a for a in achs}
        assert "Banished" in by_name
        assert "LASO Master" in by_name
        assert by_name["Banished"].description == "Complete the campaign on any difficulty."
        assert by_name["LASO Master"].description == "Complete the campaign on Legendary with all skulls."

    @responses.activate
    def test_xbox_unlock_status_and_timestamps(self, tracker, db):
        """Verify Xbox unlock status and timestamps."""
        self._register_xbox_mocks()
        pid = tracker.register_platform(
            "Xbox", "xbox", {"api_key": "FAKEKEY", "xuid": "1234567890"}
        )
        tracker.import_achievements(pid)

        games = tracker.get_games(pid)
        achs = tracker.get_achievements(games[0].id)
        by_name = {a.name: a for a in achs}

        assert by_name["Banished"].unlocked is True
        assert by_name["Banished"].unlock_date is not None
        assert "2024-12-01" in by_name["Banished"].unlock_date
        assert by_name["LASO Master"].unlocked is False
        assert by_name["LASO Master"].unlock_date is None

    @responses.activate
    def test_xbox_global_completion_and_icons(self, tracker, db):
        """Verify Xbox global completion percentages and icon URLs."""
        self._register_xbox_mocks()
        pid = tracker.register_platform(
            "Xbox", "xbox", {"api_key": "FAKEKEY", "xuid": "1234567890"}
        )
        tracker.import_achievements(pid)

        games = tracker.get_games(pid)
        achs = tracker.get_achievements(games[0].id)
        by_name = {a.name: a for a in achs}

        assert by_name["Banished"].global_completion_pct == 28.5
        assert by_name["LASO Master"].global_completion_pct == 0.8
        assert by_name["Banished"].icon_url == "https://xbox-images.com/banished.png"
        assert by_name["LASO Master"].icon_url == "https://xbox-images.com/laso.png"

    @staticmethod
    def _register_xbox_mocks():
        responses.add(
            responses.GET,
            f"{XBOX_API_BASE}/achievements",
            json=XBOX_ACHIEVEMENTS_TITLES,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{XBOX_API_BASE}/achievements/title/1234567",
            json=XBOX_ACHIEVEMENTS_LIST,
            status=200,
        )


# ===================================================================
# Completion Scenarios
# ===================================================================

class TestZeroPercentCompletion:
    """Test import for a game with 0% achievements unlocked."""

    @responses.activate
    def test_game_with_zero_percent_unlocked(self, tracker, stats, db):
        """A game where no achievements are unlocked shows 0% completion."""
        # Use Steam mock with all achievements locked
        all_locked_player = {
            "playerstats": {
                "achievements": [
                    {"apiname": "ACH_WIN_FIRST", "achieved": 0, "unlocktime": 0},
                    {"apiname": "ACH_PLAY_100", "achieved": 0, "unlocktime": 0},
                    {"apiname": "ACH_SECRET", "achieved": 0, "unlocktime": 0},
                ]
            }
        }
        responses.add(responses.GET, f"{STEAM_API_BASE}/IPlayerService/GetOwnedGames/v1/",
                       json=STEAM_OWNED_GAMES, status=200)
        responses.add(responses.GET, f"{STEAM_API_BASE}/ISteamUserStats/GetSchemaForGame/v2/",
                       json=STEAM_SCHEMA, status=200)
        responses.add(responses.GET, f"{STEAM_API_BASE}/ISteamUserStats/GetPlayerAchievements/v1/",
                       json=all_locked_player, status=200)
        responses.add(responses.GET, f"{STEAM_API_BASE}/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/",
                       json=STEAM_GLOBAL_STATS, status=200)

        pid = tracker.register_platform(
            "Steam", "steam", {"api_key": "FAKEKEY", "steam_id": "76561198000000000"}
        )
        result = tracker.import_achievements(pid)
        assert result["new_unlocks"] == 0

        games = tracker.get_games(pid)
        game_stats = stats.get_game_stats(games[0].id)
        assert game_stats.total_achievements == 3
        assert game_stats.unlocked_count == 0
        assert game_stats.completion_pct == 0.0

        achs = tracker.get_achievements(games[0].id)
        assert all(a.unlocked is False for a in achs)
        assert all(a.unlock_date is None for a in achs)


class TestHundredPercentCompletion:
    """Test import for a game with 100% achievements unlocked."""

    @responses.activate
    def test_game_with_hundred_percent_unlocked(self, tracker, stats, db):
        """A game where all achievements are unlocked shows 100% completion."""
        all_unlocked_player = {
            "playerstats": {
                "achievements": [
                    {"apiname": "ACH_WIN_FIRST", "achieved": 1, "unlocktime": 1700000000},
                    {"apiname": "ACH_PLAY_100", "achieved": 1, "unlocktime": 1705000000},
                    {"apiname": "ACH_SECRET", "achieved": 1, "unlocktime": 1710000000},
                ]
            }
        }
        responses.add(responses.GET, f"{STEAM_API_BASE}/IPlayerService/GetOwnedGames/v1/",
                       json=STEAM_OWNED_GAMES, status=200)
        responses.add(responses.GET, f"{STEAM_API_BASE}/ISteamUserStats/GetSchemaForGame/v2/",
                       json=STEAM_SCHEMA, status=200)
        responses.add(responses.GET, f"{STEAM_API_BASE}/ISteamUserStats/GetPlayerAchievements/v1/",
                       json=all_unlocked_player, status=200)
        responses.add(responses.GET, f"{STEAM_API_BASE}/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/",
                       json=STEAM_GLOBAL_STATS, status=200)

        pid = tracker.register_platform(
            "Steam", "steam", {"api_key": "FAKEKEY", "steam_id": "76561198000000000"}
        )
        result = tracker.import_achievements(pid)
        assert result["new_unlocks"] == 3

        games = tracker.get_games(pid)
        game_stats = stats.get_game_stats(games[0].id)
        assert game_stats.total_achievements == 3
        assert game_stats.unlocked_count == 3
        assert game_stats.completion_pct == 100.0

        achs = tracker.get_achievements(games[0].id)
        assert all(a.unlocked is True for a in achs)
        assert all(a.unlock_date is not None for a in achs)


class TestPartialCompletion:
    """Test import for a game with partial completion."""

    @responses.activate
    def test_game_with_partial_completion(self, tracker, stats, db):
        """A game with 2/3 unlocked shows ~66.67% completion."""
        responses.add(responses.GET, f"{STEAM_API_BASE}/IPlayerService/GetOwnedGames/v1/",
                       json=STEAM_OWNED_GAMES, status=200)
        responses.add(responses.GET, f"{STEAM_API_BASE}/ISteamUserStats/GetSchemaForGame/v2/",
                       json=STEAM_SCHEMA, status=200)
        responses.add(responses.GET, f"{STEAM_API_BASE}/ISteamUserStats/GetPlayerAchievements/v1/",
                       json=STEAM_PLAYER_ACHIEVEMENTS, status=200)
        responses.add(responses.GET, f"{STEAM_API_BASE}/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/",
                       json=STEAM_GLOBAL_STATS, status=200)

        pid = tracker.register_platform(
            "Steam", "steam", {"api_key": "FAKEKEY", "steam_id": "76561198000000000"}
        )
        tracker.import_achievements(pid)

        games = tracker.get_games(pid)
        game_stats = stats.get_game_stats(games[0].id)
        assert game_stats.total_achievements == 3
        assert game_stats.unlocked_count == 2
        assert game_stats.locked_count == 1
        assert game_stats.completion_pct == pytest.approx(66.67, abs=0.01)

        achs = tracker.get_achievements(games[0].id)
        unlocked = [a for a in achs if a.unlocked]
        locked = [a for a in achs if not a.unlocked]
        assert len(unlocked) == 2
        assert len(locked) == 1
