"""Database models for Playnite Python service."""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, JSON, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class UserProfile(Base):
    """User profile storing preferences and statistics."""

    __tablename__ = "user_profiles"

    user_id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    preferences = Column(JSON)  # Genre preferences, playtime patterns, etc.


class GameData(Base):
    """Cached game data from Playnite."""

    __tablename__ = "game_data"

    game_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    genres = Column(JSON)
    developers = Column(JSON)
    publishers = Column(JSON)
    platforms = Column(JSON)
    tags = Column(JSON)
    features = Column(JSON)
    last_synced = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PlayHistory(Base):
    """Play session history."""

    __tablename__ = "play_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    game_id = Column(String, nullable=False, index=True)
    session_start = Column(DateTime, nullable=False)
    session_end = Column(DateTime)
    duration_seconds = Column(Integer)


class Recommendation(Base):
    """Generated recommendations with scoring details."""

    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    game_id = Column(String, nullable=False, index=True)
    score = Column(Float, nullable=False)
    reason = Column(Text)
    factors = Column(JSON)  # Detailed scoring factors
    sources = Column(JSON)  # Algorithms that contributed (content, collaborative, etc.)
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    user_feedback = Column(
        String, nullable=True
    )  # "liked", "dismissed", "played", "hidden"


class CaptureSession(Base):
    """Media capture session tracking."""

    __tablename__ = "capture_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, unique=True, nullable=False, index=True)
    game_id = Column(String, nullable=False)
    game_name = Column(String, nullable=False)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime, nullable=True)
    screenshot_count = Column(Integer, default=0)
    video_count = Column(Integer, default=0)
    backend_used = Column(String)


class CaptureMetadata(Base):
    """Metadata for captured screenshots and videos."""

    __tablename__ = "capture_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # File information
    file_path = Column(String, unique=True, nullable=False, index=True)
    file_name = Column(String, nullable=False)

    # Game and session association
    game_id = Column(String, nullable=False, index=True)
    game_name = Column(String, nullable=False)
    session_id = Column(String, nullable=False, index=True)

    # Capture details
    capture_type = Column(String, nullable=False)  # "screenshot", "video", "replay"
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Media properties
    file_size_bytes = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)  # For videos only
    resolution_width = Column(Integer, nullable=True)
    resolution_height = Column(Integer, nullable=True)
    format = Column(String, nullable=True)  # "png", "mp4", etc.

    # User-editable metadata
    tags = Column(JSON, nullable=True)  # List of custom tags
    notes = Column(Text, nullable=True)  # User notes
    rating = Column(Integer, nullable=True)  # 1-5 stars
    is_favorite = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
