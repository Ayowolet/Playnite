"""
Platform configuration models for Playnite-Py.

This module defines the data structures for managing platform-specific
game configurations, including display settings, launch arguments,
environment variables, and compatibility layers.

Example:
    >>> from playnite_py.core.models.configuration import (
    ...     PlatformConfiguration, DisplayConfig, GraphicsQuality
    ... )
    >>> display = DisplayConfig(width=1920, height=1080, fullscreen=True)
    >>> config = PlatformConfiguration(
    ...     name="Desktop",
    ...     game_id=game.id,
    ...     display=display
    ... )
"""

from __future__ import annotations

import shlex
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class PlatformType(str, Enum):
    """
    Type of platform/hardware configuration.

    Attributes:
        DESKTOP: Full desktop PC (high-end gaming)
        LAPTOP: Portable laptop (power/thermal constraints)
        HTPC: Home theater PC (TV/couch gaming)
        HANDHELD: Portable gaming device (Steam Deck, etc.)
        VM: Virtual machine
        REMOTE: Remote streaming client
        CUSTOM: User-defined platform type
    """
    DESKTOP = "desktop"
    LAPTOP = "laptop"
    HTPC = "htpc"
    HANDHELD = "handheld"
    VM = "vm"
    REMOTE = "remote"
    CUSTOM = "custom"


class GraphicsQuality(str, Enum):
    """
    Graphics quality preset levels.

    Attributes:
        ULTRA: Maximum quality, highest resource usage
        HIGH: High quality, some optimizations
        MEDIUM: Balanced quality and performance
        LOW: Performance focused, reduced quality
        VERY_LOW: Minimum quality, maximum performance
        CUSTOM: User-defined settings
    """
    ULTRA = "ultra"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"
    CUSTOM = "custom"


class DisplayConfig(BaseModel):
    """
    Display configuration settings.

    Defines resolution, refresh rate, monitor selection, and
    display mode settings for game launches.

    Attributes:
        width: Horizontal resolution in pixels
        height: Vertical resolution in pixels
        refresh_rate: Target refresh rate in Hz
        fullscreen: Whether to launch in fullscreen mode
        borderless: Use borderless windowed mode
        vsync: Enable vertical sync
        target_monitor: Monitor index or name to use
        hdr_enabled: Enable HDR if supported
        scaling_mode: Display scaling mode

    Example:
        >>> display = DisplayConfig(
        ...     width=2560,
        ...     height=1440,
        ...     refresh_rate=144,
        ...     fullscreen=True,
        ...     vsync=False
        ... )
    """
    width: Optional[int] = Field(
        default=None,
        ge=640,
        le=15360,
        description="Horizontal resolution"
    )
    height: Optional[int] = Field(
        default=None,
        ge=480,
        le=8640,
        description="Vertical resolution"
    )
    refresh_rate: Optional[int] = Field(
        default=None,
        ge=30,
        le=500,
        description="Refresh rate in Hz"
    )
    fullscreen: bool = Field(
        default=False,
        description="Fullscreen mode"
    )
    borderless: bool = Field(
        default=False,
        description="Borderless windowed"
    )
    vsync: bool = Field(
        default=True,
        description="Vertical sync"
    )
    target_monitor: Optional[str] = Field(
        default=None,
        description="Target monitor identifier"
    )
    hdr_enabled: bool = Field(
        default=False,
        description="Enable HDR"
    )
    scaling_mode: str = Field(
        default="native",
        description="Scaling mode (native, stretched, aspect)"
    )


class AudioConfig(BaseModel):
    """
    Audio configuration settings.

    Defines audio output device, volume, and speaker configuration
    for game launches.

    Attributes:
        output_device: Audio output device name or ID
        volume: Master volume level (0-100)
        speaker_config: Speaker configuration (stereo, 5.1, 7.1, etc.)
        sample_rate: Audio sample rate in Hz
        enable_spatial: Enable spatial audio
        mute_on_focus_loss: Mute when game loses focus

    Example:
        >>> audio = AudioConfig(
        ...     output_device="Headphones",
        ...     volume=80,
        ...     speaker_config="stereo"
        ... )
    """
    output_device: Optional[str] = Field(
        default=None,
        description="Audio output device"
    )
    volume: int = Field(
        default=100,
        ge=0,
        le=100,
        description="Master volume (0-100)"
    )
    speaker_config: str = Field(
        default="stereo",
        description="Speaker configuration"
    )
    sample_rate: int = Field(
        default=48000,
        ge=8000,
        le=192000,
        description="Sample rate in Hz"
    )
    enable_spatial: bool = Field(
        default=False,
        description="Enable spatial audio"
    )
    mute_on_focus_loss: bool = Field(
        default=False,
        description="Mute on focus loss"
    )


class LaunchArguments(BaseModel):
    """
    Launch argument configuration.

    Manages command-line arguments for game execution, including
    arguments to add, remove, or replace from the base configuration.

    Attributes:
        base_arguments: Default arguments from game action
        add_arguments: Arguments to append
        remove_arguments: Arguments to remove from base
        replace_arguments: Completely replace base arguments
        argument_separator: Separator between arguments (usually space)

    Example:
        >>> args = LaunchArguments(
        ...     base_arguments="-window-mode exclusive",
        ...     add_arguments=["-dx12", "-high"],
        ...     remove_arguments=["-window-mode exclusive"]
        ... )
        >>> args.get_final_arguments()
        '-dx12 -high'
    """
    base_arguments: str = Field(
        default="",
        description="Base arguments from game action"
    )
    add_arguments: list[str] = Field(
        default_factory=list,
        description="Arguments to add"
    )
    remove_arguments: list[str] = Field(
        default_factory=list,
        description="Arguments to remove"
    )
    replace_arguments: Optional[str] = Field(
        default=None,
        description="Complete replacement arguments"
    )
    argument_separator: str = Field(
        default=" ",
        description="Argument separator"
    )

    def get_final_arguments(self) -> str:
        """
        Calculate the final argument string.

        If replace_arguments is set, returns that directly.
        Otherwise, starts with base_arguments, removes any
        arguments in remove_arguments, and appends add_arguments.

        Uses shlex.split() for proper handling of quoted arguments
        to prevent argument injection vulnerabilities.

        Returns:
            Final argument string for execution

        Example:
            >>> args = LaunchArguments(
            ...     base_arguments="-windowed -vsync",
            ...     add_arguments=["-dx11"],
            ...     remove_arguments=["-windowed"]
            ... )
            >>> args.get_final_arguments()
            '-vsync -dx11'
        """
        if self.replace_arguments is not None:
            return self.replace_arguments

        # Start with base arguments - use shlex.split for proper quote handling
        # This fixes Gap 5: Naive argument splitting
        if self.base_arguments:
            try:
                result_args = shlex.split(self.base_arguments)
            except ValueError:
                # Fallback to simple split if shlex fails (malformed quotes)
                result_args = self.base_arguments.split()
        else:
            result_args = []

        # Remove specified arguments
        for remove_arg in self.remove_arguments:
            # Handle both single args and key=value pairs
            result_args = [
                arg for arg in result_args
                if arg != remove_arg and not arg.startswith(f"{remove_arg}=")
            ]

        # Add new arguments
        result_args.extend(self.add_arguments)

        # Use shlex.join for proper quoting of arguments with spaces
        return shlex.join(result_args)


class EnvironmentConfig(BaseModel):
    """
    Environment variable configuration.

    Manages environment variables to set or unset when launching
    a game, with support for variable expansion.

    Attributes:
        set_variables: Variables to set (name -> value)
        unset_variables: Variables to unset
        inherit_system: Whether to inherit system environment
        expand_variables: Whether to expand variable references

    Example:
        >>> env = EnvironmentConfig(
        ...     set_variables={
        ...         "DXVK_HUD": "fps",
        ...         "MANGOHUD": "1"
        ...     }
        ... )
    """
    set_variables: dict[str, str] = Field(
        default_factory=dict,
        description="Variables to set"
    )
    unset_variables: list[str] = Field(
        default_factory=list,
        description="Variables to unset"
    )
    inherit_system: bool = Field(
        default=True,
        description="Inherit system environment"
    )
    expand_variables: bool = Field(
        default=True,
        description="Expand variable references"
    )

    def get_environment(self, base_env: Optional[dict[str, str]] = None) -> dict[str, str]:
        """
        Calculate the final environment dictionary.

        Starts with base_env (or system environment if inherit_system),
        unsets specified variables, then sets specified variables.

        Args:
            base_env: Base environment to modify (uses system env if None)

        Returns:
            Final environment dictionary

        Example:
            >>> env = EnvironmentConfig(
            ...     set_variables={"FOO": "bar"},
            ...     unset_variables=["BAZ"]
            ... )
            >>> result = env.get_environment({"BAZ": "old", "OTHER": "keep"})
            >>> "BAZ" in result
            False
            >>> result["FOO"]
            'bar'
        """
        import os

        if self.inherit_system and base_env is None:
            result = dict(os.environ)
        elif base_env is not None:
            result = base_env.copy()
        else:
            result = {}

        # Unset variables
        for var in self.unset_variables:
            result.pop(var, None)

        # Set variables
        for name, value in self.set_variables.items():
            if self.expand_variables:
                # Expand references to other variables
                for existing_name, existing_value in result.items():
                    value = value.replace(f"${existing_name}", existing_value)
                    value = value.replace(f"${{{existing_name}}}", existing_value)
            result[name] = value

        return result


class CompatibilityConfig(BaseModel):
    """
    Compatibility layer configuration.

    Manages Wine/Proton on Linux, compatibility mode on Windows,
    and other platform-specific compatibility settings.

    Attributes:
        use_compatibility_layer: Enable compatibility layer
        layer_type: Type of layer (wine, proton, crossover, etc.)
        layer_path: Path to compatibility layer installation
        layer_version: Version of compatibility layer
        prefix_path: Wine/Proton prefix path
        esync_enabled: Enable esync for Wine/Proton
        fsync_enabled: Enable fsync for Wine/Proton
        dxvk_enabled: Enable DXVK for Vulkan translation
        vkd3d_enabled: Enable vkd3d for DX12 support
        windows_version: Windows version to emulate
        dll_overrides: DLL override configuration
        custom_commands: Custom commands to run before game

    Example:
        >>> compat = CompatibilityConfig(
        ...     use_compatibility_layer=True,
        ...     layer_type="proton",
        ...     layer_version="8.0",
        ...     dxvk_enabled=True,
        ...     fsync_enabled=True
        ... )
    """
    use_compatibility_layer: bool = Field(
        default=False,
        description="Enable compatibility layer"
    )
    layer_type: str = Field(
        default="wine",
        description="Compatibility layer type"
    )
    layer_path: Optional[Path] = Field(
        default=None,
        description="Path to layer installation"
    )
    layer_version: Optional[str] = Field(
        default=None,
        description="Layer version"
    )
    prefix_path: Optional[Path] = Field(
        default=None,
        description="Wine/Proton prefix path"
    )
    esync_enabled: bool = Field(
        default=True,
        description="Enable esync"
    )
    fsync_enabled: bool = Field(
        default=True,
        description="Enable fsync"
    )
    dxvk_enabled: bool = Field(
        default=True,
        description="Enable DXVK"
    )
    vkd3d_enabled: bool = Field(
        default=False,
        description="Enable vkd3d for DX12"
    )
    windows_version: str = Field(
        default="win10",
        description="Windows version to emulate"
    )
    dll_overrides: dict[str, str] = Field(
        default_factory=dict,
        description="DLL override settings"
    )
    custom_commands: list[str] = Field(
        default_factory=list,
        description="Custom pre-launch commands"
    )

    model_config = {
        "json_encoders": {
            Path: str,
        }
    }

    @field_validator("layer_type")
    @classmethod
    def validate_layer_type(cls, v: str) -> str:
        """Validate compatibility layer type."""
        allowed = {"wine", "proton", "crossover", "whisky", "gptk", "none"}
        if v.lower() not in allowed:
            raise ValueError(f"Layer type must be one of: {allowed}")
        return v.lower()


class ConfigurationUsageStats(BaseModel):
    """
    Usage statistics for a configuration.

    Tracks how often a configuration is used and its success rate
    to help identify problematic configurations.

    Attributes:
        use_count: Number of times configuration was used
        success_count: Number of successful launches
        failure_count: Number of failed launches
        last_used: Last usage timestamp
        average_session_minutes: Average session duration
        total_playtime_minutes: Total playtime with this config

    Example:
        >>> stats = ConfigurationUsageStats()
        >>> stats.record_launch(success=True, session_minutes=60)
        >>> stats.success_rate
        1.0
    """
    use_count: int = Field(
        default=0,
        ge=0,
        description="Total use count"
    )
    success_count: int = Field(
        default=0,
        ge=0,
        description="Successful launches"
    )
    failure_count: int = Field(
        default=0,
        ge=0,
        description="Failed launches"
    )
    last_used: Optional[datetime] = Field(
        default=None,
        description="Last usage time"
    )
    average_session_minutes: float = Field(
        default=0.0,
        ge=0,
        description="Average session duration"
    )
    total_playtime_minutes: int = Field(
        default=0,
        ge=0,
        description="Total playtime"
    )

    @property
    def success_rate(self) -> float:
        """
        Calculate the success rate of this configuration.

        Returns:
            Success rate as a float between 0 and 1
        """
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    def record_launch(
        self,
        success: bool,
        session_minutes: Optional[int] = None
    ) -> None:
        """
        Record a launch attempt.

        Args:
            success: Whether the launch was successful
            session_minutes: Duration of the session (if known)

        Example:
            >>> stats = ConfigurationUsageStats()
            >>> stats.record_launch(success=True, session_minutes=45)
            >>> stats.use_count
            1
        """
        self.use_count += 1
        self.last_used = datetime.now()

        if success:
            self.success_count += 1
            if session_minutes is not None:
                # Update running average
                total_sessions = self.success_count
                if total_sessions == 1:
                    self.average_session_minutes = float(session_minutes)
                else:
                    # Incremental average calculation
                    self.average_session_minutes = (
                        self.average_session_minutes * (total_sessions - 1)
                        + session_minutes
                    ) / total_sessions
                self.total_playtime_minutes += session_minutes
        else:
            self.failure_count += 1


class ConfigurationTemplate(BaseModel):
    """
    Template for creating platform configurations.

    Provides predefined settings for common use cases like
    Performance, Quality, or Battery Saver modes.

    Attributes:
        id: Unique template identifier
        name: Template display name
        description: Template description
        platform_type: Target platform type
        graphics_quality: Graphics quality preset
        display: Display configuration
        audio: Audio configuration
        launch_args: Launch argument configuration
        environment: Environment variable configuration
        compatibility: Compatibility layer configuration
        is_builtin: Whether this is a system template
        created_at: Template creation timestamp

    Example:
        >>> template = ConfigurationTemplate(
        ...     name="Performance Mode",
        ...     description="Optimized for maximum FPS",
        ...     graphics_quality=GraphicsQuality.LOW,
        ...     display=DisplayConfig(vsync=False)
        ... )
    """
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique template identifier"
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Template name"
    )
    description: str = Field(
        default="",
        max_length=500,
        description="Template description"
    )
    platform_type: PlatformType = Field(
        default=PlatformType.DESKTOP,
        description="Target platform"
    )
    graphics_quality: GraphicsQuality = Field(
        default=GraphicsQuality.MEDIUM,
        description="Graphics preset"
    )
    display: DisplayConfig = Field(
        default_factory=DisplayConfig,
        description="Display settings"
    )
    audio: AudioConfig = Field(
        default_factory=AudioConfig,
        description="Audio settings"
    )
    launch_args: LaunchArguments = Field(
        default_factory=LaunchArguments,
        description="Launch arguments"
    )
    environment: EnvironmentConfig = Field(
        default_factory=EnvironmentConfig,
        description="Environment variables"
    )
    compatibility: CompatibilityConfig = Field(
        default_factory=CompatibilityConfig,
        description="Compatibility settings"
    )
    is_builtin: bool = Field(
        default=False,
        description="System-provided template"
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Creation timestamp"
    )


class PlatformConfiguration(BaseModel):
    """
    Platform-specific configuration for a game.

    Represents a complete configuration for launching a game on
    a specific platform or in a specific mode (Desktop, Laptop, TV, etc.).

    Attributes:
        id: Unique configuration identifier
        name: Configuration display name
        description: Configuration description
        game_id: ID of the game this configuration belongs to
        platform_type: Target platform type
        graphics_quality: Graphics quality preset
        display: Display configuration
        audio: Audio configuration
        launch_args: Launch argument overrides
        environment: Environment variable configuration
        compatibility: Compatibility layer configuration
        working_directory: Override working directory
        pre_launch_script: Script to run before launch
        post_launch_script: Script to run after game exits
        is_default: Default configuration for this game
        is_enabled: Whether configuration is active
        fallback_config_id: Configuration to use if this one fails
        priority: Priority for auto-detection (higher = preferred)
        statistics: Usage statistics
        hardware_requirements: Minimum hardware requirements
        tags: User-defined tags for organization
        created_at: Creation timestamp
        modified_at: Last modification timestamp

    Example:
        >>> config = PlatformConfiguration(
        ...     name="Desktop High Quality",
        ...     game_id=game.id,
        ...     platform_type=PlatformType.DESKTOP,
        ...     graphics_quality=GraphicsQuality.HIGH,
        ...     display=DisplayConfig(width=2560, height=1440)
        ... )
    """
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique configuration identifier"
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Configuration name"
    )
    description: str = Field(
        default="",
        max_length=500,
        description="Configuration description"
    )
    game_id: UUID = Field(
        ...,
        description="Associated game ID"
    )
    platform_type: PlatformType = Field(
        default=PlatformType.DESKTOP,
        description="Target platform"
    )
    graphics_quality: GraphicsQuality = Field(
        default=GraphicsQuality.MEDIUM,
        description="Graphics preset"
    )
    display: DisplayConfig = Field(
        default_factory=DisplayConfig,
        description="Display settings"
    )
    audio: AudioConfig = Field(
        default_factory=AudioConfig,
        description="Audio settings"
    )
    launch_args: LaunchArguments = Field(
        default_factory=LaunchArguments,
        description="Launch arguments"
    )
    environment: EnvironmentConfig = Field(
        default_factory=EnvironmentConfig,
        description="Environment variables"
    )
    compatibility: CompatibilityConfig = Field(
        default_factory=CompatibilityConfig,
        description="Compatibility settings"
    )
    working_directory: Optional[Path] = Field(
        default=None,
        description="Override working directory"
    )
    pre_launch_script: Optional[str] = Field(
        default=None,
        description="Pre-launch script content"
    )
    post_launch_script: Optional[str] = Field(
        default=None,
        description="Post-launch script content"
    )
    is_default: bool = Field(
        default=False,
        description="Default for this game"
    )
    is_enabled: bool = Field(
        default=True,
        description="Configuration is active"
    )
    fallback_config_id: Optional[UUID] = Field(
        default=None,
        description="Fallback configuration ID"
    )
    priority: int = Field(
        default=0,
        description="Priority for auto-detection"
    )
    statistics: ConfigurationUsageStats = Field(
        default_factory=ConfigurationUsageStats,
        description="Usage statistics"
    )
    hardware_requirements: dict[str, Any] = Field(
        default_factory=dict,
        description="Minimum hardware requirements"
    )
    tags: list[str] = Field(
        default_factory=list,
        description="User-defined tags"
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Creation timestamp"
    )
    modified_at: datetime = Field(
        default_factory=datetime.now,
        description="Last modification"
    )

    model_config = {
        "json_encoders": {
            Path: str,
            datetime: lambda v: v.isoformat(),
            UUID: str,
        }
    }

    def mark_modified(self) -> None:
        """Update the modified timestamp."""
        self.modified_at = datetime.now()

    @classmethod
    def from_template(
        cls,
        template: ConfigurationTemplate,
        game_id: UUID,
        name: Optional[str] = None
    ) -> "PlatformConfiguration":
        """
        Create a configuration from a template.

        Args:
            template: Template to base configuration on
            game_id: ID of the game for this configuration
            name: Override name (uses template name if not provided)

        Returns:
            New PlatformConfiguration instance

        Example:
            >>> template = ConfigurationTemplate(name="Performance")
            >>> config = PlatformConfiguration.from_template(
            ...     template, game.id, name="My Performance Config"
            ... )
        """
        return cls(
            name=name or template.name,
            description=template.description,
            game_id=game_id,
            platform_type=template.platform_type,
            graphics_quality=template.graphics_quality,
            display=template.display.model_copy(),
            audio=template.audio.model_copy(),
            launch_args=template.launch_args.model_copy(),
            environment=template.environment.model_copy(),
            compatibility=template.compatibility.model_copy(),
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert configuration to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlatformConfiguration":
        """
        Create a configuration from a dictionary.

        Args:
            data: Dictionary containing configuration data

        Returns:
            New PlatformConfiguration instance
        """
        return cls.model_validate(data)

    def validate_configuration(self) -> tuple[bool, list[str]]:
        """
        Validate the configuration for common issues.

        Checks for invalid paths, incompatible settings, and
        other potential problems.

        Returns:
            Tuple of (is_valid, errors) where is_valid is True if no errors

        Example:
            >>> config = PlatformConfiguration(
            ...     name="Test", game_id=uuid4(),
            ...     display=DisplayConfig(width=1920, height=1080)
            ... )
            >>> is_valid, errors = config.validate_configuration()
        """
        errors = []

        # Check display resolution is reasonable
        if self.display.width and self.display.height:
            if self.display.width < 640 or self.display.height < 480:
                errors.append("Resolution is too small (minimum 640x480)")
            aspect = self.display.width / self.display.height
            if aspect < 0.5 or aspect > 4.0:
                errors.append(f"Unusual aspect ratio: {aspect:.2f}")

        # Check compatibility layer settings
        if self.compatibility.use_compatibility_layer:
            if self.compatibility.layer_path and not Path(
                self.compatibility.layer_path
            ).exists():
                errors.append(
                    f"Compatibility layer path not found: {self.compatibility.layer_path}"
                )

        # Check working directory
        if self.working_directory and not self.working_directory.exists():
            errors.append(
                f"Working directory not found: {self.working_directory}"
            )

        return (len(errors) == 0, errors)
