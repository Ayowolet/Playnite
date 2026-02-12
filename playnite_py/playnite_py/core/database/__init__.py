"""
Database layer for Playnite-Py.

This module provides the SQLAlchemy-based database layer for
persistent storage of profiles, games, and configurations.

The database uses SQLite for local storage with support for
profile-isolated databases.

Modules:
    engine: Database engine and session management
    models: SQLAlchemy ORM models
    repositories: Data access repositories
"""

from playnite_py.core.database.engine import (
    DatabaseEngine,
    get_database_url,
    create_engine_for_profile,
)
from playnite_py.core.database.repositories import (
    ProfileRepository,
    GameRepository,
    ConfigurationRepository,
)

__all__ = [
    "DatabaseEngine",
    "get_database_url",
    "create_engine_for_profile",
    "ProfileRepository",
    "GameRepository",
    "ConfigurationRepository",
]
