"""
Configuration templates for Playnite-Py.

This module provides configuration template management including builtin
presets for common use cases like Performance, Quality, and Battery Saver.

Example:
    >>> from playnite_py.configurations.templates import get_builtin_config_templates
    >>> templates = get_builtin_config_templates()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
from uuid import UUID

if TYPE_CHECKING:
    from playnite_py.core.database.repositories import ConfigurationTemplateRepository

from playnite_py.core.models.configuration import (
    ConfigurationTemplate,
    DisplayConfig,
    AudioConfig,
    LaunchArguments,
    EnvironmentConfig,
    CompatibilityConfig,
    PlatformType,
    GraphicsQuality,
)

logger = logging.getLogger(__name__)


def get_builtin_config_templates() -> list[ConfigurationTemplate]:
    """
    Get all builtin configuration templates.

    Returns a list of predefined templates for common use cases.

    Returns:
        List of builtin ConfigurationTemplate objects

    Example:
        >>> templates = get_builtin_config_templates()
        >>> for t in templates:
        ...     print(f"{t.name}: {t.description}")
    """
    return [
        # Performance preset - prioritize FPS over quality
        ConfigurationTemplate(
            name="Performance",
            description="Optimized for maximum FPS with reduced graphics quality",
            platform_type=PlatformType.DESKTOP,
            graphics_quality=GraphicsQuality.LOW,
            display=DisplayConfig(
                fullscreen=True,
                vsync=False,  # Minimize input lag
                borderless=False,
            ),
            audio=AudioConfig(
                volume=100,
            ),
            launch_args=LaunchArguments(
                add_arguments=["-high"],  # Common high-priority flag
            ),
            environment=EnvironmentConfig(
                set_variables={
                    "DXVK_HUD": "fps,gpuload",  # Show performance overlay on Linux
                },
            ),
            is_builtin=True,
        ),
        # Quality preset - maximize visual quality
        ConfigurationTemplate(
            name="Quality",
            description="Maximum visual quality with high graphics settings",
            platform_type=PlatformType.DESKTOP,
            graphics_quality=GraphicsQuality.ULTRA,
            display=DisplayConfig(
                fullscreen=True,
                vsync=True,
                borderless=False,
                hdr_enabled=True,
            ),
            audio=AudioConfig(
                volume=100,
                enable_spatial=True,
            ),
            is_builtin=True,
        ),
        # Balanced preset - compromise between performance and quality
        ConfigurationTemplate(
            name="Balanced",
            description="Balance between visual quality and performance",
            platform_type=PlatformType.DESKTOP,
            graphics_quality=GraphicsQuality.MEDIUM,
            display=DisplayConfig(
                fullscreen=True,
                vsync=True,
                borderless=False,
            ),
            audio=AudioConfig(
                volume=100,
            ),
            is_builtin=True,
        ),
        # Battery Saver preset - minimize power consumption
        ConfigurationTemplate(
            name="Battery Saver",
            description="Optimized for battery life on laptops",
            platform_type=PlatformType.LAPTOP,
            graphics_quality=GraphicsQuality.LOW,
            display=DisplayConfig(
                fullscreen=False,  # Windowed uses less power
                vsync=True,  # Cap framerate
                borderless=True,
            ),
            audio=AudioConfig(
                volume=80,
            ),
            environment=EnvironmentConfig(
                set_variables={
                    # Limit framerate where possible
                    "DXVK_FRAME_RATE": "30",
                },
            ),
            is_builtin=True,
        ),
        # Streaming preset - optimized for game streaming/recording
        ConfigurationTemplate(
            name="Streaming",
            description="Optimized for game streaming and recording",
            platform_type=PlatformType.DESKTOP,
            graphics_quality=GraphicsQuality.HIGH,
            display=DisplayConfig(
                width=1920,
                height=1080,
                refresh_rate=60,
                fullscreen=True,
                vsync=True,  # Stable framerate for streaming
                borderless=False,
            ),
            audio=AudioConfig(
                volume=100,
            ),
            is_builtin=True,
        ),
        # TV/Couch preset - optimized for big screen gaming
        ConfigurationTemplate(
            name="TV/Couch",
            description="Optimized for TV and couch gaming",
            platform_type=PlatformType.HTPC,
            graphics_quality=GraphicsQuality.HIGH,
            display=DisplayConfig(
                fullscreen=True,
                vsync=True,
                borderless=False,
                hdr_enabled=True,
            ),
            audio=AudioConfig(
                volume=100,
                speaker_config="5.1",  # Surround sound for TV
            ),
            is_builtin=True,
        ),
        # Handheld preset - Steam Deck and similar devices
        ConfigurationTemplate(
            name="Handheld",
            description="Optimized for handheld devices like Steam Deck",
            platform_type=PlatformType.HANDHELD,
            graphics_quality=GraphicsQuality.LOW,
            display=DisplayConfig(
                width=1280,
                height=800,  # Steam Deck resolution
                refresh_rate=60,
                fullscreen=True,
                vsync=True,
            ),
            audio=AudioConfig(
                volume=80,
            ),
            environment=EnvironmentConfig(
                set_variables={
                    "DXVK_FRAME_RATE": "60",
                    "MANGOHUD": "1",
                },
            ),
            is_builtin=True,
        ),
        # Wine/Proton preset - Linux gaming with compatibility layer
        ConfigurationTemplate(
            name="Linux Gaming",
            description="Optimized settings for Wine/Proton on Linux",
            platform_type=PlatformType.DESKTOP,
            graphics_quality=GraphicsQuality.MEDIUM,
            display=DisplayConfig(
                fullscreen=True,
                vsync=True,
            ),
            compatibility=CompatibilityConfig(
                use_compatibility_layer=True,
                layer_type="proton",
                esync_enabled=True,
                fsync_enabled=True,
                dxvk_enabled=True,
                windows_version="win10",
            ),
            environment=EnvironmentConfig(
                set_variables={
                    "PROTON_USE_WINED3D": "0",
                    "DXVK_ASYNC": "1",
                },
            ),
            is_builtin=True,
        ),
        # Debug preset - for troubleshooting
        ConfigurationTemplate(
            name="Debug",
            description="Debug configuration with verbose logging",
            platform_type=PlatformType.DESKTOP,
            graphics_quality=GraphicsQuality.LOW,
            display=DisplayConfig(
                fullscreen=False,
                borderless=True,
            ),
            environment=EnvironmentConfig(
                set_variables={
                    "DXVK_HUD": "full",
                    "DXVK_LOG_LEVEL": "info",
                    "WINEDEBUG": "+all",
                },
            ),
            is_builtin=True,
        ),
    ]


class ConfigTemplateManager:
    """
    Manager for configuration templates.

    Handles template retrieval, creation, and management operations.

    Attributes:
        repo: Template repository for database operations

    Example:
        >>> manager = ConfigTemplateManager(repo)
        >>> template = manager.get_template("performance")
    """

    def __init__(self, repo: "ConfigurationTemplateRepository") -> None:
        """
        Initialize the template manager.

        Args:
            repo: Configuration template repository
        """
        self.repo = repo

    def get_template(self, name: str) -> Optional[ConfigurationTemplate]:
        """
        Get a template by name.

        Args:
            name: Template name (case-insensitive)

        Returns:
            ConfigurationTemplate if found, None otherwise

        Example:
            >>> template = manager.get_template("performance")
        """
        # Try exact match first
        template = self.repo.get_by_name(name)
        if template:
            return template

        # Try case-insensitive match
        for t in self.repo.get_all():
            if t.name.lower() == name.lower():
                return t

        return None

    def get_template_by_id(self, template_id: UUID) -> Optional[ConfigurationTemplate]:
        """
        Get a template by ID.

        Args:
            template_id: Template UUID

        Returns:
            ConfigurationTemplate if found, None otherwise
        """
        return self.repo.get_by_id(template_id)

    def list_templates(self) -> list[ConfigurationTemplate]:
        """
        List all available templates.

        Returns:
            List of all templates (builtin and custom)
        """
        return self.repo.get_all()

    def list_builtin_templates(self) -> list[ConfigurationTemplate]:
        """
        List only builtin templates.

        Returns:
            List of builtin templates
        """
        return self.repo.get_builtin()

    def list_custom_templates(self) -> list[ConfigurationTemplate]:
        """
        List only custom (user-created) templates.

        Returns:
            List of custom templates
        """
        return [t for t in self.repo.get_all() if not t.is_builtin]

    def create_template(
        self,
        name: str,
        description: str = "",
        platform_type: PlatformType = PlatformType.DESKTOP,
        graphics_quality: GraphicsQuality = GraphicsQuality.MEDIUM,
        display: Optional[DisplayConfig] = None,
        audio: Optional[AudioConfig] = None,
        launch_args: Optional[LaunchArguments] = None,
        environment: Optional[EnvironmentConfig] = None,
        compatibility: Optional[CompatibilityConfig] = None,
    ) -> ConfigurationTemplate:
        """
        Create a new custom template.

        Args:
            name: Unique template name
            description: Template description
            platform_type: Target platform
            graphics_quality: Graphics quality preset
            display: Display configuration
            audio: Audio configuration
            launch_args: Launch argument configuration
            environment: Environment variable configuration
            compatibility: Compatibility layer configuration

        Returns:
            The created template

        Raises:
            ValueError: If template name already exists

        Example:
            >>> template = manager.create_template(
            ...     "My Preset",
            ...     description="Custom settings",
            ...     graphics_quality=GraphicsQuality.HIGH
            ... )
        """
        if self.repo.get_by_name(name):
            raise ValueError(f"Template '{name}' already exists")

        template = ConfigurationTemplate(
            name=name,
            description=description,
            platform_type=platform_type,
            graphics_quality=graphics_quality,
            display=display or DisplayConfig(),
            audio=audio or AudioConfig(),
            launch_args=launch_args or LaunchArguments(),
            environment=environment or EnvironmentConfig(),
            compatibility=compatibility or CompatibilityConfig(),
            is_builtin=False,
        )

        self.repo.create(template)
        logger.info(f"Created template: {name}")
        return template

    def delete_template(self, name: str) -> bool:
        """
        Delete a custom template.

        Builtin templates cannot be deleted.

        Args:
            name: Template name to delete

        Returns:
            True if deleted, False if not found

        Raises:
            ValueError: If trying to delete a builtin template
        """
        template = self.repo.get_by_name(name)
        if not template:
            return False

        if template.is_builtin:
            raise ValueError(f"Cannot delete builtin template '{name}'")

        self.repo.delete(template.id)
        logger.info(f"Deleted template: {name}")
        return True

    def list_templates_by_platform(
        self,
        platform_type: PlatformType,
    ) -> list[ConfigurationTemplate]:
        """
        List templates for a specific platform type.

        Args:
            platform_type: Platform to filter by

        Returns:
            List of templates for the platform
        """
        return [t for t in self.repo.get_all() if t.platform_type == platform_type]
