"""
Core module for Playnite-Py.

This module contains the fundamental data models, database layer,
and core services that power the game library manager.

Modules:
    models: Pydantic data models for profiles, games, and configurations
    database: SQLAlchemy database layer for persistent storage
    services: Core business logic services
"""

from playnite_py.core.models import (
    Profile,
    ProfileSettings,
    ProfileTemplate,
    Game,
    GameAction,
    GameMetadata,
    PlatformConfiguration,
    ConfigurationTemplate,
)

__all__ = [
    "Profile",
    "ProfileSettings",
    "ProfileTemplate",
    "Game",
    "GameAction",
    "GameMetadata",
    "PlatformConfiguration",
    "ConfigurationTemplate",
]
