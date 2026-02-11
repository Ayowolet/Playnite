"""Game model mirroring C# Playnite.SDK.Models.Game."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from .base import DatabaseObject
from .game_action import GameAction
from .game_rom import GameRom
from .link import Link
from .release_date import ReleaseDate

_EMPTY_UUID = uuid.UUID(int=0)


@dataclass(slots=True)
class Game(DatabaseObject):
    """Full game model with all persistent fields from Playnite's Game class."""

    # Provider-specific identifier (e.g. Steam app ID).
    game_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plugin_id: uuid.UUID = field(default_factory=lambda: _EMPTY_UUID)

    sorting_name: str | None = None
    description: str = ""
    notes: str = ""

    # Boolean flags
    hidden: bool = False
    favorite: bool = False
    is_installed: bool = False
    is_installing: bool = False
    is_uninstalling: bool = False
    is_launching: bool = False
    is_running: bool = False
    override_install_state: bool = False
    include_library_plugin_action: bool = True
    enable_system_hdr: bool = False

    # Relationship IDs
    platform_ids: list[uuid.UUID] | None = None
    developer_ids: list[uuid.UUID] | None = None
    publisher_ids: list[uuid.UUID] | None = None
    genre_ids: list[uuid.UUID] | None = None
    category_ids: list[uuid.UUID] | None = None
    tag_ids: list[uuid.UUID] | None = None
    feature_ids: list[uuid.UUID] | None = None
    series_ids: list[uuid.UUID] | None = None
    age_rating_ids: list[uuid.UUID] | None = None
    region_ids: list[uuid.UUID] | None = None

    # Single-value relationship IDs
    source_id: uuid.UUID = field(default_factory=lambda: _EMPTY_UUID)
    completion_status_id: uuid.UUID = field(default_factory=lambda: _EMPTY_UUID)

    # Dates
    release_date: ReleaseDate | None = None
    last_activity: datetime | None = None
    added: datetime | None = None
    modified: datetime | None = None
    last_size_scan_date: datetime | None = None

    # Play statistics
    playtime: int = 0
    play_count: int = 0
    install_size: int | None = None

    # Scores
    user_score: int | None = None
    critic_score: int | None = None
    community_score: int | None = None

    # Media paths (local file, HTTP URL, or database file ID)
    icon: str | None = None
    cover_image: str | None = None
    background_image: str | None = None

    # Paths
    install_directory: str | None = None
    version: str | None = None
    manual: str = ""

    # Scripts
    pre_script: str = ""
    post_script: str = ""
    game_started_script: str = ""
    use_global_pre_script: bool = True
    use_global_post_script: bool = True
    use_global_game_started_script: bool = True

    # Complex sub-objects
    links: list[Link] | None = None
    game_actions: list[GameAction] | None = None
    roms: list[GameRom] | None = None

    # ------------------------------------------------------------------ #
    # Computed properties (not serialised)
    # ------------------------------------------------------------------ #

    @property
    def release_year(self) -> int | None:
        return self.release_date.year if self.release_date else None

    @property
    def is_custom_game(self) -> bool:
        return self.plugin_id == _EMPTY_UUID
