"""Data models for game library."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


def _safe_json_loads(value: str | None, default=None):
    """Parse JSON with a fallback default on malformed data."""
    if not value:
        return default if default is not None else {}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Malformed JSON in database field: %r", value[:100] if isinstance(value, str) else value)
        return default if default is not None else {}


def _safe_decrypt_credentials(value: str | None) -> dict:
    """Decrypt credentials, falling back to plain JSON for legacy rows."""
    if not value:
        return {}
    try:
        from .achievements.credential_store import decrypt_credentials
        return decrypt_credentials(value)
    except Exception:
        logger.warning("Failed to decrypt credentials, trying plain JSON fallback")
        return _safe_json_loads(value, {})


class PlatformType(str, Enum):
    STEAM = "steam"
    XBOX = "xbox"
    PSN = "psn"
    GOG = "gog"
    MANUAL = "manual"


class BackupType(str, Enum):
    FULL = "full"
    INCREMENTAL = "incremental"


class SyncStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DifficultyTier(str, Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    VERY_RARE = "very_rare"
    ULTRA_RARE = "ultra_rare"

    @classmethod
    def from_global_pct(cls, pct: float) -> DifficultyTier:
        if pct >= 50.0:
            return cls.COMMON
        elif pct >= 25.0:
            return cls.UNCOMMON
        elif pct >= 10.0:
            return cls.RARE
        elif pct >= 2.0:
            return cls.VERY_RARE
        else:
            return cls.ULTRA_RARE


@dataclass
class Platform:
    id: int | None = None
    name: str = ""
    api_type: str = ""
    credentials: dict = field(default_factory=dict)
    enabled: bool = True

    @classmethod
    def from_row(cls, row: dict) -> Platform:
        return cls(
            id=row["id"],
            name=row["name"],
            api_type=row["api_type"],
            credentials=_safe_decrypt_credentials(row["credentials"]),
            enabled=bool(row["enabled"]),
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["credentials"] = "(hidden)"
        return d


@dataclass
class Game:
    id: int | None = None
    platform_id: int = 0
    external_game_id: str = ""
    name: str = ""
    total_achievements: int = 0
    icon_url: str = ""
    platform_name: str = ""

    @classmethod
    def from_row(cls, row: dict) -> Game:
        return cls(
            id=row["id"],
            platform_id=row["platform_id"],
            external_game_id=row["external_game_id"],
            name=row["name"],
            total_achievements=row["total_achievements"],
            icon_url=row["icon_url"] or "",
            platform_name=row["platform_name"] if "platform_name" in row.keys() else "",
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Achievement:
    id: int | None = None
    game_id: int = 0
    external_achievement_id: str = ""
    name: str = ""
    description: str = ""
    icon_url: str = ""
    locked_icon_url: str = ""
    global_completion_pct: float = 0.0
    difficulty_score: float = 0.0
    is_hidden: bool = False
    max_progress: int = 0
    category: str = ""
    # Unlock data (joined from achievement_unlocks)
    unlocked: bool = False
    unlock_date: str | None = None
    current_progress: int = 0
    source: str = "api"

    @classmethod
    def from_row(cls, row: dict) -> Achievement:
        keys = row.keys()
        return cls(
            id=row["id"],
            game_id=row["game_id"],
            external_achievement_id=row["external_achievement_id"],
            name=row["name"],
            description=row["description"] or "",
            icon_url=row["icon_url"] or "",
            locked_icon_url=row["locked_icon_url"] or "",
            global_completion_pct=row["global_completion_pct"] or 0.0,
            difficulty_score=row["difficulty_score"] or 0.0,
            is_hidden=bool(row["is_hidden"]),
            max_progress=row["max_progress"] or 0,
            category=row["category"] or "",
            unlocked=bool(row["unlocked"]) if "unlocked" in keys else False,
            unlock_date=row["unlock_date"] if "unlock_date" in keys else None,
            current_progress=row["current_progress"] if "current_progress" in keys else 0,
            source=row["source"] if "source" in keys else "api",
        )

    @property
    def difficulty_tier(self) -> DifficultyTier:
        return DifficultyTier.from_global_pct(self.global_completion_pct)

    @property
    def is_rare(self) -> bool:
        return self.global_completion_pct < 10.0

    @property
    def progress_pct(self) -> float:
        if self.max_progress <= 0:
            return 100.0 if self.unlocked else 0.0
        return min(100.0, (self.current_progress / self.max_progress) * 100)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["difficulty_tier"] = self.difficulty_tier.value
        d["is_rare"] = self.is_rare
        d["progress_pct"] = self.progress_pct
        return d


@dataclass
class SyncRecord:
    id: int | None = None
    platform_id: int | None = None
    sync_type: str = "full"
    started_at: str = ""
    completed_at: str | None = None
    achievements_found: int = 0
    new_unlocks: int = 0
    status: str = "running"
    error_message: str | None = None

    @classmethod
    def from_row(cls, row: dict) -> SyncRecord:
        return cls(
            id=row["id"],
            platform_id=row["platform_id"],
            sync_type=row["sync_type"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            achievements_found=row["achievements_found"],
            new_unlocks=row["new_unlocks"],
            status=row["status"],
            error_message=row["error_message"],
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GameCompletionStats:
    game_id: int = 0
    game_name: str = ""
    platform_name: str = ""
    total_achievements: int = 0
    unlocked_count: int = 0
    locked_count: int = 0
    completion_pct: float = 0.0
    rare_unlocked: int = 0
    rare_total: int = 0
    avg_difficulty: float = 0.0
    latest_unlock: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OverallStats:
    total_games: int = 0
    total_achievements: int = 0
    total_unlocked: int = 0
    overall_completion_pct: float = 0.0
    rare_unlocked: int = 0
    ultra_rare_unlocked: int = 0
    perfect_games: int = 0
    avg_game_completion: float = 0.0
    total_platforms: int = 0
    recent_unlocks: list = field(default_factory=list)
    unlock_velocity: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BackupRecord:
    id: int | None = None
    profile_id: int | None = None
    backup_type: str = "full"
    file_path: str = ""
    created_at: str = ""
    size_bytes: int = 0
    compressed_size: int = 0
    is_encrypted: bool = False
    destination: str = "local"
    checksum: str = ""
    parent_backup_id: int | None = None
    status: str = "completed"
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: dict) -> BackupRecord:
        return cls(
            id=row["id"],
            profile_id=row["profile_id"],
            backup_type=row["backup_type"],
            file_path=row["file_path"],
            created_at=row["created_at"],
            size_bytes=row["size_bytes"],
            compressed_size=row["compressed_size"],
            is_encrypted=bool(row["is_encrypted"]),
            destination=row["destination"],
            checksum=row["checksum"] or "",
            parent_backup_id=row["parent_backup_id"],
            status=row["status"],
            metadata=_safe_json_loads(row["metadata"], {}),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BackupProfile:
    id: int | None = None
    name: str = ""
    description: str = ""
    schedule_cron: str | None = None
    retention_days: int = 30
    max_backups: int = 10
    destinations: list[str] = field(default_factory=lambda: ["local"])
    include_patterns: list[str] = field(default_factory=lambda: ["*"])
    exclude_patterns: list[str] = field(default_factory=list)
    encrypt: bool = False

    @classmethod
    def from_row(cls, row: dict) -> BackupProfile:
        return cls(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            schedule_cron=row["schedule_cron"],
            retention_days=row["retention_days"],
            max_backups=row["max_backups"],
            destinations=_safe_json_loads(row["destinations"], ["local"]),
            include_patterns=_safe_json_loads(row["include_patterns"], ["*"]),
            exclude_patterns=_safe_json_loads(row["exclude_patterns"], []),
            encrypt=bool(row["encrypt"]),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BackupReport:
    backup_id: int = 0
    backup_type: str = "full"
    created_at: str = ""
    file_path: str = ""
    total_items: int = 0
    total_size: int = 0
    compressed_size: int = 0
    compression_ratio: float = 0.0
    is_encrypted: bool = False
    items_by_type: dict = field(default_factory=dict)
    is_verified: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AchievementMilestone:
    id: int | None = None
    milestone_type: str = ""
    milestone_value: str = ""
    reached_at: str = ""
    details: dict = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: dict) -> AchievementMilestone:
        return cls(
            id=row["id"],
            milestone_type=row["milestone_type"],
            milestone_value=row["milestone_value"],
            reached_at=row["reached_at"],
            details=_safe_json_loads(row["details"], {}),
        )

    def to_dict(self) -> dict:
        return asdict(self)
