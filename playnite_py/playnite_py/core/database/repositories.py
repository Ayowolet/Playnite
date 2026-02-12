"""
Data access repositories for Playnite-Py.

This module provides repository classes for CRUD operations on
database entities, abstracting the SQLAlchemy layer from business logic.

Example:
    >>> from playnite_py.core.database import DatabaseEngine, ProfileRepository
    >>> db = DatabaseEngine.create_in_memory()
    >>> repo = ProfileRepository(db)
    >>> profile = repo.create(Profile(name="Test"))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Generic, Optional, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from playnite_py.core.database.engine import DatabaseEngine

from playnite_py.core.database.models import (
    Base,
    ConfigurationModel,
    ConfigurationTemplateModel,
    GameModel,
    ProfileAccessLogModel,
    ProfileModel,
    ProfileTemplateModel,
)
from playnite_py.core.models import (
    Game,
    GameAction,
    GameMetadata,
    GamePlayStatistics,
    GameSource,
    GameStatus,
    PlatformConfiguration,
    ConfigurationTemplate,
    DisplayConfig,
    AudioConfig,
    LaunchArguments,
    EnvironmentConfig,
    CompatibilityConfig,
    ConfigurationUsageStats,
    PlatformType,
    GraphicsQuality,
)
from playnite_py.core.models.profile import (
    Profile,
    ProfileSettings,
    ProfileStatistics,
    ProfileSecurity,
    ProfileSharing,
    ProfileTemplate,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Base)
M = TypeVar("M")


class BaseRepository(Generic[T, M]):
    """
    Base repository class with common CRUD operations.

    Provides a generic interface for database operations that can
    be specialized for specific entity types.

    Attributes:
        db: Database engine instance
        model_class: SQLAlchemy model class
    """

    model_class: type[T]

    def __init__(self, db: "DatabaseEngine") -> None:
        """
        Initialize the repository.

        Args:
            db: Database engine instance
        """
        self.db = db

    def _get_session(self) -> Session:
        """Get a new database session."""
        return self.db.create_session()


class ProfileRepository(BaseRepository[ProfileModel, Profile]):
    """
    Repository for profile operations.

    Provides CRUD operations for Profile entities, handling
    conversion between Pydantic models and SQLAlchemy models.

    Example:
        >>> repo = ProfileRepository(db)
        >>> profile = repo.create(Profile(name="Gaming"))
        >>> found = repo.get_by_name("Gaming")
    """

    model_class = ProfileModel

    def create(self, profile: Profile) -> Profile:
        """
        Create a new profile in the database.

        Args:
            profile: Profile to create

        Returns:
            Created profile with database ID

        Raises:
            ValueError: If profile name already exists

        Example:
            >>> profile = repo.create(Profile(name="New Profile"))
        """
        with self.db.session() as session:
            # Check for existing profile with same name
            existing = session.execute(
                select(ProfileModel).where(ProfileModel.name == profile.name)
            ).scalar_one_or_none()
            if existing:
                raise ValueError(f"Profile '{profile.name}' already exists")

            model = ProfileModel(
                id=str(profile.id),
                name=profile.name,
                description=profile.description,
                settings_json=profile.settings.model_dump(mode='json'),
                statistics_json=profile.statistics.model_dump(mode='json'),
                security_json=profile.security.model_dump(mode='json'),
                sharing_json=profile.sharing.model_dump(mode='json'),
                parent_profile_id=str(profile.parent_profile_id) if profile.parent_profile_id else None,
                data_directory=str(profile.data_directory) if profile.data_directory else None,
                is_active=profile.is_active,
                is_default=profile.is_default,
                created_from_template_id=str(profile.created_from_template_id) if profile.created_from_template_id else None,
                tags=profile.tags,
                icon_path=str(profile.icon_path) if profile.icon_path else None,
            )
            session.add(model)

        logger.info(f"Created profile: {profile.name}")
        return profile

    def get_by_id(self, profile_id: UUID) -> Optional[Profile]:
        """
        Get a profile by its ID.

        Args:
            profile_id: Profile UUID

        Returns:
            Profile if found, None otherwise

        Example:
            >>> profile = repo.get_by_id(uuid)
        """
        with self.db.session() as session:
            model = session.get(ProfileModel, str(profile_id))
            if model:
                return self._model_to_profile(model)
            return None

    def get_by_name(self, name: str) -> Optional[Profile]:
        """
        Get a profile by its name.

        Args:
            name: Profile name

        Returns:
            Profile if found, None otherwise

        Example:
            >>> profile = repo.get_by_name("Gaming")
        """
        with self.db.session() as session:
            model = session.execute(
                select(ProfileModel).where(ProfileModel.name == name)
            ).scalar_one_or_none()
            if model:
                return self._model_to_profile(model)
            return None

    def get_all(self) -> list[Profile]:
        """
        Get all profiles.

        Returns:
            List of all profiles

        Example:
            >>> profiles = repo.get_all()
        """
        with self.db.session() as session:
            models = session.execute(select(ProfileModel)).scalars().all()
            return [self._model_to_profile(m) for m in models]

    def get_active(self) -> Optional[Profile]:
        """
        Get the currently active profile.

        Returns:
            Active profile if any, None otherwise
        """
        with self.db.session() as session:
            model = session.execute(
                select(ProfileModel).where(ProfileModel.is_active == True)
            ).scalar_one_or_none()
            if model:
                return self._model_to_profile(model)
            return None

    def get_default(self) -> Optional[Profile]:
        """
        Get the default profile.

        Returns:
            Default profile if set, None otherwise
        """
        with self.db.session() as session:
            model = session.execute(
                select(ProfileModel).where(ProfileModel.is_default == True)
            ).scalar_one_or_none()
            if model:
                return self._model_to_profile(model)
            return None

    def update(self, profile: Profile) -> Profile:
        """
        Update an existing profile.

        Args:
            profile: Profile with updated data

        Returns:
            Updated profile

        Raises:
            ValueError: If profile not found

        Example:
            >>> profile.settings.theme = "dark"
            >>> repo.update(profile)
        """
        with self.db.session() as session:
            model = session.get(ProfileModel, str(profile.id))
            if not model:
                raise ValueError(f"Profile not found: {profile.id}")

            model.name = profile.name
            model.description = profile.description
            model.settings_json = profile.settings.model_dump(mode='json')
            model.statistics_json = profile.statistics.model_dump(mode='json')
            model.security_json = profile.security.model_dump(mode='json')
            model.sharing_json = profile.sharing.model_dump(mode='json')
            model.parent_profile_id = str(profile.parent_profile_id) if profile.parent_profile_id else None
            model.data_directory = str(profile.data_directory) if profile.data_directory else None
            model.is_active = profile.is_active
            model.is_default = profile.is_default
            model.tags = profile.tags
            model.icon_path = str(profile.icon_path) if profile.icon_path else None

        logger.info(f"Updated profile: {profile.name}")
        return profile

    def delete(self, profile_id: UUID) -> bool:
        """
        Delete a profile.

        Args:
            profile_id: Profile UUID to delete

        Returns:
            True if deleted, False if not found

        Example:
            >>> repo.delete(profile.id)
        """
        with self.db.session() as session:
            model = session.get(ProfileModel, str(profile_id))
            if model:
                session.delete(model)
                logger.info(f"Deleted profile: {model.name}")
                return True
            return False

    def set_active(self, profile_id: UUID) -> None:
        """
        Set a profile as active, deactivating others.

        Args:
            profile_id: Profile UUID to activate

        Raises:
            ValueError: If profile not found
        """
        with self.db.session() as session:
            # Deactivate all profiles
            session.execute(
                ProfileModel.__table__.update().values(is_active=False)
            )
            # Activate the specified profile
            model = session.get(ProfileModel, str(profile_id))
            if not model:
                raise ValueError(f"Profile not found: {profile_id}")
            model.is_active = True
            logger.info(f"Activated profile: {model.name}")

    def set_default(self, profile_id: UUID) -> None:
        """
        Set a profile as the default.

        Args:
            profile_id: Profile UUID to set as default

        Raises:
            ValueError: If profile not found
        """
        with self.db.session() as session:
            # Clear existing default
            session.execute(
                ProfileModel.__table__.update().values(is_default=False)
            )
            # Set new default
            model = session.get(ProfileModel, str(profile_id))
            if not model:
                raise ValueError(f"Profile not found: {profile_id}")
            model.is_default = True
            logger.info(f"Set default profile: {model.name}")

    def log_access(
        self,
        profile_id: UUID,
        event_type: str,
        success: bool = True,
        details: Optional[dict] = None,
    ) -> None:
        """
        Log a profile access event.

        Args:
            profile_id: Profile that was accessed
            event_type: Type of access event
            success: Whether access was successful
            details: Additional event details
        """
        with self.db.session() as session:
            log = ProfileAccessLogModel(
                profile_id=str(profile_id),
                event_type=event_type,
                success=success,
                details=details or {},
            )
            session.add(log)

    def _model_to_profile(self, model: ProfileModel) -> Profile:
        """Convert SQLAlchemy model to Pydantic model."""
        return Profile(
            id=UUID(model.id),
            name=model.name,
            description=model.description,
            settings=ProfileSettings(**model.settings_json),
            statistics=ProfileStatistics(**model.statistics_json),
            security=ProfileSecurity(**model.security_json),
            sharing=ProfileSharing(**model.sharing_json),
            parent_profile_id=UUID(model.parent_profile_id) if model.parent_profile_id else None,
            data_directory=Path(model.data_directory) if model.data_directory else None,
            is_active=model.is_active,
            is_default=model.is_default,
            created_from_template_id=UUID(model.created_from_template_id) if model.created_from_template_id else None,
            tags=model.tags,
            icon_path=Path(model.icon_path) if model.icon_path else None,
        )


class ProfileTemplateRepository(BaseRepository[ProfileTemplateModel, ProfileTemplate]):
    """
    Repository for profile template operations.

    Example:
        >>> repo = ProfileTemplateRepository(db)
        >>> template = repo.create(ProfileTemplate(name="Default"))
    """

    model_class = ProfileTemplateModel

    def create(self, template: ProfileTemplate) -> ProfileTemplate:
        """Create a new template."""
        with self.db.session() as session:
            model = ProfileTemplateModel(
                id=str(template.id),
                name=template.name,
                description=template.description,
                settings_json=template.settings.model_dump(mode='json'),
                sharing_json=template.sharing.model_dump(mode='json'),
                is_builtin=template.is_builtin,
                source_profile_id=str(template.source_profile_id) if template.source_profile_id else None,
            )
            session.add(model)
        return template

    def get_by_id(self, template_id: UUID) -> Optional[ProfileTemplate]:
        """Get a template by ID."""
        with self.db.session() as session:
            model = session.get(ProfileTemplateModel, str(template_id))
            if model:
                return self._model_to_template(model)
            return None

    def get_by_name(self, name: str) -> Optional[ProfileTemplate]:
        """Get a template by name."""
        with self.db.session() as session:
            model = session.execute(
                select(ProfileTemplateModel).where(ProfileTemplateModel.name == name)
            ).scalar_one_or_none()
            if model:
                return self._model_to_template(model)
            return None

    def get_all(self) -> list[ProfileTemplate]:
        """Get all templates."""
        with self.db.session() as session:
            models = session.execute(select(ProfileTemplateModel)).scalars().all()
            return [self._model_to_template(m) for m in models]

    def get_builtin(self) -> list[ProfileTemplate]:
        """Get all builtin templates."""
        with self.db.session() as session:
            models = session.execute(
                select(ProfileTemplateModel).where(ProfileTemplateModel.is_builtin == True)
            ).scalars().all()
            return [self._model_to_template(m) for m in models]

    def delete(self, template_id: UUID) -> bool:
        """Delete a template."""
        with self.db.session() as session:
            model = session.get(ProfileTemplateModel, str(template_id))
            if model:
                session.delete(model)
                return True
            return False

    def _model_to_template(self, model: ProfileTemplateModel) -> ProfileTemplate:
        """Convert SQLAlchemy model to Pydantic model."""
        return ProfileTemplate(
            id=UUID(model.id),
            name=model.name,
            description=model.description,
            settings=ProfileSettings(**model.settings_json),
            sharing=ProfileSharing(**model.sharing_json),
            is_builtin=model.is_builtin,
            source_profile_id=UUID(model.source_profile_id) if model.source_profile_id else None,
            created_at=model.created_at,
        )


class GameRepository(BaseRepository[GameModel, Game]):
    """
    Repository for game operations.

    Provides CRUD operations for Game entities within a profile's
    isolated database.

    Example:
        >>> repo = GameRepository(db)
        >>> game = repo.create(Game(name="Cyberpunk 2077"))
    """

    model_class = GameModel

    def create(self, game: Game) -> Game:
        """
        Create a new game in the database.

        Args:
            game: Game to create

        Returns:
            Created game

        Example:
            >>> game = repo.create(Game(name="New Game"))
        """
        with self.db.session() as session:
            model = GameModel(
                id=str(game.id),
                name=game.name,
                sorting_name=game.sorting_name,
                source=game.source.value,
                source_game_id=game.source_game_id,
                status=game.status.value,
                metadata_json=game.metadata.model_dump(mode='json'),
                statistics_json=game.statistics.model_dump(mode='json'),
                actions_json=[a.model_dump(mode='json') for a in game.actions],
                install_directory=str(game.install_directory) if game.install_directory else None,
                icon_path=str(game.icon_path) if game.icon_path else None,
                cover_image_path=str(game.cover_image_path) if game.cover_image_path else None,
                background_image_path=str(game.background_image_path) if game.background_image_path else None,
                is_hidden=game.is_hidden,
                is_favorite=game.is_favorite,
                notes=game.notes,
                configuration_ids=[str(c) for c in game.configuration_ids],
            )
            session.add(model)

        logger.info(f"Created game: {game.name}")
        return game

    def get_by_id(self, game_id: UUID) -> Optional[Game]:
        """Get a game by ID."""
        with self.db.session() as session:
            model = session.get(GameModel, str(game_id))
            if model:
                return self._model_to_game(model)
            return None

    def get_by_name(self, name: str) -> Optional[Game]:
        """Get a game by name."""
        with self.db.session() as session:
            model = session.execute(
                select(GameModel).where(GameModel.name == name)
            ).scalar_one_or_none()
            if model:
                return self._model_to_game(model)
            return None

    def get_all(self) -> list[Game]:
        """Get all games."""
        with self.db.session() as session:
            models = session.execute(select(GameModel)).scalars().all()
            return [self._model_to_game(m) for m in models]

    def get_by_source(self, source: GameSource) -> list[Game]:
        """Get games by source platform."""
        with self.db.session() as session:
            models = session.execute(
                select(GameModel).where(GameModel.source == source.value)
            ).scalars().all()
            return [self._model_to_game(m) for m in models]

    def get_favorites(self) -> list[Game]:
        """Get all favorite games."""
        with self.db.session() as session:
            models = session.execute(
                select(GameModel).where(GameModel.is_favorite == True)
            ).scalars().all()
            return [self._model_to_game(m) for m in models]

    def search(self, query: str) -> list[Game]:
        """
        Search games by name.

        Args:
            query: Search query string

        Returns:
            List of matching games
        """
        with self.db.session() as session:
            models = session.execute(
                select(GameModel).where(GameModel.name.ilike(f"%{query}%"))
            ).scalars().all()
            return [self._model_to_game(m) for m in models]

    def update(self, game: Game) -> Game:
        """Update an existing game."""
        with self.db.session() as session:
            model = session.get(GameModel, str(game.id))
            if not model:
                raise ValueError(f"Game not found: {game.id}")

            model.name = game.name
            model.sorting_name = game.sorting_name
            model.source = game.source.value
            model.source_game_id = game.source_game_id
            model.status = game.status.value
            model.metadata_json = game.metadata.model_dump(mode='json')
            model.statistics_json = game.statistics.model_dump(mode='json')
            model.actions_json = [a.model_dump(mode='json') for a in game.actions]
            model.install_directory = str(game.install_directory) if game.install_directory else None
            model.icon_path = str(game.icon_path) if game.icon_path else None
            model.cover_image_path = str(game.cover_image_path) if game.cover_image_path else None
            model.background_image_path = str(game.background_image_path) if game.background_image_path else None
            model.is_hidden = game.is_hidden
            model.is_favorite = game.is_favorite
            model.notes = game.notes
            model.configuration_ids = [str(c) for c in game.configuration_ids]

        logger.info(f"Updated game: {game.name}")
        return game

    def delete(self, game_id: UUID) -> bool:
        """Delete a game."""
        with self.db.session() as session:
            model = session.get(GameModel, str(game_id))
            if model:
                session.delete(model)
                logger.info(f"Deleted game: {model.name}")
                return True
            return False

    def count(self) -> int:
        """Get total game count."""
        with self.db.session() as session:
            return session.query(GameModel).count()

    def _model_to_game(self, model: GameModel) -> Game:
        """Convert SQLAlchemy model to Pydantic model."""
        return Game(
            id=UUID(model.id),
            name=model.name,
            sorting_name=model.sorting_name,
            source=GameSource(model.source),
            source_game_id=model.source_game_id,
            status=GameStatus(model.status),
            metadata=GameMetadata(**model.metadata_json),
            statistics=GamePlayStatistics(**model.statistics_json),
            actions=[GameAction(**a) for a in model.actions_json],
            install_directory=Path(model.install_directory) if model.install_directory else None,
            icon_path=Path(model.icon_path) if model.icon_path else None,
            cover_image_path=Path(model.cover_image_path) if model.cover_image_path else None,
            background_image_path=Path(model.background_image_path) if model.background_image_path else None,
            is_hidden=model.is_hidden,
            is_favorite=model.is_favorite,
            notes=model.notes,
            configuration_ids=[UUID(c) for c in model.configuration_ids],
            added_date=model.added_date,
            modified_date=model.modified_date,
        )


class ConfigurationRepository(BaseRepository[ConfigurationModel, PlatformConfiguration]):
    """
    Repository for configuration operations.

    Example:
        >>> repo = ConfigurationRepository(db)
        >>> config = repo.create(PlatformConfiguration(name="Desktop", game_id=game.id))
    """

    model_class = ConfigurationModel

    def create(self, config: PlatformConfiguration) -> PlatformConfiguration:
        """Create a new configuration."""
        with self.db.session() as session:
            model = ConfigurationModel(
                id=str(config.id),
                name=config.name,
                description=config.description,
                game_id=str(config.game_id),
                platform_type=config.platform_type.value,
                graphics_quality=config.graphics_quality.value,
                display_json=config.display.model_dump(mode='json'),
                audio_json=config.audio.model_dump(mode='json'),
                launch_args_json=config.launch_args.model_dump(mode='json'),
                environment_json=config.environment.model_dump(mode='json'),
                compatibility_json=config.compatibility.model_dump(mode='json'),
                working_directory=str(config.working_directory) if config.working_directory else None,
                pre_launch_script=config.pre_launch_script,
                post_launch_script=config.post_launch_script,
                is_default=config.is_default,
                is_enabled=config.is_enabled,
                fallback_config_id=str(config.fallback_config_id) if config.fallback_config_id else None,
                priority=config.priority,
                statistics_json=config.statistics.model_dump(mode='json'),
                hardware_requirements=config.hardware_requirements,
                tags=config.tags,
            )
            session.add(model)

        logger.info(f"Created configuration: {config.name}")
        return config

    def get_by_id(self, config_id: UUID) -> Optional[PlatformConfiguration]:
        """Get a configuration by ID."""
        with self.db.session() as session:
            model = session.get(ConfigurationModel, str(config_id))
            if model:
                return self._model_to_config(model)
            return None

    def get_by_game_id(self, game_id: UUID) -> list[PlatformConfiguration]:
        """Get all configurations for a game."""
        with self.db.session() as session:
            models = session.execute(
                select(ConfigurationModel).where(ConfigurationModel.game_id == str(game_id))
            ).scalars().all()
            return [self._model_to_config(m) for m in models]

    def get_default_for_game(self, game_id: UUID) -> Optional[PlatformConfiguration]:
        """Get the default configuration for a game."""
        with self.db.session() as session:
            model = session.execute(
                select(ConfigurationModel).where(
                    ConfigurationModel.game_id == str(game_id),
                    ConfigurationModel.is_default == True,
                )
            ).scalar_one_or_none()
            if model:
                return self._model_to_config(model)
            return None

    def get_by_platform_type(
        self, game_id: UUID, platform_type: PlatformType
    ) -> list[PlatformConfiguration]:
        """Get configurations for a game by platform type."""
        with self.db.session() as session:
            models = session.execute(
                select(ConfigurationModel).where(
                    ConfigurationModel.game_id == str(game_id),
                    ConfigurationModel.platform_type == platform_type.value,
                )
            ).scalars().all()
            return [self._model_to_config(m) for m in models]

    def get_all(self) -> list[PlatformConfiguration]:
        """Get all configurations."""
        with self.db.session() as session:
            models = session.execute(select(ConfigurationModel)).scalars().all()
            return [self._model_to_config(m) for m in models]

    def update(self, config: PlatformConfiguration) -> PlatformConfiguration:
        """Update an existing configuration."""
        with self.db.session() as session:
            model = session.get(ConfigurationModel, str(config.id))
            if not model:
                raise ValueError(f"Configuration not found: {config.id}")

            model.name = config.name
            model.description = config.description
            model.platform_type = config.platform_type.value
            model.graphics_quality = config.graphics_quality.value
            model.display_json = config.display.model_dump(mode='json')
            model.audio_json = config.audio.model_dump(mode='json')
            model.launch_args_json = config.launch_args.model_dump(mode='json')
            model.environment_json = config.environment.model_dump(mode='json')
            model.compatibility_json = config.compatibility.model_dump(mode='json')
            model.working_directory = str(config.working_directory) if config.working_directory else None
            model.pre_launch_script = config.pre_launch_script
            model.post_launch_script = config.post_launch_script
            model.is_default = config.is_default
            model.is_enabled = config.is_enabled
            model.fallback_config_id = str(config.fallback_config_id) if config.fallback_config_id else None
            model.priority = config.priority
            model.statistics_json = config.statistics.model_dump(mode='json')
            model.hardware_requirements = config.hardware_requirements
            model.tags = config.tags

        logger.info(f"Updated configuration: {config.name}")
        return config

    def delete(self, config_id: UUID) -> bool:
        """Delete a configuration."""
        with self.db.session() as session:
            model = session.get(ConfigurationModel, str(config_id))
            if model:
                session.delete(model)
                logger.info(f"Deleted configuration: {model.name}")
                return True
            return False

    def set_default(self, config_id: UUID, game_id: UUID) -> None:
        """Set a configuration as the default for its game."""
        with self.db.session() as session:
            # Clear existing default for this game
            session.execute(
                ConfigurationModel.__table__.update()
                .where(ConfigurationModel.game_id == str(game_id))
                .values(is_default=False)
            )
            # Set new default
            model = session.get(ConfigurationModel, str(config_id))
            if model:
                model.is_default = True

    def _model_to_config(self, model: ConfigurationModel) -> PlatformConfiguration:
        """Convert SQLAlchemy model to Pydantic model."""
        return PlatformConfiguration(
            id=UUID(model.id),
            name=model.name,
            description=model.description,
            game_id=UUID(model.game_id),
            platform_type=PlatformType(model.platform_type),
            graphics_quality=GraphicsQuality(model.graphics_quality),
            display=DisplayConfig(**model.display_json),
            audio=AudioConfig(**model.audio_json),
            launch_args=LaunchArguments(**model.launch_args_json),
            environment=EnvironmentConfig(**model.environment_json),
            compatibility=CompatibilityConfig(**model.compatibility_json),
            working_directory=Path(model.working_directory) if model.working_directory else None,
            pre_launch_script=model.pre_launch_script,
            post_launch_script=model.post_launch_script,
            is_default=model.is_default,
            is_enabled=model.is_enabled,
            fallback_config_id=UUID(model.fallback_config_id) if model.fallback_config_id else None,
            priority=model.priority,
            statistics=ConfigurationUsageStats(**model.statistics_json),
            hardware_requirements=model.hardware_requirements,
            tags=model.tags,
            created_at=model.created_at,
            modified_at=model.modified_at,
        )


class ConfigurationTemplateRepository(BaseRepository[ConfigurationTemplateModel, ConfigurationTemplate]):
    """
    Repository for configuration template operations.

    Example:
        >>> repo = ConfigurationTemplateRepository(db)
        >>> template = repo.create(ConfigurationTemplate(name="Performance"))
    """

    model_class = ConfigurationTemplateModel

    def create(self, template: ConfigurationTemplate) -> ConfigurationTemplate:
        """Create a new template."""
        with self.db.session() as session:
            model = ConfigurationTemplateModel(
                id=str(template.id),
                name=template.name,
                description=template.description,
                platform_type=template.platform_type.value,
                graphics_quality=template.graphics_quality.value,
                display_json=template.display.model_dump(mode='json'),
                audio_json=template.audio.model_dump(mode='json'),
                launch_args_json=template.launch_args.model_dump(mode='json'),
                environment_json=template.environment.model_dump(mode='json'),
                compatibility_json=template.compatibility.model_dump(mode='json'),
                is_builtin=template.is_builtin,
            )
            session.add(model)
        return template

    def get_by_id(self, template_id: UUID) -> Optional[ConfigurationTemplate]:
        """Get a template by ID."""
        with self.db.session() as session:
            model = session.get(ConfigurationTemplateModel, str(template_id))
            if model:
                return self._model_to_template(model)
            return None

    def get_by_name(self, name: str) -> Optional[ConfigurationTemplate]:
        """Get a template by name."""
        with self.db.session() as session:
            model = session.execute(
                select(ConfigurationTemplateModel).where(ConfigurationTemplateModel.name == name)
            ).scalar_one_or_none()
            if model:
                return self._model_to_template(model)
            return None

    def get_all(self) -> list[ConfigurationTemplate]:
        """Get all templates."""
        with self.db.session() as session:
            models = session.execute(select(ConfigurationTemplateModel)).scalars().all()
            return [self._model_to_template(m) for m in models]

    def get_builtin(self) -> list[ConfigurationTemplate]:
        """Get all builtin templates."""
        with self.db.session() as session:
            models = session.execute(
                select(ConfigurationTemplateModel).where(ConfigurationTemplateModel.is_builtin == True)
            ).scalars().all()
            return [self._model_to_template(m) for m in models]

    def delete(self, template_id: UUID) -> bool:
        """Delete a template."""
        with self.db.session() as session:
            model = session.get(ConfigurationTemplateModel, str(template_id))
            if model:
                session.delete(model)
                return True
            return False

    def _model_to_template(self, model: ConfigurationTemplateModel) -> ConfigurationTemplate:
        """Convert SQLAlchemy model to Pydantic model."""
        return ConfigurationTemplate(
            id=UUID(model.id),
            name=model.name,
            description=model.description,
            platform_type=PlatformType(model.platform_type),
            graphics_quality=GraphicsQuality(model.graphics_quality),
            display=DisplayConfig(**model.display_json),
            audio=AudioConfig(**model.audio_json),
            launch_args=LaunchArguments(**model.launch_args_json),
            environment=EnvironmentConfig(**model.environment_json),
            compatibility=CompatibilityConfig(**model.compatibility_json),
            is_builtin=model.is_builtin,
            created_at=model.created_at,
        )
