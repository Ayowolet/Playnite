"""
Core data models for the Playnite Python game library manager.

These models mirror the Playnite C# models and are serialised to/from SQLite
via JSON.  All IDs are UUIDs stored as strings.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .game_classification import (
    ScoreRating,
    ScoreGroup,
    PastTimeSegment,
    PlaytimeCategory,
    InstallSizeGroup,
    InstallationStatus,
    GameField,
    _score_rating,
    _score_group,
    _classify_past_time,
)


# ---------------------------------------------------------------------------
# Enumerations (game-action specific — stay here)
# ---------------------------------------------------------------------------

class GameActionType(Enum):
    """Supported game action execution types."""
    FILE = "File"
    URL = "URL"
    SCRIPT = "Script"
    EMULATOR = "Emulator"


class TrackingMode(Enum):
    """How game process tracking works after launch."""
    DEFAULT = "Default"
    PROCESS = "Process"
    DIRECTORY = "Directory"
    ORIGINAL_PROCESS = "OriginalProcess"
    PROCESS_NAME = "ProcessName"
    NONE = "None"


# ---------------------------------------------------------------------------
# Auxiliary value objects
# ---------------------------------------------------------------------------

@dataclass
class Link:
    """An external URL associated with a game (e.g. store page, wiki)."""
    name: str = ""
    url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "url": self.url}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Link":
        return cls(name=d.get("name", ""), url=d.get("url", ""))


@dataclass
class GameAction:
    """A single launchable action tied to a game (play, install, script…)."""
    name: str = "Play"
    type: GameActionType = GameActionType.FILE
    path: str = ""
    arguments: str = ""
    working_dir: str = ""
    is_play_action: bool = False
    tracking_mode: TrackingMode = TrackingMode.DEFAULT
    tracking_path: str = ""
    initial_tracking_delay: int = 0
    tracking_frequency: int = 2000
    script: str = ""
    emulator_id: Optional[str] = None
    emulator_profile_id: Optional[str] = None
    additional_arguments: str = ""
    override_default_args: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "path": self.path,
            "arguments": self.arguments,
            "working_dir": self.working_dir,
            "is_play_action": self.is_play_action,
            "tracking_mode": self.tracking_mode.value,
            "tracking_path": self.tracking_path,
            "initial_tracking_delay": self.initial_tracking_delay,
            "tracking_frequency": self.tracking_frequency,
            "script": self.script,
            "emulator_id": self.emulator_id,
            "emulator_profile_id": self.emulator_profile_id,
            "additional_arguments": self.additional_arguments,
            "override_default_args": self.override_default_args,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GameAction":
        return cls(
            name=d.get("name", "Play"),
            type=GameActionType(d.get("type", "File")),
            path=d.get("path", ""),
            arguments=d.get("arguments", ""),
            working_dir=d.get("working_dir", ""),
            is_play_action=d.get("is_play_action", False),
            tracking_mode=TrackingMode(d.get("tracking_mode", "Default")),
            tracking_path=d.get("tracking_path", ""),
            initial_tracking_delay=d.get("initial_tracking_delay", 0),
            tracking_frequency=d.get("tracking_frequency", 2000),
            script=d.get("script", ""),
            emulator_id=d.get("emulator_id"),
            emulator_profile_id=d.get("emulator_profile_id"),
            additional_arguments=d.get("additional_arguments", ""),
            override_default_args=d.get("override_default_args", False),
        )


# ---------------------------------------------------------------------------
# Named lookup objects
# ---------------------------------------------------------------------------

@dataclass
class NamedObject:
    """Base class for all named objects stored in lookup tables."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "NamedObject":
        obj = cls()
        obj.id = d.get("id", str(uuid.uuid4()))
        obj.name = d.get("name", "")
        return obj


@dataclass
class Platform(NamedObject):
    specification_id: str = ""
    icon: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"specification_id": self.specification_id, "icon": self.icon})
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Platform":
        obj = cls()
        obj.id = d.get("id", str(uuid.uuid4()))
        obj.name = d.get("name", "")
        obj.specification_id = d.get("specification_id", "")
        obj.icon = d.get("icon", "")
        return obj


@dataclass
class Genre(NamedObject):
    pass


@dataclass
class Company(NamedObject):
    pass


@dataclass
class Tag(NamedObject):
    pass


@dataclass
class Category(NamedObject):
    pass


@dataclass
class Series(NamedObject):
    pass


@dataclass
class AgeRating(NamedObject):
    pass


@dataclass
class Region(NamedObject):
    pass


@dataclass
class GameFeature(NamedObject):
    pass


@dataclass
class GameSource(NamedObject):
    pass


@dataclass
class CompletionStatus(NamedObject):
    pass


# ---------------------------------------------------------------------------
# Main Game model
# ---------------------------------------------------------------------------

@dataclass
class Game:
    """
    Primary game record.

    Foreign-key relationships (e.g. genres, platforms) are stored as lists of
    string IDs that reference separate lookup tables in the database.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    notes: str = ""
    version: str = ""

    # Provider-specific identifier (e.g. Steam AppID)
    game_id: str = ""
    # Custom sort name (falls back to ``name`` if empty)
    sorting_name: str = ""

    # Installation state
    is_installed: bool = False
    install_directory: str = ""
    install_size: Optional[int] = None  # bytes
    override_install_state: bool = False
    is_installing: bool = False
    is_uninstalling: bool = False
    last_size_scan_date: Optional[datetime] = None

    # ROM file paths (for emulated games)
    roms: List[str] = field(default_factory=list)

    # Whether library plugin default action should be included
    include_library_plugin_action: bool = True

    # Visibility
    is_hidden: bool = False
    is_favorite: bool = False

    # Classification IDs
    platform_ids: List[str] = field(default_factory=list)
    genre_ids: List[str] = field(default_factory=list)
    developer_ids: List[str] = field(default_factory=list)
    publisher_ids: List[str] = field(default_factory=list)
    tag_ids: List[str] = field(default_factory=list)
    category_ids: List[str] = field(default_factory=list)
    feature_ids: List[str] = field(default_factory=list)
    series_ids: List[str] = field(default_factory=list)
    age_rating_ids: List[str] = field(default_factory=list)
    region_ids: List[str] = field(default_factory=list)
    source_id: Optional[str] = None
    completion_status_id: Optional[str] = None

    # Play tracking
    play_time: int = 0       # total seconds
    play_count: int = 0
    last_activity: Optional[datetime] = None
    is_running: bool = False
    is_launching: bool = False

    # Per-game scripts (Python source)
    pre_script: str = ""
    post_script: str = ""
    game_started_script: str = ""
    use_global_pre_script: bool = True
    use_global_post_script: bool = True
    use_global_game_started_script: bool = True

    # Scores (0–100, None = not rated)
    user_score: Optional[int] = None
    community_score: Optional[int] = None
    critic_score: Optional[int] = None

    # Media paths / identifiers
    background_image: str = ""
    icon: str = ""
    cover_image: str = ""
    manual: str = ""

    # Actions and links
    game_actions: List[GameAction] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)

    # Dates
    release_date: Optional[datetime] = None
    added: datetime = field(default_factory=datetime.now)
    modified: datetime = field(default_factory=datetime.now)

    # External plugin data
    plugin_id: Optional[str] = None
    enable_system_hdr: bool = False

    # ---------------------------------------------------------------------------
    # Computed properties
    # ---------------------------------------------------------------------------

    @property
    def release_year(self) -> Optional[int]:
        """Year of release, or *None* if no release date is set."""
        return self.release_date.year if self.release_date else None

    @property
    def recent_activity(self) -> Optional[datetime]:
        """
        Most recent player-facing activity timestamp.

        If the game is installed this is the later of ``last_activity`` and
        ``modified``; otherwise it is just ``last_activity``.
        """
        candidates = [
            d for d in [
                self.last_activity,
                self.modified if self.is_installed else None,
            ]
            if d is not None
        ]
        if not candidates:
            return self.last_activity
        return max(candidates)

    @property
    def is_custom_game(self) -> bool:
        """*True* if the game was added manually (not via a library plugin)."""
        return self.plugin_id is None

    @property
    def installation_status(self) -> InstallationStatus:
        return InstallationStatus.INSTALLED if self.is_installed else InstallationStatus.UNINSTALLED

    # -- Score ratings ---------------------------------------------------------

    @property
    def user_score_rating(self) -> ScoreRating:
        return _score_rating(self.user_score)

    @property
    def community_score_rating(self) -> ScoreRating:
        return _score_rating(self.community_score)

    @property
    def critic_score_rating(self) -> ScoreRating:
        return _score_rating(self.critic_score)

    # -- Score groups ----------------------------------------------------------

    @property
    def user_score_group(self) -> ScoreGroup:
        return _score_group(self.user_score)

    @property
    def community_score_group(self) -> ScoreGroup:
        return _score_group(self.community_score)

    @property
    def critic_score_group(self) -> ScoreGroup:
        return _score_group(self.critic_score)

    # -- Time segments ---------------------------------------------------------

    @property
    def last_activity_segment(self) -> PastTimeSegment:
        return _classify_past_time(self.last_activity)

    @property
    def added_segment(self) -> PastTimeSegment:
        return _classify_past_time(self.added)

    @property
    def modified_segment(self) -> PastTimeSegment:
        return _classify_past_time(self.modified)

    @property
    def recent_activity_segment(self) -> PastTimeSegment:
        return _classify_past_time(self.recent_activity)

    # -- Playtime category -----------------------------------------------------

    @property
    def playtime_category(self) -> PlaytimeCategory:
        """Bucket for total play time (seconds)."""
        s = self.play_time
        if s == 0:
            return PlaytimeCategory.NOT_PLAYED
        if s < 3_600:
            return PlaytimeCategory.LESS_THAN_HOUR
        if s < 36_000:
            return PlaytimeCategory.O1_10
        if s < 360_000:
            return PlaytimeCategory.O10_100
        if s < 1_800_000:
            return PlaytimeCategory.O100_500
        if s < 3_600_000:
            return PlaytimeCategory.O500_1000
        return PlaytimeCategory.O1000PLUS

    # -- Install size group ----------------------------------------------------

    @property
    def install_size_group(self) -> InstallSizeGroup:
        """Bucket for :attr:`install_size` (bytes)."""
        sz = self.install_size
        if not sz:
            return InstallSizeGroup.NONE
        MB = 1024 * 1024
        GB = 1024 * MB
        if sz < 100 * MB:
            return InstallSizeGroup.S0
        if sz < GB:
            return InstallSizeGroup.S1
        if sz < 5 * GB:
            return InstallSizeGroup.S2
        if sz < 10 * GB:
            return InstallSizeGroup.S3
        if sz < 20 * GB:
            return InstallSizeGroup.S4
        if sz < 50 * GB:
            return InstallSizeGroup.S5
        if sz < 100 * GB:
            return InstallSizeGroup.S6
        return InstallSizeGroup.S7

    # ---------------------------------------------------------------------------
    # Convenience helpers
    # ---------------------------------------------------------------------------

    def get_play_action(self) -> Optional[GameAction]:
        """Return the primary play action, or the first available one."""
        for action in self.game_actions:
            if action.is_play_action:
                return action
        return self.game_actions[0] if self.game_actions else None

    def touch(self) -> None:
        """Update the ``modified`` timestamp to now."""
        self.modified = datetime.now()

    def get_copy(self) -> "Game":
        """Return a deep copy of this game via serialisation round-trip."""
        return Game.from_dict(self.to_dict())

    def get_name_group(self) -> str:
        """First letter of the name (uppercased), or ``"#"`` for non-alphabetic names."""
        first = self.name[0].upper() if self.name else ""
        return first if first.isalpha() else "#"

    def get_install_drive(self) -> str:
        """Drive / root anchor of :attr:`install_directory`, or ``""``."""
        return Path(self.install_directory).anchor if self.install_directory else ""

    def get_install_drive_group(self) -> str:
        """Drive group label (drive letter without trailing slash, or ``"#"``)."""
        drive = self.get_install_drive()
        return drive.rstrip("/\\") or "#"

    def get_install_size_group(self) -> InstallSizeGroup:
        """Delegate to the :attr:`install_size_group` property."""
        return self.install_size_group

    def get_differences(self, other: "Game") -> List[GameField]:
        """
        Return the list of :class:`GameField` values that differ between
        *self* and *other*.
        """
        diffs: List[GameField] = []
        for gf, attr in _GAME_FIELD_ATTR_MAP.items():
            if getattr(self, attr) != getattr(other, attr):
                diffs.append(gf)
        return diffs

    def copy_diff_to(self, target: "Game") -> None:
        """
        Copy fields from *self* to *target* where *self*'s value differs from
        a freshly-constructed :class:`Game` default.

        Used for metadata merging: only non-default source values overwrite the
        target, leaving already-populated target fields intact.
        """
        _defaults_dict = {
            f: getattr(Game(), a) for f, a in _GAME_FIELD_ATTR_MAP.items()
        }
        for gf, attr in _GAME_FIELD_ATTR_MAP.items():
            self_val = getattr(self, attr)
            if self_val != _defaults_dict[gf]:
                setattr(target, attr, self_val)

    # ---------------------------------------------------------------------------
    # Serialisation
    # ---------------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        def _dt(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None

        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "notes": self.notes,
            "version": self.version,
            "game_id": self.game_id,
            "sorting_name": self.sorting_name,
            "is_installed": self.is_installed,
            "install_directory": self.install_directory,
            "install_size": self.install_size,
            "override_install_state": self.override_install_state,
            "is_installing": self.is_installing,
            "is_uninstalling": self.is_uninstalling,
            "last_size_scan_date": _dt(self.last_size_scan_date),
            "roms": self.roms,
            "include_library_plugin_action": self.include_library_plugin_action,
            "is_hidden": self.is_hidden,
            "is_favorite": self.is_favorite,
            "platform_ids": self.platform_ids,
            "genre_ids": self.genre_ids,
            "developer_ids": self.developer_ids,
            "publisher_ids": self.publisher_ids,
            "tag_ids": self.tag_ids,
            "category_ids": self.category_ids,
            "feature_ids": self.feature_ids,
            "series_ids": self.series_ids,
            "age_rating_ids": self.age_rating_ids,
            "region_ids": self.region_ids,
            "source_id": self.source_id,
            "completion_status_id": self.completion_status_id,
            "play_time": self.play_time,
            "play_count": self.play_count,
            "last_activity": _dt(self.last_activity),
            "is_running": self.is_running,
            "is_launching": self.is_launching,
            "pre_script": self.pre_script,
            "post_script": self.post_script,
            "game_started_script": self.game_started_script,
            "use_global_pre_script": self.use_global_pre_script,
            "use_global_post_script": self.use_global_post_script,
            "use_global_game_started_script": self.use_global_game_started_script,
            "user_score": self.user_score,
            "community_score": self.community_score,
            "critic_score": self.critic_score,
            "background_image": self.background_image,
            "icon": self.icon,
            "cover_image": self.cover_image,
            "manual": self.manual,
            "game_actions": [a.to_dict() for a in self.game_actions],
            "links": [lnk.to_dict() for lnk in self.links],
            "release_date": _dt(self.release_date),
            "added": _dt(self.added),
            "modified": _dt(self.modified),
            "plugin_id": self.plugin_id,
            "enable_system_hdr": self.enable_system_hdr,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Game":
        def _dt(s: Optional[str]) -> Optional[datetime]:
            return datetime.fromisoformat(s) if s else None

        g = cls()
        g.id = d.get("id", str(uuid.uuid4()))
        g.name = d.get("name", "")
        g.description = d.get("description", "")
        g.notes = d.get("notes", "")
        g.version = d.get("version", "")
        g.game_id = d.get("game_id", "")
        g.sorting_name = d.get("sorting_name", "")
        g.is_installed = d.get("is_installed", False)
        g.install_directory = d.get("install_directory", "")
        g.install_size = d.get("install_size")
        g.override_install_state = d.get("override_install_state", False)
        g.is_installing = d.get("is_installing", False)
        g.is_uninstalling = d.get("is_uninstalling", False)
        g.last_size_scan_date = _dt(d.get("last_size_scan_date"))
        g.roms = d.get("roms", [])
        g.include_library_plugin_action = d.get("include_library_plugin_action", True)
        g.is_hidden = d.get("is_hidden", False)
        g.is_favorite = d.get("is_favorite", False)
        g.platform_ids = d.get("platform_ids", [])
        g.genre_ids = d.get("genre_ids", [])
        g.developer_ids = d.get("developer_ids", [])
        g.publisher_ids = d.get("publisher_ids", [])
        g.tag_ids = d.get("tag_ids", [])
        g.category_ids = d.get("category_ids", [])
        g.feature_ids = d.get("feature_ids", [])
        g.series_ids = d.get("series_ids", [])
        g.age_rating_ids = d.get("age_rating_ids", [])
        g.region_ids = d.get("region_ids", [])
        g.source_id = d.get("source_id")
        g.completion_status_id = d.get("completion_status_id")
        g.play_time = d.get("play_time", 0)
        g.play_count = d.get("play_count", 0)
        g.last_activity = _dt(d.get("last_activity"))
        g.is_running = d.get("is_running", False)
        g.is_launching = d.get("is_launching", False)
        g.pre_script = d.get("pre_script", "")
        g.post_script = d.get("post_script", "")
        g.game_started_script = d.get("game_started_script", "")
        g.use_global_pre_script = d.get("use_global_pre_script", True)
        g.use_global_post_script = d.get("use_global_post_script", True)
        g.use_global_game_started_script = d.get("use_global_game_started_script", True)
        g.user_score = d.get("user_score")
        g.community_score = d.get("community_score")
        g.critic_score = d.get("critic_score")
        g.background_image = d.get("background_image", "")
        g.icon = d.get("icon", "")
        g.cover_image = d.get("cover_image", "")
        g.manual = d.get("manual", "")
        g.game_actions = [GameAction.from_dict(a) for a in d.get("game_actions", [])]
        g.links = [Link.from_dict(lnk) for lnk in d.get("links", [])]
        g.release_date = _dt(d.get("release_date"))
        g.added = _dt(d.get("added")) or datetime.now()
        g.modified = _dt(d.get("modified")) or datetime.now()
        g.plugin_id = d.get("plugin_id")
        g.enable_system_hdr = d.get("enable_system_hdr", False)
        return g


# ---------------------------------------------------------------------------
# GameField → Game attribute mapping (auto-generated from dataclass fields)
# ---------------------------------------------------------------------------

# Override entries where Game attr name ≠ simple snake_case(GameField.name)
_GAME_FIELD_OVERRIDE: Dict[str, str] = {
    "Platforms": "platform_ids",
    "Genres": "genre_ids",
    "Developers": "developer_ids",
    "Publishers": "publisher_ids",
    "Tags": "tag_ids",
    "Categories": "category_ids",
    "Features": "feature_ids",
    "Series": "series_ids",
    "AgeRatings": "age_rating_ids",
    "Regions": "region_ids",
    "Source": "source_id",
    "CompletionStatus": "completion_status_id",
}


def _build_game_field_map() -> Dict[GameField, str]:
    """Build GameField→attr mapping from dataclass field names."""
    import dataclasses as _dc
    field_by_pascal: Dict[str, str] = {
        "".join(p.capitalize() for p in f.name.split("_")): f.name
        for f in _dc.fields(Game)
    }
    field_by_pascal.update(_GAME_FIELD_OVERRIDE)
    return {
        gf: field_by_pascal[gf.name]
        for gf in GameField
        if gf.name in field_by_pascal
    }


_GAME_FIELD_ATTR_MAP: Dict[GameField, str] = _build_game_field_map()
