"""
Pytest configuration and shared fixtures for Playnite-Py tests.

This module provides fixtures used across all test modules.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Generator
from uuid import uuid4

import pytest

from playnite_py.core.database.engine import DatabaseEngine
from playnite_py.core.database.repositories import (
    ProfileRepository,
    GameRepository,
    ConfigurationRepository,
    ProfileTemplateRepository,
    ConfigurationTemplateRepository,
)
from playnite_py.core.models.profile import (
    Profile,
    ProfileSettings,
    ProfileTemplate,
)
from playnite_py.core.models.game import Game, GameAction, GameActionType, GameSource
from playnite_py.core.models.configuration import (
    PlatformConfiguration,
    ConfigurationTemplate,
    PlatformType,
    GraphicsQuality,
    DisplayConfig,
)
from playnite_py.profiles.manager import ProfileManager


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def in_memory_db() -> Generator[DatabaseEngine, None, None]:
    """Create an in-memory database for tests."""
    db = DatabaseEngine.create_in_memory()
    yield db
    db.close()


@pytest.fixture
def temp_db(temp_dir: Path) -> Generator[DatabaseEngine, None, None]:
    """Create a temporary file-based database for tests."""
    db = DatabaseEngine.create_for_profile(temp_dir)
    yield db
    db.close()


@pytest.fixture
def profile_repo(in_memory_db: DatabaseEngine) -> ProfileRepository:
    """Create a ProfileRepository with in-memory database."""
    return ProfileRepository(in_memory_db)


@pytest.fixture
def template_repo(in_memory_db: DatabaseEngine) -> ProfileTemplateRepository:
    """Create a ProfileTemplateRepository with in-memory database."""
    return ProfileTemplateRepository(in_memory_db)


@pytest.fixture
def game_repo(in_memory_db: DatabaseEngine) -> GameRepository:
    """Create a GameRepository with in-memory database."""
    return GameRepository(in_memory_db)


@pytest.fixture
def config_repo(in_memory_db: DatabaseEngine) -> ConfigurationRepository:
    """Create a ConfigurationRepository with in-memory database."""
    return ConfigurationRepository(in_memory_db)


@pytest.fixture
def config_template_repo(in_memory_db: DatabaseEngine) -> ConfigurationTemplateRepository:
    """Create a ConfigurationTemplateRepository with in-memory database."""
    return ConfigurationTemplateRepository(in_memory_db)


@pytest.fixture
def profile_manager(temp_dir: Path) -> Generator[ProfileManager, None, None]:
    """Create a ProfileManager with temporary data directory."""
    manager = ProfileManager(temp_dir)
    yield manager
    manager.close()


@pytest.fixture
def sample_profile() -> Profile:
    """Create a sample profile for testing."""
    return Profile(
        name="Test Profile",
        description="A test profile",
        settings=ProfileSettings(
            theme="dark",
            language="en",
            default_view="grid",
        ),
    )


@pytest.fixture
def sample_template() -> ProfileTemplate:
    """Create a sample profile template for testing."""
    return ProfileTemplate(
        name="Test Template",
        description="A test template",
        settings=ProfileSettings(
            theme="light",
            language="en",
        ),
        is_builtin=False,
    )


@pytest.fixture
def sample_game() -> Game:
    """Create a sample game for testing."""
    game = Game(
        name="Test Game",
        source=GameSource.MANUAL,
    )
    game.actions.append(
        GameAction(
            name="Play",
            type=GameActionType.FILE,
            path="/path/to/game.exe",
            is_default=True,
        )
    )
    return game


@pytest.fixture
def sample_config(sample_game: Game) -> PlatformConfiguration:
    """Create a sample configuration for testing."""
    return PlatformConfiguration(
        name="Desktop",
        game_id=sample_game.id,
        platform_type=PlatformType.DESKTOP,
        graphics_quality=GraphicsQuality.HIGH,
        display=DisplayConfig(
            width=1920,
            height=1080,
            fullscreen=True,
        ),
    )


@pytest.fixture
def sample_config_template() -> ConfigurationTemplate:
    """Create a sample configuration template for testing."""
    return ConfigurationTemplate(
        name="Test Config Template",
        description="A test config template",
        platform_type=PlatformType.DESKTOP,
        graphics_quality=GraphicsQuality.MEDIUM,
        is_builtin=False,
    )
