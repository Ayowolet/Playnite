"""Pydantic models for capture API."""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class CaptureSettings(BaseModel):
    """Settings for capture session."""

    screenshot_hotkey: str = Field(default="f8", description="Hotkey for screenshots")
    video_hotkey: str = Field(default="f9", description="Hotkey for video recording")
    backend: str = Field(default="direct", description="Capture backend (direct, obs, gamebar)")
    video_quality: str = Field(default="high", description="Video quality (low, medium, high)")


class StartCaptureRequest(BaseModel):
    """Request to start a capture session."""

    game_id: str = Field(..., description="Game identifier")
    game_name: str = Field(..., description="Game name")
    process_id: int = Field(..., description="Game process ID")
    settings: Optional[CaptureSettings] = Field(default=None, description="Capture settings")


class CaptureSessionResponse(BaseModel):
    """Response with capture session information."""

    session_id: str = Field(..., description="Unique session identifier")
    status: str = Field(..., description="Session status")
    game_name: Optional[str] = Field(default=None, description="Game name")
    backend: Optional[str] = Field(default=None, description="Backend being used")
    screenshot_count: Optional[int] = Field(default=0, description="Number of screenshots taken")
    video_count: Optional[int] = Field(default=0, description="Number of videos recorded")


class ScreenshotResponse(BaseModel):
    """Response after capturing a screenshot."""

    session_id: str = Field(..., description="Session identifier")
    file_path: str = Field(..., description="Path to captured screenshot")
    timestamp: str = Field(..., description="ISO timestamp of capture")
    size_bytes: Optional[int] = Field(default=None, description="File size in bytes")


class VideoResponse(BaseModel):
    """Response after video recording."""

    session_id: str = Field(..., description="Session identifier")
    file_path: Optional[str] = Field(default=None, description="Path to recorded video")
    recording: bool = Field(..., description="Whether recording is active")


class StorageUsageResponse(BaseModel):
    """Storage usage statistics."""

    total_size_bytes: int = Field(..., description="Total size in bytes")
    total_size_mb: float = Field(..., description="Total size in MB")
    total_size_gb: float = Field(..., description="Total size in GB")
    game_count: int = Field(..., description="Number of games with captures")
    total_screenshots: int = Field(..., description="Total screenshot count")
    total_videos: int = Field(..., description="Total video count")


class GameCapturesResponse(BaseModel):
    """List of captures for a specific game."""

    game_id: str = Field(..., description="Game identifier")
    screenshots: list = Field(..., description="List of screenshot paths")
    videos: list = Field(..., description="List of video paths")


class CaptureMetadataResponse(BaseModel):
    """Detailed metadata for a capture."""

    id: int = Field(..., description="Metadata identifier")
    file_path: str = Field(..., description="Path to capture file")
    file_name: str = Field(..., description="File name")
    game_id: str = Field(..., description="Game identifier")
    game_name: str = Field(..., description="Game name")
    session_id: str = Field(..., description="Capture session ID")
    capture_type: str = Field(..., description="Type: screenshot, video, or replay")
    timestamp: str = Field(..., description="ISO timestamp of capture")
    file_size_bytes: Optional[int] = Field(default=None, description="File size in bytes")
    duration_seconds: Optional[float] = Field(default=None, description="Video duration (seconds)")
    resolution_width: Optional[int] = Field(default=None, description="Width in pixels")
    resolution_height: Optional[int] = Field(default=None, description="Height in pixels")
    format: Optional[str] = Field(default=None, description="File format (png, mp4, etc.)")
    tags: list = Field(default=[], description="Custom tags")
    notes: Optional[str] = Field(default=None, description="User notes")
    rating: Optional[int] = Field(default=None, description="Rating 1-5")
    is_favorite: bool = Field(default=False, description="Favorite status")
    created_at: Optional[str] = Field(default=None, description="ISO creation timestamp")
    updated_at: Optional[str] = Field(default=None, description="ISO last update timestamp")


class MetadataUpdateRequest(BaseModel):
    """Request to update metadata fields."""

    tags: Optional[list] = Field(default=None, description="New tags list")
    notes: Optional[str] = Field(default=None, description="New notes text")
    rating: Optional[int] = Field(default=None, ge=1, le=5, description="New rating 1-5")
    is_favorite: Optional[bool] = Field(default=None, description="New favorite status")


class SearchCapturesRequest(BaseModel):
    """Request to search captures with filters."""

    game_id: Optional[str] = Field(default=None, description="Filter by game ID")
    capture_type: Optional[str] = Field(default=None, description="Filter by type: screenshot, video, replay")
    tags: Optional[list] = Field(default=None, description="Filter by tags (any match)")
    is_favorite: Optional[bool] = Field(default=None, description="Filter by favorite status")
    min_rating: Optional[int] = Field(default=None, ge=1, le=5, description="Minimum rating")
    start_date: Optional[str] = Field(default=None, description="ISO start date")
    end_date: Optional[str] = Field(default=None, description="ISO end date")
    limit: int = Field(default=100, ge=1, le=1000, description="Max results")
    offset: int = Field(default=0, ge=0, description="Results to skip")


class StatisticsResponse(BaseModel):
    """Capture statistics."""

    total_captures: int = Field(..., description="Total number of captures")
    total_screenshots: int = Field(..., description="Total screenshots")
    total_videos: int = Field(..., description="Total videos")
    total_replays: int = Field(..., description="Total instant replays")
    total_size_bytes: int = Field(..., description="Total size in bytes")
    total_size_mb: float = Field(..., description="Total size in MB")
    total_size_gb: float = Field(..., description="Total size in GB")
    favorites_count: int = Field(..., description="Number of favorites")
    games_count: int = Field(..., description="Number of games with captures")
