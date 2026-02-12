"""
Game data models for Playnite-Py.

This module defines the data structures for representing games,
game actions, and game metadata in the library.

Example:
    >>> from playnite_py.core.models.game import Game, GameAction
    >>> action = GameAction(name="Play", path="/games/mygame.exe")
    >>> game = Game(name="My Game", actions=[action])
    >>> print(game.name)
    My Game
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_serializer, field_validator


class GameStatus(str, Enum):
    """
    Installation and play status of a game.

    Attributes:
        NOT_INSTALLED: Game is in library but not installed
        INSTALLED: Game is installed and ready to play
        INSTALLING: Game is currently being installed
        UPDATING: Game is being updated
        RUNNING: Game is currently running
        UNINSTALLING: Game is being uninstalled
    """
    NOT_INSTALLED = "not_installed"
    INSTALLED = "installed"
    INSTALLING = "installing"
    UPDATING = "updating"
    RUNNING = "running"
    UNINSTALLING = "uninstalling"


class GameSource(str, Enum):
    """
    Source platform from which a game was imported.

    Attributes:
        STEAM: Valve Steam
        EPIC: Epic Games Store
        GOG: GOG.com
        ORIGIN: EA Origin/EA App
        UBISOFT: Ubisoft Connect
        BATTLE_NET: Blizzard Battle.net
        XBOX: Xbox/Microsoft Store
        PLAYSTATION: PlayStation (for remote play)
        NINTENDO: Nintendo (for emulation metadata)
        EMULATOR: ROM-based emulated game
        MANUAL: Manually added game
        ITCH: itch.io
        AMAZON: Amazon Games
        HUMBLE: Humble Bundle
        OTHER: Other source
    """
    STEAM = "steam"
    EPIC = "epic"
    GOG = "gog"
    ORIGIN = "origin"
    UBISOFT = "ubisoft"
    BATTLE_NET = "battle_net"
    XBOX = "xbox"
    PLAYSTATION = "playstation"
    NINTENDO = "nintendo"
    EMULATOR = "emulator"
    MANUAL = "manual"
    ITCH = "itch"
    AMAZON = "amazon"
    HUMBLE = "humble"
    OTHER = "other"


class GameActionType(str, Enum):
    """
    Type of game action that can be executed.

    Attributes:
        FILE: Execute a file (exe, script, etc.)
        URL: Open a URL in browser
        EMULATOR: Run with an emulator
        SCRIPT: Execute a custom script
    """
    FILE = "file"
    URL = "url"
    EMULATOR = "emulator"
    SCRIPT = "script"


class GameAction(BaseModel):
    """
    An executable action associated with a game.

    Represents a way to launch or interact with a game, such as
    running the main executable, opening a configuration tool,
    or launching through an emulator.

    Attributes:
        id: Unique action identifier
        name: Display name for the action (e.g., "Play", "Configure")
        type: Type of action (file, url, emulator, script)
        path: Path to executable or URL
        arguments: Command-line arguments
        working_directory: Working directory for execution
        is_default: Whether this is the primary play action
        emulator_id: Emulator to use (for emulator type actions)
        emulator_profile_id: Emulator profile to use
        script_content: Script content (for script type actions)

    Example:
        >>> action = GameAction(
        ...     name="Play",
        ...     type=GameActionType.FILE,
        ...     path="/games/mygame/mygame.exe",
        ...     arguments="--fullscreen",
        ...     is_default=True
        ... )
    """
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique action identifier"
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Action display name"
    )
    type: GameActionType = Field(
        default=GameActionType.FILE,
        description="Type of action"
    )
    path: Optional[str] = Field(
        default=None,
        description="Path to executable or URL"
    )
    arguments: str = Field(
        default="",
        description="Command-line arguments"
    )
    working_directory: Optional[Path] = Field(
        default=None,
        description="Working directory for execution"
    )
    is_default: bool = Field(
        default=False,
        description="Primary play action"
    )
    emulator_id: Optional[UUID] = Field(
        default=None,
        description="Emulator to use"
    )
    emulator_profile_id: Optional[UUID] = Field(
        default=None,
        description="Emulator profile"
    )
    script_content: Optional[str] = Field(
        default=None,
        description="Script content for script actions"
    )

    @field_serializer("id", "emulator_id", "emulator_profile_id")
    def serialize_uuid(self, v: UUID | None) -> str | None:
        """Serialize UUID fields to strings."""
        return str(v) if v else None

    @field_serializer("working_directory")
    def serialize_path(self, v: Path | None) -> str | None:
        """Serialize Path fields to strings."""
        return str(v) if v else None


class GameMetadata(BaseModel):
    """
    Metadata information for a game.

    Contains descriptive information about a game that can be
    fetched from metadata providers or entered manually.

    Attributes:
        description: Full game description/summary
        developers: List of developer company names
        publishers: List of publisher company names
        genres: List of genre names
        tags: User-defined tags
        categories: Library categories
        features: Game features (multiplayer, controller support, etc.)
        release_date: Original release date
        critic_score: Metacritic-style score (0-100)
        community_score: Community rating (0-100)
        age_rating: Age rating (ESRB, PEGI, etc.)
        series: Game series name
        platform: Platform name
        region: Game region
        version: Game version string
        links: Related URLs (website, store page, etc.)

    Example:
        >>> metadata = GameMetadata(
        ...     description="An action adventure game...",
        ...     developers=["Studio X"],
        ...     genres=["Action", "Adventure"],
        ...     release_date=datetime(2023, 1, 15)
        ... )
    """
    description: str = Field(
        default="",
        description="Game description"
    )
    developers: list[str] = Field(
        default_factory=list,
        description="Developer companies"
    )
    publishers: list[str] = Field(
        default_factory=list,
        description="Publisher companies"
    )
    genres: list[str] = Field(
        default_factory=list,
        description="Game genres"
    )
    tags: list[str] = Field(
        default_factory=list,
        description="User-defined tags"
    )
    categories: list[str] = Field(
        default_factory=list,
        description="Library categories"
    )
    features: list[str] = Field(
        default_factory=list,
        description="Game features"
    )
    release_date: Optional[datetime] = Field(
        default=None,
        description="Release date"
    )
    critic_score: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Critic score (0-100)"
    )
    community_score: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Community score (0-100)"
    )
    age_rating: Optional[str] = Field(
        default=None,
        description="Age rating"
    )
    series: Optional[str] = Field(
        default=None,
        description="Game series"
    )
    platform: Optional[str] = Field(
        default=None,
        description="Platform name"
    )
    region: Optional[str] = Field(
        default=None,
        description="Game region"
    )
    version: Optional[str] = Field(
        default=None,
        description="Game version"
    )
    links: dict[str, str] = Field(
        default_factory=dict,
        description="Related URLs"
    )

    @field_serializer("release_date")
    def serialize_datetime(self, v: datetime | None) -> str | None:
        """Serialize datetime fields to ISO format."""
        return v.isoformat() if v else None


class GamePlayStatistics(BaseModel):
    """
    Play statistics for a game within a profile.

    Tracks playtime, session count, and other gameplay metrics
    specific to the current profile (separate from global stats).

    Attributes:
        total_playtime_minutes: Total time played in minutes
        session_count: Number of play sessions
        last_played: Last play session timestamp
        first_played: First play session timestamp
        completion_percentage: Game completion progress (0-100)
        achievements_earned: Number of achievements earned
        achievements_total: Total achievements available

    Example:
        >>> stats = GamePlayStatistics()
        >>> stats.record_session(60)
        >>> stats.total_playtime_minutes
        60
    """
    total_playtime_minutes: int = Field(
        default=0,
        ge=0,
        description="Total playtime in minutes"
    )
    session_count: int = Field(
        default=0,
        ge=0,
        description="Number of sessions"
    )
    last_played: Optional[datetime] = Field(
        default=None,
        description="Last play timestamp"
    )
    first_played: Optional[datetime] = Field(
        default=None,
        description="First play timestamp"
    )
    completion_percentage: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Completion progress"
    )
    achievements_earned: int = Field(
        default=0,
        ge=0,
        description="Achievements earned"
    )
    achievements_total: int = Field(
        default=0,
        ge=0,
        description="Total achievements"
    )

    def record_session(self, playtime_minutes: int) -> None:
        """
        Record a play session.

        Args:
            playtime_minutes: Duration of the session in minutes

        Example:
            >>> stats = GamePlayStatistics()
            >>> stats.record_session(45)
            >>> stats.session_count
            1
            >>> stats.total_playtime_minutes
            45
        """
        now = datetime.now()
        self.total_playtime_minutes += max(0, playtime_minutes)
        self.session_count += 1
        self.last_played = now
        if self.first_played is None:
            self.first_played = now


class Game(BaseModel):
    """
    Represents a game in the library.

    A game is the core entity in the library, containing all information
    about a single game including metadata, play statistics, actions,
    and media files.

    Attributes:
        id: Unique game identifier
        name: Game display name
        sorting_name: Name used for sorting (optional)
        source: Platform source (Steam, Epic, etc.)
        source_game_id: ID from the source platform
        status: Installation status
        metadata: Game metadata
        statistics: Play statistics for current profile
        actions: List of game actions
        install_directory: Game installation path
        icon_path: Path to game icon
        cover_image_path: Path to cover image
        background_image_path: Path to background image
        is_hidden: Whether game is hidden in library
        is_favorite: Whether game is marked as favorite
        notes: User notes about the game
        added_date: When game was added to library
        modified_date: Last modification timestamp
        configuration_ids: Platform configuration IDs for this game

    Example:
        >>> game = Game(
        ...     name="Cyberpunk 2077",
        ...     source=GameSource.GOG,
        ...     actions=[GameAction(name="Play", path="/games/cp2077.exe")]
        ... )
    """
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique game identifier"
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Game display name"
    )
    sorting_name: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Name for sorting"
    )
    source: GameSource = Field(
        default=GameSource.MANUAL,
        description="Game source platform"
    )
    source_game_id: Optional[str] = Field(
        default=None,
        description="ID from source platform"
    )
    status: GameStatus = Field(
        default=GameStatus.NOT_INSTALLED,
        description="Installation status"
    )
    metadata: GameMetadata = Field(
        default_factory=GameMetadata,
        description="Game metadata"
    )
    statistics: GamePlayStatistics = Field(
        default_factory=GamePlayStatistics,
        description="Play statistics"
    )
    actions: list[GameAction] = Field(
        default_factory=list,
        description="Game actions"
    )
    install_directory: Optional[Path] = Field(
        default=None,
        description="Installation path"
    )
    icon_path: Optional[Path] = Field(
        default=None,
        description="Icon image path"
    )
    cover_image_path: Optional[Path] = Field(
        default=None,
        description="Cover image path"
    )
    background_image_path: Optional[Path] = Field(
        default=None,
        description="Background image path"
    )
    is_hidden: bool = Field(
        default=False,
        description="Hidden in library"
    )
    is_favorite: bool = Field(
        default=False,
        description="Marked as favorite"
    )
    notes: str = Field(
        default="",
        description="User notes"
    )
    added_date: datetime = Field(
        default_factory=datetime.now,
        description="Date added to library"
    )
    modified_date: datetime = Field(
        default_factory=datetime.now,
        description="Last modification date"
    )
    configuration_ids: list[UUID] = Field(
        default_factory=list,
        description="Platform configuration IDs"
    )

    @field_serializer("id")
    def serialize_uuid(self, v: UUID) -> str:
        """Serialize UUID to string."""
        return str(v)

    @field_serializer("configuration_ids")
    def serialize_uuid_list(self, v: list[UUID]) -> list[str]:
        """Serialize UUID list to string list."""
        return [str(u) for u in v]

    @field_serializer("install_directory", "icon_path", "cover_image_path", "background_image_path")
    def serialize_path(self, v: Path | None) -> str | None:
        """Serialize Path fields to strings."""
        return str(v) if v else None

    @field_serializer("added_date", "modified_date")
    def serialize_datetime(self, v: datetime) -> str:
        """Serialize datetime to ISO format."""
        return v.isoformat()

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate and clean game name."""
        return v.strip()

    def get_default_action(self) -> Optional[GameAction]:
        """
        Get the default play action for this game.

        Returns:
            The default GameAction, or the first action if no default is set,
            or None if there are no actions.

        Example:
            >>> game = Game(name="Test")
            >>> action = GameAction(name="Play", is_default=True)
            >>> game.actions.append(action)
            >>> game.get_default_action().name
            'Play'
        """
        for action in self.actions:
            if action.is_default:
                return action
        return self.actions[0] if self.actions else None

    def get_display_name(self) -> str:
        """
        Get the name to display for this game.

        Uses sorting_name if set, otherwise uses name.

        Returns:
            Display name string
        """
        return self.sorting_name or self.name

    def mark_modified(self) -> None:
        """
        Update the modified timestamp.

        Should be called whenever the game data is changed.
        """
        self.modified_date = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """
        Convert game to dictionary for serialization.

        Returns:
            Dictionary representation of the game
        """
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Game":
        """
        Create a game from a dictionary.

        Args:
            data: Dictionary containing game data

        Returns:
            New Game instance
        """
        return cls.model_validate(data)
