"""SQLAlchemy ORM models for Python Playnite."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    """Return current UTC time as a naive datetime (stored without tzinfo in SQLite)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class JobStatus(str, enum.Enum):
    """Status values for BackupJob and RestoreLog records."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class SyncStatus(str, enum.Enum):
    """Status values for SyncLog records."""

    SUCCESS = "success"
    ERROR = "error"


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Game library
# ---------------------------------------------------------------------------


class Game(Base):
    """A game entry in the library, scoped to one platform."""

    __tablename__ = "games"
    __table_args__ = (
        UniqueConstraint("platform", "platform_game_id", name="uq_platform_game"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    platform_game_id: Mapped[str] = mapped_column(String(100), nullable=False)
    icon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_achievements: Mapped[int] = mapped_column(Integer, default=0)
    last_synced: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    achievements: Mapped[list[Achievement]] = relationship(
        back_populates="game", cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------


class Achievement(Base):
    """An achievement definition belonging to a game."""

    __tablename__ = "achievements"
    __table_args__ = (
        UniqueConstraint("game_id", "achievement_id", name="uq_game_achievement"),
        Index("ix_achievements_game_rare", "game_id", "is_rare"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), nullable=False)
    achievement_id: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    icon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon_locked_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Global completion percentage as reported by the platform
    global_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Calculated: 1.0 - (global_percentage / 100); null until global_percentage known
    difficulty_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_rare: Mapped[bool] = mapped_column(Boolean, default=False)
    # For incremental / multi-stage achievements
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow,
    )

    game: Mapped[Game] = relationship(back_populates="achievements")
    user_achievements: Mapped[list[UserAchievement]] = relationship(
        back_populates="achievement", cascade="all, delete-orphan",
    )


class UserAchievement(Base):
    """Per-user unlock record for an achievement."""

    __tablename__ = "user_achievements"
    __table_args__ = (
        UniqueConstraint(
            "achievement_id", "platform_user_id", name="uq_user_achievement",
        ),
        Index("ix_user_achievements_lookup", "achievement_id", "platform_user_id", "is_unlocked"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    achievement_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("achievements.id"), nullable=False,
    )
    platform_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    is_unlocked: Mapped[bool] = mapped_column(Boolean, default=False)
    unlock_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow,
    )

    achievement: Mapped[Achievement] = relationship(back_populates="user_achievements")


class SyncLog(Base):
    """Record of a platform sync operation."""

    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    sync_date: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    games_synced: Mapped[int] = mapped_column(Integer, default=0)
    achievements_found: Mapped[int] = mapped_column(Integer, default=0)
    achievements_unlocked: Mapped[int] = mapped_column(Integer, default=0)
    new_unlocks: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class AchievementNotification(Base):
    """Pending unlock notification."""

    __tablename__ = "achievement_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    achievement_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("achievements.id"), nullable=False,
    )
    platform_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    game_name: Mapped[str] = mapped_column(String(500), nullable=False)
    achievement_name: Mapped[str] = mapped_column(String(500), nullable=False)
    notified_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


class BackupProfile(Base):
    """Named backup strategy/profile."""

    __tablename__ = "backup_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    schedule_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # JSON list of destination paths
    destinations: Mapped[str | None] = mapped_column(Text, nullable=True)
    include_database: Mapped[bool] = mapped_column(Boolean, default=True)
    include_configs: Mapped[bool] = mapped_column(Boolean, default=True)
    include_themes: Mapped[bool] = mapped_column(Boolean, default=True)
    include_plugins: Mapped[bool] = mapped_column(Boolean, default=True)
    include_achievements: Mapped[bool] = mapped_column(Boolean, default=True)
    include_controller_mappings: Mapped[bool] = mapped_column(Boolean, default=True)
    max_retention_days: Mapped[int] = mapped_column(Integer, default=30)
    max_backup_count: Mapped[int] = mapped_column(Integer, default=10)
    encrypt: Mapped[bool] = mapped_column(Boolean, default=False)
    compress: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow,
    )

    jobs: Mapped[list[BackupJob]] = relationship(back_populates="profile")


class BackupJob(Base):
    """A single backup execution record."""

    __tablename__ = "backup_jobs"
    __table_args__ = (
        Index("ix_backup_jobs_created_type", "created_at", "backup_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backup_type: Mapped[str] = mapped_column(String(20), nullable=False)  # full / incremental
    profile_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("backup_profiles.id"), nullable=True,
    )
    parent_backup_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("backup_jobs.id"), nullable=True,
    )
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    backup_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_size: Mapped[int] = mapped_column(Integer, default=0)
    compressed_size: Mapped[int] = mapped_column(Integer, default=0)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    profile: Mapped[BackupProfile | None] = relationship(back_populates="jobs")
    files: Mapped[list[BackupFile]] = relationship(
        back_populates="job", cascade="all, delete-orphan",
    )
    restore_logs: Mapped[list[RestoreLog]] = relationship(back_populates="backup_job")


class BackupFile(Base):
    """Individual file record within a backup job."""

    __tablename__ = "backup_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("backup_jobs.id"), nullable=False,
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    modified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    backup_category: Mapped[str | None] = mapped_column(String(50), nullable=True)

    job: Mapped[BackupJob] = relationship(back_populates="files")


class RestoreLog(Base):
    """Record of a restore operation."""

    __tablename__ = "restore_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backup_job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("backup_jobs.id"), nullable=False,
    )
    restored_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    items_restored: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    selective: Mapped[bool] = mapped_column(Boolean, default=False)
    # JSON list of restored category names
    restored_categories: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    backup_job: Mapped[BackupJob] = relationship(back_populates="restore_logs")
