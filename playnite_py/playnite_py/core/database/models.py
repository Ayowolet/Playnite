"""
SQLAlchemy ORM models for Playnite-Py database.

This module defines the database schema using SQLAlchemy ORM,
mapping Pydantic models to database tables.

Note:
    These models are for database persistence only. Use the Pydantic
    models in playnite_py.core.models for application logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    type_annotation_map = {
        dict[str, Any]: JSON,
        list[str]: JSON,
        list[UUID]: JSON,
    }


class ProfileModel(Base):
    """
    Database model for user profiles.

    Stores profile metadata, settings, and references to related data.
    The actual game library is stored in a separate profile-specific database.

    Attributes:
        id: UUID primary key
        name: Profile display name
        description: Profile description
        settings_json: Serialized ProfileSettings
        statistics_json: Serialized ProfileStatistics
        security_json: Serialized ProfileSecurity
        sharing_json: Serialized ProfileSharing
        parent_profile_id: Parent profile for inheritance
        data_directory: Path to profile data
        is_active: Currently loaded profile
        is_default: Default startup profile
        created_from_template_id: Source template
        tags: JSON array of tags
        icon_path: Profile icon path
        created_at: Creation timestamp
        modified_at: Last modification
    """

    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    statistics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    security_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    sharing_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    parent_profile_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("profiles.id"), nullable=True
    )
    data_directory: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_from_template_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    icon_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    modified_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationship for inheritance
    parent: Mapped[Optional["ProfileModel"]] = relationship(
        "ProfileModel",
        remote_side=[id],
        backref="children",
    )


class ProfileTemplateModel(Base):
    """
    Database model for profile templates.

    Stores templates that can be used to create new profiles
    with predefined settings.

    Attributes:
        id: UUID primary key
        name: Template name
        description: Template description
        settings_json: Default settings
        sharing_json: Default sharing config
        is_builtin: System-provided template
        source_profile_id: Source profile ID
        created_at: Creation timestamp
    """

    __tablename__ = "profile_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    sharing_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    source_profile_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ProfileAccessLogModel(Base):
    """
    Database model for profile access logs.

    Tracks access events for profiles with security logging enabled.

    Attributes:
        id: Auto-increment primary key
        profile_id: Profile that was accessed
        event_type: Type of access event
        timestamp: Event timestamp
        ip_address: Client IP if applicable
        user_agent: Client user agent if applicable
        success: Whether access was successful
        details: Additional event details
    """

    __tablename__ = "profile_access_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("profiles.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class GameModel(Base):
    """
    Database model for games.

    Stores game entries within a profile's database.

    Attributes:
        id: UUID primary key
        name: Game display name
        sorting_name: Name for sorting
        source: Game source platform
        source_game_id: ID from source
        status: Installation status
        metadata_json: Serialized GameMetadata
        statistics_json: Serialized GamePlayStatistics
        actions_json: Serialized list of GameAction
        install_directory: Installation path
        icon_path: Icon image path
        cover_image_path: Cover image path
        background_image_path: Background path
        is_hidden: Hidden in library
        is_favorite: Marked favorite
        notes: User notes
        configuration_ids: Associated config IDs
        added_date: Date added
        modified_date: Last modified
    """

    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    sorting_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    source_game_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="not_installed")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    statistics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    actions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    install_directory: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    icon_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    cover_image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    background_image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    configuration_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    added_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    modified_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationship to configurations
    configurations: Mapped[list["ConfigurationModel"]] = relationship(
        "ConfigurationModel",
        back_populates="game",
        cascade="all, delete-orphan",
    )


class ConfigurationModel(Base):
    """
    Database model for platform configurations.

    Stores platform-specific game configurations.

    Attributes:
        id: UUID primary key
        name: Configuration name
        description: Configuration description
        game_id: Associated game ID
        platform_type: Target platform
        graphics_quality: Graphics preset
        display_json: Display settings
        audio_json: Audio settings
        launch_args_json: Launch arguments
        environment_json: Environment variables
        compatibility_json: Compatibility settings
        working_directory: Override directory
        pre_launch_script: Pre-launch script
        post_launch_script: Post-launch script
        is_default: Default for game
        is_enabled: Configuration active
        fallback_config_id: Fallback config
        priority: Auto-detect priority
        statistics_json: Usage statistics
        hardware_requirements: Requirements
        tags: Configuration tags
        created_at: Creation timestamp
        modified_at: Last modification
    """

    __tablename__ = "configurations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    game_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("games.id"), nullable=False, index=True
    )
    platform_type: Mapped[str] = mapped_column(String(50), default="desktop")
    graphics_quality: Mapped[str] = mapped_column(String(50), default="medium")
    display_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    audio_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    launch_args_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    environment_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    compatibility_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    working_directory: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    pre_launch_script: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    post_launch_script: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    fallback_config_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    statistics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    hardware_requirements: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    modified_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationship to game
    game: Mapped["GameModel"] = relationship("GameModel", back_populates="configurations")


class ConfigurationTemplateModel(Base):
    """
    Database model for configuration templates.

    Stores templates for creating platform configurations.

    Attributes:
        id: UUID primary key
        name: Template name
        description: Template description
        platform_type: Target platform
        graphics_quality: Graphics preset
        display_json: Display settings
        audio_json: Audio settings
        launch_args_json: Launch arguments
        environment_json: Environment variables
        compatibility_json: Compatibility settings
        is_builtin: System template
        created_at: Creation timestamp
    """

    __tablename__ = "configuration_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    platform_type: Mapped[str] = mapped_column(String(50), default="desktop")
    graphics_quality: Mapped[str] = mapped_column(String(50), default="medium")
    display_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    audio_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    launch_args_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    environment_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    compatibility_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# Event listeners for automatic timestamp updates
@event.listens_for(ProfileModel, "before_update")
def profile_before_update(mapper, connection, target):
    """Update modified_at timestamp before profile update."""
    target.modified_at = datetime.now()


@event.listens_for(GameModel, "before_update")
def game_before_update(mapper, connection, target):
    """Update modified_date timestamp before game update."""
    target.modified_date = datetime.now()


@event.listens_for(ConfigurationModel, "before_update")
def config_before_update(mapper, connection, target):
    """Update modified_at timestamp before configuration update."""
    target.modified_at = datetime.now()
