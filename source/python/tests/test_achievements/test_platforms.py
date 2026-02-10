"""Tests for platform providers and difficulty models."""

import pytest

from gamelibrary.achievements.platforms.manual import ManualProvider
from gamelibrary.achievements.platforms.steam import SteamProvider
from gamelibrary.achievements.platforms.xbox import XboxProvider
from gamelibrary.achievements.platforms.psn import PSNProvider
from gamelibrary.achievements.platforms.gog import GOGProvider
from gamelibrary.achievements.platforms.base import PlatformGame, PlatformAchievement
from gamelibrary.models import DifficultyTier
from gamelibrary.achievements.tracker import _calculate_difficulty_score


class TestManualProvider:
    def test_manual_provider_validate(self):
        """ManualProvider.validate_credentials always returns True."""
        provider = ManualProvider()
        assert provider.validate_credentials() is True

    def test_manual_provider_create_game(self):
        """ManualProvider.create_game returns a PlatformGame with the given name."""
        provider = ManualProvider()
        game = provider.create_game("My RPG", game_id="rpg-1")
        assert isinstance(game, PlatformGame)
        assert game.name == "My RPG"
        assert game.external_id == "rpg-1"

    def test_manual_provider_create_achievement(self):
        """ManualProvider.create_achievement returns a PlatformAchievement with correct fields."""
        provider = ManualProvider()
        ach = provider.create_achievement(
            name="Boss Slayer",
            description="Defeat the final boss",
            unlocked=True,
            unlock_time="2025-05-01T00:00:00",
            global_completion_pct=12.5,
            max_progress=0,
            current_progress=0,
        )
        assert isinstance(ach, PlatformAchievement)
        assert ach.name == "Boss Slayer"
        assert ach.unlocked is True
        assert ach.global_completion_pct == 12.5
        assert ach.unlock_time == "2025-05-01T00:00:00"


class TestSteamProviderProperties:
    def test_steam_provider_properties(self):
        """SteamProvider has correct platform_name and api_type."""
        provider = SteamProvider()
        assert provider.platform_name == "Steam"
        assert provider.api_type == "steam"


class TestXboxProviderProperties:
    def test_xbox_provider_properties(self):
        """XboxProvider has correct platform_name and api_type."""
        provider = XboxProvider()
        assert provider.platform_name == "Xbox Live"
        assert provider.api_type == "xbox"


class TestPSNProviderProperties:
    def test_psn_provider_properties(self):
        """PSNProvider has correct platform_name and api_type."""
        provider = PSNProvider()
        assert provider.platform_name == "PlayStation Network"
        assert provider.api_type == "psn"


class TestGOGProviderProperties:
    def test_gog_provider_properties(self):
        """GOGProvider has correct platform_name and api_type."""
        provider = GOGProvider()
        assert provider.platform_name == "GOG Galaxy"
        assert provider.api_type == "gog"


class TestDifficultyTier:
    @pytest.mark.parametrize(
        "pct, expected_tier",
        [
            (75.0, DifficultyTier.COMMON),       # >= 50
            (50.0, DifficultyTier.COMMON),        # boundary
            (30.0, DifficultyTier.UNCOMMON),      # >= 25, < 50
            (25.0, DifficultyTier.UNCOMMON),      # boundary
            (15.0, DifficultyTier.RARE),          # >= 10, < 25
            (10.0, DifficultyTier.RARE),          # boundary
            (5.0, DifficultyTier.VERY_RARE),      # >= 2, < 10
            (2.0, DifficultyTier.VERY_RARE),      # boundary
            (1.0, DifficultyTier.ULTRA_RARE),     # < 2
        ],
    )
    def test_difficulty_tier_from_pct(self, pct, expected_tier):
        """DifficultyTier.from_global_pct maps percentages to the correct tier."""
        assert DifficultyTier.from_global_pct(pct) == expected_tier


class TestDifficultyScore:
    def test_difficulty_score_calculation(self):
        """_calculate_difficulty_score returns 100 - pct, clamped to [0, 100]."""
        assert _calculate_difficulty_score(0.0) == 100.0
        assert _calculate_difficulty_score(100.0) == 0.0
        assert _calculate_difficulty_score(30.0) == 70.0
        assert _calculate_difficulty_score(75.5) == 24.5
        # Edge: negative pct treated as 0 -> 100
        assert _calculate_difficulty_score(-5.0) == 100.0
