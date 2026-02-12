"""
Playnite-Py: Modern Python Game Library Manager

A comprehensive game library manager with multi-profile support and
platform-specific configurations.

Example Usage:
    >>> from playnite_py import ProfileManager, ConfigurationManager
    >>> profile_mgr = ProfileManager()
    >>> profile = profile_mgr.create_profile("Gaming")
    >>> profile_mgr.switch_profile("Gaming")
"""

__version__ = "1.0.0"
__author__ = "Playnite Python Team"

from playnite_py.core.models.profile import Profile, ProfileSettings, ProfileTemplate
from playnite_py.core.models.game import Game, GameAction, GameMetadata
from playnite_py.core.models.configuration import (
    PlatformConfiguration,
    ConfigurationTemplate,
    LaunchArguments,
    EnvironmentConfig,
    DisplayConfig,
    AudioConfig,
)
from playnite_py.profiles.manager import ProfileManager
from playnite_py.configurations.manager import ConfigurationManager

__all__ = [
    # Version info
    "__version__",
    "__author__",
    # Profile models
    "Profile",
    "ProfileSettings",
    "ProfileTemplate",
    # Game models
    "Game",
    "GameAction",
    "GameMetadata",
    # Configuration models
    "PlatformConfiguration",
    "ConfigurationTemplate",
    "LaunchArguments",
    "EnvironmentConfig",
    "DisplayConfig",
    "AudioConfig",
    # Managers
    "ProfileManager",
    "ConfigurationManager",
]
