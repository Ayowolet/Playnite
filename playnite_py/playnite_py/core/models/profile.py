"""
Profile data models for Playnite-Py.

This module defines the data structures for managing user profiles,
including profile settings, templates, security, statistics, and sharing.

Example:
    >>> from playnite_py.core.models.profile import Profile, ProfileSettings
    >>> settings = ProfileSettings(theme="dark", language="en")
    >>> profile = Profile(name="Personal", settings=settings)
    >>> print(profile.name)
    Personal
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class DataSharingMode(str, Enum):
    """
    Defines how data is shared between profiles.

    Attributes:
        NONE: No data sharing, fully isolated
        READ_ONLY: Can read shared data but not modify
        BIDIRECTIONAL: Full read-write access to shared data
        SELECTIVE: Share only specific categories of data
    """
    NONE = "none"
    READ_ONLY = "read_only"
    BIDIRECTIONAL = "bidirectional"
    SELECTIVE = "selective"


class ProfileSharing(BaseModel):
    """
    Configuration for data sharing between profiles.

    This model defines what data can be shared between profiles and how
    that sharing is implemented (symlinks, copies, or references).

    Attributes:
        mode: The sharing mode (none, read_only, bidirectional, selective)
        share_categories: Whether to share game categories
        share_tags: Whether to share game tags
        share_metadata_cache: Whether to share downloaded metadata
        share_media_files: Whether to share cover images, screenshots, etc.
        share_plugins: Whether to share plugin configurations
        shared_profile_ids: List of profile IDs this profile shares data with

    Example:
        >>> sharing = ProfileSharing(
        ...     mode=DataSharingMode.SELECTIVE,
        ...     share_categories=True,
        ...     share_tags=True,
        ...     share_metadata_cache=True
        ... )
    """
    mode: DataSharingMode = Field(
        default=DataSharingMode.NONE,
        description="How data is shared with other profiles"
    )
    share_categories: bool = Field(
        default=False,
        description="Share game categories across profiles"
    )
    share_tags: bool = Field(
        default=False,
        description="Share game tags across profiles"
    )
    share_metadata_cache: bool = Field(
        default=False,
        description="Share downloaded game metadata"
    )
    share_media_files: bool = Field(
        default=False,
        description="Share media files (covers, screenshots)"
    )
    share_plugins: bool = Field(
        default=False,
        description="Share plugin configurations"
    )
    shared_profile_ids: list[UUID] = Field(
        default_factory=list,
        description="IDs of profiles to share data with"
    )


class ProfileSecurity(BaseModel):
    """
    Security settings for a profile.

    Implements optional password protection using PBKDF2-SHA256 with
    configurable iterations and random salt for secure password storage.

    Attributes:
        password_protected: Whether the profile requires a password
        password_hash: PBKDF2-SHA256 hash of the password
        password_salt: Random salt used for hashing
        failed_attempts: Count of failed login attempts
        locked_until: Timestamp when profile will be unlocked (if locked)
        access_log_enabled: Whether to log profile access events
        max_failed_attempts: Number of attempts before lockout
        lockout_duration_minutes: How long lockout lasts

    Example:
        >>> security = ProfileSecurity(password_protected=True)
        >>> security.set_password("my_secure_password")
        >>> assert security.verify_password("my_secure_password")
    """
    password_protected: bool = Field(
        default=False,
        description="Whether password is required to access profile"
    )
    password_hash: Optional[str] = Field(
        default=None,
        description="PBKDF2-SHA256 hash of the password"
    )
    password_salt: Optional[str] = Field(
        default=None,
        description="Random salt for password hashing"
    )
    failed_attempts: int = Field(
        default=0,
        ge=0,
        description="Count of failed password attempts"
    )
    locked_until: Optional[datetime] = Field(
        default=None,
        description="Profile locked until this time"
    )
    access_log_enabled: bool = Field(
        default=False,
        description="Log all profile access events"
    )
    max_failed_attempts: int = Field(
        default=5,
        ge=1,
        description="Max failed attempts before lockout"
    )
    lockout_duration_minutes: int = Field(
        default=15,
        ge=1,
        description="Duration of lockout in minutes"
    )

    def set_password(self, password: str, iterations: int = 100000) -> None:
        """
        Set a new password for the profile.

        Uses PBKDF2-SHA256 with a random salt for secure password storage.
        The salt is 32 bytes (64 hex characters) and generated using
        cryptographically secure random bytes.

        Args:
            password: The plaintext password to hash
            iterations: Number of PBKDF2 iterations (default: 100000)

        Example:
            >>> security = ProfileSecurity(password_protected=True)
            >>> security.set_password("secure_pass_123")
            >>> security.password_hash is not None
            True
        """
        self.password_salt = secrets.token_hex(32)
        self.password_hash = self._hash_password(password, self.password_salt, iterations)
        self.password_protected = True
        self.failed_attempts = 0
        self.locked_until = None

    def verify_password(self, password: str, iterations: int = 100000) -> bool:
        """
        Verify a password against the stored hash.

        Performs constant-time comparison to prevent timing attacks.
        Increments failed attempt counter on failure.

        Args:
            password: The plaintext password to verify
            iterations: Number of PBKDF2 iterations (must match set_password)

        Returns:
            True if password matches, False otherwise

        Raises:
            ValueError: If profile has no password set

        Example:
            >>> security = ProfileSecurity(password_protected=True)
            >>> security.set_password("correct_password")
            >>> security.verify_password("correct_password")
            True
            >>> security.verify_password("wrong_password")
            False
        """
        if not self.password_hash or not self.password_salt:
            raise ValueError("No password set for this profile")

        computed_hash = self._hash_password(password, self.password_salt, iterations)
        # Use secrets.compare_digest for constant-time comparison
        is_valid = secrets.compare_digest(computed_hash, self.password_hash)

        if not is_valid:
            self.failed_attempts += 1
        else:
            self.failed_attempts = 0

        return is_valid

    def clear_password(self) -> None:
        """
        Remove password protection from the profile.

        Clears the password hash, salt, and resets failed attempts.

        Example:
            >>> security = ProfileSecurity(password_protected=True)
            >>> security.set_password("password")
            >>> security.clear_password()
            >>> security.password_protected
            False
        """
        self.password_protected = False
        self.password_hash = None
        self.password_salt = None
        self.failed_attempts = 0
        self.locked_until = None

    def is_locked(self) -> bool:
        """
        Check if the profile is currently locked due to failed attempts.

        Returns:
            True if profile is locked, False otherwise

        Example:
            >>> security = ProfileSecurity(max_failed_attempts=3)
            >>> security.is_locked()
            False
        """
        if self.locked_until is None:
            return False
        return datetime.now() < self.locked_until

    @staticmethod
    def _hash_password(password: str, salt: str, iterations: int) -> str:
        """
        Hash a password using PBKDF2-SHA256.

        Args:
            password: Plaintext password
            salt: Hex-encoded salt
            iterations: Number of PBKDF2 iterations

        Returns:
            Hex-encoded password hash
        """
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            iterations
        ).hex()


class ProfileStatistics(BaseModel):
    """
    Usage statistics for a profile.

    Tracks various metrics about profile usage including playtime,
    game counts, and access patterns.

    Attributes:
        created_at: When the profile was created
        last_used: When the profile was last accessed
        total_playtime_minutes: Total playtime across all games in this profile
        game_count: Number of games in this profile
        session_count: Number of times profile has been loaded
        last_played_game_id: ID of the most recently played game
        favorite_game_ids: List of user's favorite game IDs
        total_achievements: Total achievements earned in this profile

    Example:
        >>> stats = ProfileStatistics()
        >>> stats.record_session()
        >>> stats.session_count
        1
    """
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Profile creation timestamp"
    )
    last_used: Optional[datetime] = Field(
        default=None,
        description="Last profile access timestamp"
    )
    total_playtime_minutes: int = Field(
        default=0,
        ge=0,
        description="Total playtime in minutes"
    )
    game_count: int = Field(
        default=0,
        ge=0,
        description="Number of games in profile"
    )
    session_count: int = Field(
        default=0,
        ge=0,
        description="Number of profile sessions"
    )
    last_played_game_id: Optional[UUID] = Field(
        default=None,
        description="Most recently played game"
    )
    favorite_game_ids: list[UUID] = Field(
        default_factory=list,
        description="User's favorite games"
    )
    total_achievements: int = Field(
        default=0,
        ge=0,
        description="Total achievements earned"
    )

    def record_session(self) -> None:
        """
        Record a new profile session.

        Updates last_used timestamp and increments session count.

        Example:
            >>> stats = ProfileStatistics()
            >>> stats.record_session()
            >>> stats.session_count
            1
        """
        self.last_used = datetime.now()
        self.session_count += 1

    def add_playtime(self, minutes: int) -> None:
        """
        Add playtime to the profile statistics.

        Args:
            minutes: Number of minutes to add

        Example:
            >>> stats = ProfileStatistics()
            >>> stats.add_playtime(60)
            >>> stats.total_playtime_minutes
            60
        """
        self.total_playtime_minutes += max(0, minutes)


class ProfileSettings(BaseModel):
    """
    User preferences and settings for a profile.

    Contains all configurable options that control the appearance
    and behavior of the application for this profile.

    Attributes:
        theme: UI theme name (e.g., "dark", "light", "custom")
        language: Language code (e.g., "en", "de", "ja")
        default_view: Default library view mode
        grid_size: Grid view item size
        show_hidden_games: Whether to display hidden games
        auto_update_library: Auto-refresh library sources
        enabled_sources: List of enabled library source IDs
        disabled_plugins: List of disabled plugin IDs
        custom_fields: Dictionary of custom user-defined settings
        startup_profile_id: Profile to load on startup (if different)

    Example:
        >>> settings = ProfileSettings(
        ...     theme="dark",
        ...     language="en",
        ...     default_view="grid"
        ... )
    """
    theme: str = Field(
        default="default",
        description="UI theme name"
    )
    language: str = Field(
        default="en",
        pattern=r"^[a-z]{2}(-[A-Z]{2})?$",
        description="Language code (ISO 639-1)"
    )
    default_view: str = Field(
        default="grid",
        description="Default library view (grid, list, details)"
    )
    grid_size: int = Field(
        default=200,
        ge=100,
        le=500,
        description="Grid view item size in pixels"
    )
    show_hidden_games: bool = Field(
        default=False,
        description="Show hidden games in library"
    )
    auto_update_library: bool = Field(
        default=True,
        description="Auto-update library on startup"
    )
    enabled_sources: list[str] = Field(
        default_factory=lambda: ["steam", "epic", "gog"],
        description="Enabled library source identifiers"
    )
    disabled_plugins: list[str] = Field(
        default_factory=list,
        description="Disabled plugin identifiers"
    )
    custom_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Custom user-defined settings"
    )
    startup_profile_id: Optional[UUID] = Field(
        default=None,
        description="Override startup profile"
    )

    @field_validator("default_view")
    @classmethod
    def validate_view(cls, v: str) -> str:
        """Validate that view mode is supported."""
        allowed_views = {"grid", "list", "details", "compact"}
        if v not in allowed_views:
            raise ValueError(f"View must be one of: {allowed_views}")
        return v


class ProfileTemplate(BaseModel):
    """
    Template for creating new profiles.

    Templates provide predefined settings and configurations that
    can be used to quickly create new profiles with consistent setups.

    Attributes:
        id: Unique template identifier
        name: Human-readable template name
        description: Description of the template's purpose
        settings: Default settings for profiles created from this template
        sharing: Default sharing configuration
        is_builtin: Whether this is a system-provided template
        created_at: Template creation timestamp
        source_profile_id: Profile this template was created from (if any)

    Example:
        >>> template = ProfileTemplate(
        ...     name="Kids Profile",
        ...     description="Safe gaming profile for children",
        ...     settings=ProfileSettings(show_hidden_games=False)
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
    settings: ProfileSettings = Field(
        default_factory=ProfileSettings,
        description="Default profile settings"
    )
    sharing: ProfileSharing = Field(
        default_factory=ProfileSharing,
        description="Default sharing configuration"
    )
    is_builtin: bool = Field(
        default=False,
        description="System-provided template"
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Template creation time"
    )
    source_profile_id: Optional[UUID] = Field(
        default=None,
        description="Source profile for template creation"
    )


class Profile(BaseModel):
    """
    Represents a user's game library profile.

    A profile contains an isolated game library with its own database,
    configuration, media files, and settings. Profiles can optionally
    inherit settings from parent profiles and share data with other profiles.

    Attributes:
        id: Unique profile identifier
        name: Human-readable profile name
        description: Optional profile description
        settings: Profile-specific settings and preferences
        statistics: Usage statistics and metrics
        security: Security and access control settings
        sharing: Data sharing configuration
        parent_profile_id: Parent profile for inheritance (optional)
        data_directory: Path to profile's data directory
        is_active: Whether this profile is currently loaded
        is_default: Whether this is the default startup profile
        created_from_template_id: Template used to create this profile
        tags: User-defined tags for organization
        icon_path: Path to profile icon image

    Example:
        >>> profile = Profile(
        ...     name="Personal Gaming",
        ...     description="My personal game library"
        ... )
        >>> profile.settings.theme = "dark"
        >>> profile.save()
    """
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique profile identifier"
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Profile display name"
    )
    description: str = Field(
        default="",
        max_length=500,
        description="Profile description"
    )
    settings: ProfileSettings = Field(
        default_factory=ProfileSettings,
        description="Profile settings"
    )
    statistics: ProfileStatistics = Field(
        default_factory=ProfileStatistics,
        description="Usage statistics"
    )
    security: ProfileSecurity = Field(
        default_factory=ProfileSecurity,
        description="Security settings"
    )
    sharing: ProfileSharing = Field(
        default_factory=ProfileSharing,
        description="Data sharing config"
    )
    parent_profile_id: Optional[UUID] = Field(
        default=None,
        description="Parent profile for inheritance"
    )
    data_directory: Optional[Path] = Field(
        default=None,
        description="Profile data directory path"
    )
    is_active: bool = Field(
        default=False,
        description="Profile is currently loaded"
    )
    is_default: bool = Field(
        default=False,
        description="Default startup profile"
    )
    created_from_template_id: Optional[UUID] = Field(
        default=None,
        description="Source template ID"
    )
    tags: list[str] = Field(
        default_factory=list,
        description="User-defined tags"
    )
    icon_path: Optional[Path] = Field(
        default=None,
        description="Path to profile icon"
    )

    model_config = {
        "json_encoders": {
            Path: str,
            datetime: lambda v: v.isoformat(),
            UUID: str,
        }
    }

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """
        Validate profile name is filesystem-safe.

        Names cannot contain characters that would cause issues
        with directory creation on any supported platform.
        """
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            if char in v:
                raise ValueError(f"Profile name cannot contain: {invalid_chars}")
        return v.strip()

    @model_validator(mode="after")
    def set_data_directory(self) -> "Profile":
        """Set default data directory based on profile ID if not specified."""
        if self.data_directory is None:
            # Will be set by ProfileManager based on app data location
            pass
        return self

    def get_effective_settings(self, parent: Optional["Profile"] = None) -> ProfileSettings:
        """
        Get effective settings with inheritance applied.

        If this profile has a parent, settings are merged with parent
        settings, with this profile's settings taking precedence.

        Args:
            parent: Parent profile for inheritance

        Returns:
            Merged settings object

        Example:
            >>> parent = Profile(name="Parent")
            >>> parent.settings.theme = "dark"
            >>> child = Profile(name="Child", parent_profile_id=parent.id)
            >>> effective = child.get_effective_settings(parent)
            >>> effective.theme
            'dark'
        """
        if parent is None:
            return self.settings.model_copy()

        # Start with parent settings
        merged_data = parent.settings.model_dump()
        # Override with child settings (non-default values)
        child_data = self.settings.model_dump()

        # Only override if child has explicitly set the value
        defaults = ProfileSettings().model_dump()
        for key, value in child_data.items():
            if value != defaults.get(key):
                merged_data[key] = value

        return ProfileSettings(**merged_data)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert profile to dictionary for serialization.

        Returns:
            Dictionary representation of the profile
        """
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Profile":
        """
        Create a profile from a dictionary.

        Args:
            data: Dictionary containing profile data

        Returns:
            New Profile instance
        """
        return cls.model_validate(data)

    @classmethod
    def from_template(cls, template: ProfileTemplate, name: str) -> "Profile":
        """
        Create a new profile from a template.

        Args:
            template: Template to base profile on
            name: Name for the new profile

        Returns:
            New Profile instance with template settings

        Example:
            >>> template = ProfileTemplate(name="Gaming")
            >>> profile = Profile.from_template(template, "My Games")
            >>> profile.created_from_template_id == template.id
            True
        """
        return cls(
            name=name,
            settings=template.settings.model_copy(),
            sharing=template.sharing.model_copy(),
            created_from_template_id=template.id,
        )
