"""
Data models for Playnite-Py.

This module defines all Pydantic models used throughout the application
for data validation, serialization, and type safety.

Models are organized into:
    - Profile models: User profiles, settings, templates
    - Game models: Game entries, actions, metadata
    - Configuration models: Platform configurations, presets
"""

from playnite_py.core.models.profile import (
    Profile,
    ProfileSettings,
    ProfileTemplate,
    ProfileStatistics,
    ProfileSecurity,
    ProfileSharing,
    DataSharingMode,
)
from playnite_py.core.models.game import (
    Game,
    GameAction,
    GameActionType,
    GameMetadata,
    GamePlayStatistics,
    GameStatus,
    GameSource,
)
from playnite_py.core.models.configuration import (
    PlatformConfiguration,
    ConfigurationTemplate,
    LaunchArguments,
    EnvironmentConfig,
    DisplayConfig,
    AudioConfig,
    CompatibilityConfig,
    ConfigurationUsageStats,
    PlatformType,
    GraphicsQuality,
)

__all__ = [
    # Profile models
    "Profile",
    "ProfileSettings",
    "ProfileTemplate",
    "ProfileStatistics",
    "ProfileSecurity",
    "ProfileSharing",
    "DataSharingMode",
    # Game models
    "Game",
    "GameAction",
    "GameActionType",
    "GameMetadata",
    "GamePlayStatistics",
    "GameStatus",
    "GameSource",
    # Configuration models
    "PlatformConfiguration",
    "ConfigurationTemplate",
    "LaunchArguments",
    "EnvironmentConfig",
    "DisplayConfig",
    "AudioConfig",
    "CompatibilityConfig",
    "ConfigurationUsageStats",
    "PlatformType",
    "GraphicsQuality",
]
