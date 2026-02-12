"""
Configuration manager for Playnite-Py.

This module provides the main ConfigurationManager class that handles
all platform-specific game configuration operations.

Example:
    >>> from playnite_py.configurations import ConfigurationManager
    >>> manager = ConfigurationManager(db)
    >>> config = manager.create_configuration(game_id, "Desktop")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

if TYPE_CHECKING:
    from playnite_py.core.database.engine import DatabaseEngine

from playnite_py.core.database.repositories import (
    ConfigurationRepository,
    ConfigurationTemplateRepository,
    GameRepository,
)
from playnite_py.core.models.configuration import (
    PlatformConfiguration,
    ConfigurationTemplate,
    LaunchArguments,
    EnvironmentConfig,
    DisplayConfig,
    AudioConfig,
    CompatibilityConfig,
    PlatformType,
    GraphicsQuality,
)
from playnite_py.configurations.detection import (
    PlatformDetector,
    detect_current_platform,
)
from playnite_py.configurations.templates import (
    ConfigTemplateManager,
    get_builtin_config_templates,
)

logger = logging.getLogger(__name__)


class ConfigurationManager:
    """
    Central manager for platform-specific game configurations.

    Handles creation, modification, and application of platform
    configurations for games.

    Attributes:
        db: Database engine for the current profile
        config_repo: Configuration repository
        template_repo: Template repository
        game_repo: Game repository
        platform_detector: Platform detection utility
        template_manager: Configuration template manager

    Example:
        >>> manager = ConfigurationManager(db)
        >>> config = manager.create_configuration(
        ...     game_id, "Desktop High",
        ...     platform_type=PlatformType.DESKTOP,
        ...     preset="quality"
        ... )
    """

    def __init__(self, db: "DatabaseEngine") -> None:
        """
        Initialize the configuration manager.

        Args:
            db: Database engine for the current profile
        """
        self.db = db
        self.config_repo = ConfigurationRepository(db)
        self.template_repo = ConfigurationTemplateRepository(db)
        self.game_repo = GameRepository(db)
        self.platform_detector = PlatformDetector()
        self.template_manager = ConfigTemplateManager(self.template_repo)

        # Ensure builtin templates exist
        self._ensure_builtin_templates()

    def _ensure_builtin_templates(self) -> None:
        """Ensure builtin configuration templates exist."""
        existing = {t.name for t in self.template_repo.get_all()}
        for template in get_builtin_config_templates():
            if template.name not in existing:
                self.template_repo.create(template)
                logger.debug(f"Created builtin config template: {template.name}")

    def create_configuration(
        self,
        game_id: UUID,
        name: str,
        description: str = "",
        platform_type: PlatformType = PlatformType.DESKTOP,
        preset: Optional[str] = None,
        display: Optional[DisplayConfig] = None,
        audio: Optional[AudioConfig] = None,
        launch_args: Optional[LaunchArguments] = None,
        environment: Optional[EnvironmentConfig] = None,
        compatibility: Optional[CompatibilityConfig] = None,
        is_default: bool = False,
    ) -> PlatformConfiguration:
        """
        Create a new platform configuration for a game.

        Args:
            game_id: ID of the game to create configuration for
            name: Configuration name (e.g., "Desktop", "Laptop", "TV")
            description: Optional description
            platform_type: Target platform type
            preset: Template preset name (e.g., "performance", "quality")
            display: Display configuration
            audio: Audio configuration
            launch_args: Launch argument configuration
            environment: Environment variable configuration
            compatibility: Compatibility layer configuration
            is_default: Whether this is the default configuration

        Returns:
            The created PlatformConfiguration

        Raises:
            ValueError: If game not found or configuration name exists

        Example:
            >>> config = manager.create_configuration(
            ...     game.id, "Desktop High",
            ...     platform_type=PlatformType.DESKTOP,
            ...     preset="quality"
            ... )
        """
        # Verify game exists
        game = self.game_repo.get_by_id(game_id)
        if not game:
            raise ValueError(f"Game not found: {game_id}")

        # Check for existing configuration with same name
        existing = self.config_repo.get_by_game_id(game_id)
        if any(c.name == name for c in existing):
            raise ValueError(
                f"Configuration '{name}' already exists for game '{game.name}'"
            )

        # Start with preset if specified
        if preset:
            template = self.template_manager.get_template(preset)
            if template:
                config = PlatformConfiguration.from_template(template, game_id, name)
            else:
                raise ValueError(f"Preset '{preset}' not found")
        else:
            config = PlatformConfiguration(
                name=name,
                game_id=game_id,
                platform_type=platform_type,
            )

        # Apply custom settings
        config.description = description
        config.platform_type = platform_type

        if display:
            config.display = display
        if audio:
            config.audio = audio
        if launch_args:
            config.launch_args = launch_args
        if environment:
            config.environment = environment
        if compatibility:
            config.compatibility = compatibility

        # Set as default if requested or if first configuration
        if is_default or not existing:
            config.is_default = True
            # Clear other defaults
            for other in existing:
                if other.is_default:
                    other.is_default = False
                    self.config_repo.update(other)

        # Save configuration
        self.config_repo.create(config)

        # Update game's configuration list
        game.configuration_ids.append(config.id)
        self.game_repo.update(game)

        logger.info(f"Created configuration '{name}' for game '{game.name}'")
        return config

    def get_configuration(self, config_id: UUID) -> Optional[PlatformConfiguration]:
        """
        Get a configuration by ID.

        Args:
            config_id: Configuration UUID

        Returns:
            PlatformConfiguration if found, None otherwise
        """
        return self.config_repo.get_by_id(config_id)

    def get_configurations_for_game(
        self,
        game_id: UUID,
    ) -> list[PlatformConfiguration]:
        """
        Get all configurations for a game.

        Args:
            game_id: Game UUID

        Returns:
            List of configurations for the game
        """
        return self.config_repo.get_by_game_id(game_id)

    def get_default_configuration(
        self,
        game_id: UUID,
    ) -> Optional[PlatformConfiguration]:
        """
        Get the default configuration for a game.

        Args:
            game_id: Game UUID

        Returns:
            Default configuration, or None if not set
        """
        return self.config_repo.get_default_for_game(game_id)

    def get_configuration_for_platform(
        self,
        game_id: UUID,
        platform_type: Optional[PlatformType] = None,
    ) -> Optional[PlatformConfiguration]:
        """
        Get the best configuration for a game on a platform.

        If no platform type specified, auto-detects current platform.
        Returns the highest priority configuration for the platform,
        or the default configuration if no platform-specific one exists.

        Args:
            game_id: Game UUID
            platform_type: Target platform (auto-detected if None)

        Returns:
            Best matching configuration, or None if no configurations exist
        """
        if platform_type is None:
            platform_type = detect_current_platform()

        # Get configurations for this platform
        platform_configs = self.config_repo.get_by_platform_type(game_id, platform_type)

        if platform_configs:
            # Return highest priority enabled configuration
            enabled = [c for c in platform_configs if c.is_enabled]
            if enabled:
                return max(enabled, key=lambda c: c.priority)

        # Fall back to default configuration
        return self.config_repo.get_default_for_game(game_id)

    def update_configuration(
        self,
        config_id: UUID,
        **kwargs: Any,
    ) -> PlatformConfiguration:
        """
        Update a configuration.

        Args:
            config_id: Configuration UUID
            **kwargs: Fields to update

        Returns:
            Updated configuration

        Raises:
            ValueError: If configuration not found

        Example:
            >>> manager.update_configuration(
            ...     config.id,
            ...     display=DisplayConfig(width=2560, height=1440)
            ... )
        """
        config = self.config_repo.get_by_id(config_id)
        if not config:
            raise ValueError(f"Configuration not found: {config_id}")

        # Update allowed fields
        allowed_fields = {
            "name", "description", "platform_type", "graphics_quality",
            "display", "audio", "launch_args", "environment", "compatibility",
            "working_directory", "pre_launch_script", "post_launch_script",
            "is_enabled", "fallback_config_id", "priority", "tags",
        }

        for key, value in kwargs.items():
            if key in allowed_fields:
                setattr(config, key, value)

        config.mark_modified()
        self.config_repo.update(config)

        logger.info(f"Updated configuration: {config.name}")
        return config

    def delete_configuration(self, config_id: UUID) -> bool:
        """
        Delete a configuration.

        Args:
            config_id: Configuration UUID

        Returns:
            True if deleted, False if not found

        Example:
            >>> manager.delete_configuration(config.id)
        """
        config = self.config_repo.get_by_id(config_id)
        if not config:
            return False

        # Remove from game's configuration list
        game = self.game_repo.get_by_id(config.game_id)
        if game and config_id in game.configuration_ids:
            game.configuration_ids.remove(config_id)
            self.game_repo.update(game)

        self.config_repo.delete(config_id)
        logger.info(f"Deleted configuration: {config.name}")
        return True

    def set_default_configuration(
        self,
        game_id: UUID,
        config_id: UUID,
    ) -> None:
        """
        Set a configuration as the default for a game.

        Args:
            game_id: Game UUID
            config_id: Configuration UUID to set as default

        Raises:
            ValueError: If configuration not found or doesn't belong to game
        """
        config = self.config_repo.get_by_id(config_id)
        if not config:
            raise ValueError(f"Configuration not found: {config_id}")
        if config.game_id != game_id:
            raise ValueError("Configuration doesn't belong to the specified game")

        self.config_repo.set_default(config_id, game_id)
        logger.info(f"Set default configuration: {config.name}")

    def duplicate_configuration(
        self,
        config_id: UUID,
        new_name: str,
    ) -> PlatformConfiguration:
        """
        Create a copy of a configuration.

        Args:
            config_id: Source configuration UUID
            new_name: Name for the new configuration

        Returns:
            The duplicated configuration

        Raises:
            ValueError: If configuration not found or name exists
        """
        config = self.config_repo.get_by_id(config_id)
        if not config:
            raise ValueError(f"Configuration not found: {config_id}")

        # Check for name conflict
        existing = self.config_repo.get_by_game_id(config.game_id)
        if any(c.name == new_name for c in existing):
            raise ValueError(f"Configuration '{new_name}' already exists")

        # Create copy
        new_config = config.model_copy(
            update={
                "id": None,  # Will generate new ID
                "name": new_name,
                "is_default": False,
                "statistics": None,  # Reset statistics
            }
        )

        self.config_repo.create(new_config)

        # Update game's configuration list
        game = self.game_repo.get_by_id(config.game_id)
        if game:
            game.configuration_ids.append(new_config.id)
            self.game_repo.update(game)

        logger.info(f"Duplicated configuration: {config.name} -> {new_name}")
        return new_config

    def apply_preset_to_configuration(
        self,
        config_id: UUID,
        preset_name: str,
        merge: bool = True,
    ) -> PlatformConfiguration:
        """
        Apply a preset template to a configuration.

        Args:
            config_id: Configuration UUID
            preset_name: Name of preset to apply
            merge: If True, merge with existing settings; if False, replace

        Returns:
            Updated configuration

        Raises:
            ValueError: If configuration or preset not found
        """
        config = self.config_repo.get_by_id(config_id)
        if not config:
            raise ValueError(f"Configuration not found: {config_id}")

        template = self.template_manager.get_template(preset_name)
        if not template:
            raise ValueError(f"Preset not found: {preset_name}")

        if merge:
            # Merge template settings into configuration
            if template.display:
                config.display = template.display.model_copy()
            if template.audio:
                config.audio = template.audio.model_copy()
            if template.launch_args:
                config.launch_args = template.launch_args.model_copy()
            if template.environment:
                config.environment = template.environment.model_copy()
            if template.compatibility:
                config.compatibility = template.compatibility.model_copy()
            config.graphics_quality = template.graphics_quality
        else:
            # Replace all settings
            config.display = template.display.model_copy()
            config.audio = template.audio.model_copy()
            config.launch_args = template.launch_args.model_copy()
            config.environment = template.environment.model_copy()
            config.compatibility = template.compatibility.model_copy()
            config.graphics_quality = template.graphics_quality
            config.platform_type = template.platform_type

        config.mark_modified()
        self.config_repo.update(config)

        logger.info(f"Applied preset '{preset_name}' to configuration '{config.name}'")
        return config

    def validate_configuration(
        self,
        config_id: UUID,
    ) -> tuple[bool, list[str]]:
        """
        Validate a configuration.

        Args:
            config_id: Configuration UUID

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        config = self.config_repo.get_by_id(config_id)
        if not config:
            return False, ["Configuration not found"]

        errors = config.validate_configuration()
        return len(errors) == 0, errors

    def batch_create_configurations(
        self,
        game_ids: list[UUID],
        name: str,
        preset: str,
        overwrite: bool = False,
    ) -> dict[UUID, Optional[PlatformConfiguration]]:
        """
        Create configurations for multiple games.

        Args:
            game_ids: List of game UUIDs
            name: Configuration name
            preset: Preset to use
            overwrite: Replace existing configurations with same name

        Returns:
            Dictionary mapping game_id to created configuration (or None if failed)

        Example:
            >>> configs = manager.batch_create_configurations(
            ...     [game1.id, game2.id],
            ...     "Performance",
            ...     preset="performance"
            ... )
        """
        results: dict[UUID, Optional[PlatformConfiguration]] = {}

        for game_id in game_ids:
            try:
                # Check for existing
                existing = self.config_repo.get_by_game_id(game_id)
                existing_with_name = [c for c in existing if c.name == name]

                if existing_with_name and overwrite:
                    for config in existing_with_name:
                        self.delete_configuration(config.id)
                elif existing_with_name:
                    results[game_id] = None
                    continue

                config = self.create_configuration(
                    game_id, name, preset=preset
                )
                results[game_id] = config

            except Exception as e:
                logger.error(f"Failed to create config for game {game_id}: {e}")
                results[game_id] = None

        logger.info(
            f"Batch created {sum(1 for c in results.values() if c)} configurations"
        )
        return results

    def record_launch(
        self,
        config_id: UUID,
        success: bool,
        session_minutes: Optional[int] = None,
    ) -> None:
        """
        Record a game launch using a configuration.

        Updates usage statistics for the configuration.

        Args:
            config_id: Configuration UUID
            success: Whether the launch was successful
            session_minutes: Duration of the session
        """
        config = self.config_repo.get_by_id(config_id)
        if not config:
            return

        config.statistics.record_launch(success, session_minutes)
        self.config_repo.update(config)

    def get_configuration_statistics(
        self,
        config_id: UUID,
    ) -> Optional[dict[str, Any]]:
        """
        Get usage statistics for a configuration.

        Args:
            config_id: Configuration UUID

        Returns:
            Statistics dictionary, or None if not found
        """
        config = self.config_repo.get_by_id(config_id)
        if not config:
            return None

        return {
            "use_count": config.statistics.use_count,
            "success_count": config.statistics.success_count,
            "failure_count": config.statistics.failure_count,
            "success_rate": config.statistics.success_rate,
            "average_session_minutes": config.statistics.average_session_minutes,
            "total_playtime_minutes": config.statistics.total_playtime_minutes,
            "last_used": config.statistics.last_used.isoformat() if config.statistics.last_used else None,
        }

    def to_dict(self, config_id: UUID) -> Optional[dict[str, Any]]:
        """
        Get configuration data as dictionary (for CLI JSON output).

        Args:
            config_id: Configuration UUID

        Returns:
            Dictionary representation, or None if not found
        """
        config = self.config_repo.get_by_id(config_id)
        if not config:
            return None
        return config.to_dict()
