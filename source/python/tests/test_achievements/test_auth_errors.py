"""Tests for authentication error handling across providers."""

import pytest
import responses

from gamelibrary.database import Database
from gamelibrary.achievements.tracker import AchievementTracker
from gamelibrary.achievements.sync import SyncScheduler
from gamelibrary.achievements.platforms.base import AuthenticationError
from gamelibrary.achievements.platforms.steam import SteamProvider
from gamelibrary.achievements.platforms.xbox import XboxProvider
from gamelibrary.achievements.platforms.gog import GOGProvider
from gamelibrary.achievements.platforms.psn import PSNProvider


# --- Steam 401 ---

class TestSteam401:
    @responses.activate
    def test_get_games_401_raises_auth_error(self):
        responses.add(
            responses.GET,
            "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/",
            status=401,
        )
        provider = SteamProvider()
        provider.configure({"api_key": "bad_key", "steam_id": "123"})
        with pytest.raises(AuthenticationError, match="Steam"):
            provider.get_games()

    @responses.activate
    def test_get_schema_401_raises_auth_error(self):
        responses.add(
            responses.GET,
            "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/",
            status=403,
        )
        provider = SteamProvider()
        provider.configure({"api_key": "bad_key", "steam_id": "123"})
        with pytest.raises(AuthenticationError, match="Steam"):
            provider._get_achievement_schema("440")


# --- Xbox 401 ---

class TestXbox401:
    @responses.activate
    def test_get_games_401_raises_auth_error(self):
        responses.add(
            responses.GET,
            "https://xbl.io/api/v2/achievements",
            status=401,
        )
        provider = XboxProvider()
        provider.configure({"api_key": "bad_key", "xuid": "123"})
        with pytest.raises(AuthenticationError, match="Xbox"):
            provider.get_games()

    @responses.activate
    def test_get_achievements_403_raises_auth_error(self):
        responses.add(
            responses.GET,
            "https://xbl.io/api/v2/achievements/title/12345",
            status=403,
        )
        provider = XboxProvider()
        provider.configure({"api_key": "bad_key", "xuid": "123"})
        with pytest.raises(AuthenticationError, match="Xbox"):
            provider.get_achievements("12345")


# --- GOG 401 with refresh ---

class TestGOG401:
    @responses.activate
    def test_refresh_succeeds_on_401(self):
        """First request returns 401, refresh succeeds, retry returns 200."""
        # First call: 401
        responses.add(
            responses.GET,
            "https://embed.gog.com/account/getFilteredProducts",
            status=401,
        )
        # Refresh token call: success
        responses.add(
            responses.GET,
            "https://embed.gog.com/token",
            json={"access_token": "new_token", "refresh_token": "new_refresh", "user_id": "42"},
            status=200,
        )
        # Retry after refresh: success
        responses.add(
            responses.GET,
            "https://embed.gog.com/account/getFilteredProducts",
            json={"products": []},
            status=200,
        )
        provider = GOGProvider()
        provider.configure({
            "access_token": "old_token",
            "refresh_token": "valid_refresh",
            "client_id": "cid",
            "client_secret": "csecret",
            "user_id": "42",
        })
        result = provider.get_games()
        assert result == []  # No products, but no error
        assert provider.access_token == "new_token"

    @responses.activate
    def test_refresh_fails_raises_auth_error(self):
        """First request returns 401, refresh fails, raises AuthenticationError."""
        # First call: 401
        responses.add(
            responses.GET,
            "https://embed.gog.com/account/getFilteredProducts",
            status=401,
        )
        # Refresh token call: fails
        responses.add(
            responses.GET,
            "https://embed.gog.com/token",
            status=401,
        )
        provider = GOGProvider()
        provider.configure({
            "access_token": "old_token",
            "refresh_token": "bad_refresh",
            "client_id": "cid",
            "client_secret": "csecret",
            "user_id": "42",
        })
        with pytest.raises(AuthenticationError, match="GOG"):
            provider.get_games()

    def test_get_credentials_returns_current_state(self):
        provider = GOGProvider()
        provider.configure({
            "access_token": "tok",
            "refresh_token": "ref",
            "user_id": "uid",
            "client_id": "cid",
            "client_secret": "csec",
        })
        creds = provider.get_credentials()
        assert creds["access_token"] == "tok"
        assert creds["refresh_token"] == "ref"
        assert creds["client_id"] == "cid"


# --- PSN 401 with re-auth ---

class TestPSN401:
    @responses.activate
    def test_reauth_succeeds_on_401(self):
        """First request returns 401, re-auth succeeds, retry returns 200."""
        # First call: 401
        responses.add(
            responses.GET,
            "https://m.np.playstation.com/api/trophy/v1/users/me/trophyTitles",
            status=401,
        )
        # Re-authenticate: success
        responses.add(
            responses.POST,
            "https://ca.account.sony.com/api/authz/v3/oauth/token",
            json={"access_token": "new_psn_token"},
            status=200,
        )
        # Retry: success
        responses.add(
            responses.GET,
            "https://m.np.playstation.com/api/trophy/v1/users/me/trophyTitles",
            json={"trophyTitles": []},
            status=200,
        )
        provider = PSNProvider()
        provider.configure({
            "npsso": "valid_npsso",
            "access_token": "expired_token",
            "account_id": "me",
        })
        result = provider.get_games()
        assert result == []
        assert provider.access_token == "new_psn_token"

    @responses.activate
    def test_reauth_fails_raises_auth_error(self):
        """First request returns 401, re-auth fails, raises AuthenticationError."""
        # First call: 401
        responses.add(
            responses.GET,
            "https://m.np.playstation.com/api/trophy/v1/users/me/trophyTitles",
            status=401,
        )
        # Re-authenticate: fails
        responses.add(
            responses.POST,
            "https://ca.account.sony.com/api/authz/v3/oauth/token",
            status=401,
        )
        provider = PSNProvider()
        provider.configure({
            "npsso": "bad_npsso",
            "access_token": "expired_token",
            "account_id": "me",
        })
        with pytest.raises(AuthenticationError, match="PlayStation"):
            provider.get_games()

    def test_get_credentials_returns_current_state(self):
        provider = PSNProvider()
        provider.configure({
            "npsso": "npsso_val",
            "access_token": "tok_val",
            "account_id": "me",
        })
        creds = provider.get_credentials()
        assert creds["npsso"] == "npsso_val"
        assert creds["access_token"] == "tok_val"


# --- Tracker auth_failed sync status ---

class TestTrackerAuthFailed:
    def test_import_sets_auth_failed_status(self, tmp_path, monkeypatch):
        """When a provider raises AuthenticationError, sync status is 'auth_failed'."""
        db = Database(tmp_path / "test.db")
        tracker = AchievementTracker(db)
        pid = tracker.register_platform("BadSteam", "manual", {"platform_label": "Test"})

        # Monkeypatch import_achievements to simulate AuthenticationError
        def fake_get_games(self):
            raise AuthenticationError("Steam", "HTTP 401")

        from gamelibrary.achievements.platforms import manual as manual_mod
        monkeypatch.setattr(manual_mod.ManualProvider, "get_games", fake_get_games)

        with pytest.raises(AuthenticationError):
            tracker.import_achievements(pid)

        # Verify sync record has auth_failed status
        rows = db.execute("SELECT status FROM sync_history ORDER BY id DESC LIMIT 1")
        assert rows[0]["status"] == "auth_failed"


# --- Sync classification ---

class TestSyncAuthClassification:
    def test_sync_all_classifies_auth_failures(self, tmp_path, monkeypatch):
        """sync_all() reports auth failures with status 'auth_failed'."""
        db = Database(tmp_path / "test.db")
        tracker = AchievementTracker(db)
        tracker.register_platform("FailSteam", "steam", {"api_key": "bad", "steam_id": "123"})

        def fake_import(platform_id):
            raise AuthenticationError("Steam", "HTTP 401")

        scheduler = SyncScheduler(db)
        monkeypatch.setattr(scheduler.tracker, "import_achievements", fake_import)

        results = scheduler.sync_all()
        assert len(results) == 1
        assert results[0]["status"] == "auth_failed"
        assert "401" in results[0]["error"]


# --- Credential persistence after import ---

class TestCredentialPersistence:
    def test_credentials_persisted_after_import(self, tmp_path, monkeypatch):
        """After import, refreshed provider credentials are saved to DB."""
        db = Database(tmp_path / "test.db")
        tracker = AchievementTracker(db)
        pid = tracker.register_platform(
            "TestGOG", "manual", {"platform_label": "Test"},
        )

        # Monkeypatch to simulate a provider that returns updated credentials
        from gamelibrary.achievements.platforms import manual as manual_mod

        def fake_get_credentials(self):
            return {"access_token": "refreshed_token", "refresh_token": "new_ref"}

        monkeypatch.setattr(manual_mod.ManualProvider, "get_credentials", fake_get_credentials)
        monkeypatch.setattr(manual_mod.ManualProvider, "get_games", lambda self: [])

        tracker.import_achievements(pid)

        # Verify the DB row was updated with encrypted credentials
        from gamelibrary.achievements.credential_store import is_encrypted
        rows = db.execute("SELECT credentials FROM platforms WHERE id = ?", (pid,))
        stored = rows[0]["credentials"]
        assert is_encrypted(stored)
