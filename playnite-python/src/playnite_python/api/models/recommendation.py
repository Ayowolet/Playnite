"""Pydantic models for recommendation API."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class GameData(BaseModel):
    """Game data sent from Playnite."""

    game_id: str = Field(..., description="Unique game identifier")
    name: str = Field(..., description="Game name")
    genres: Optional[List[str]] = Field(default=[], description="Game genres")
    developers: Optional[List[str]] = Field(default=[], description="Game developers")
    publishers: Optional[List[str]] = Field(default=[], description="Game publishers")
    platforms: Optional[List[str]] = Field(default=[], description="Game platforms")
    tags: Optional[List[str]] = Field(default=[], description="User-defined tags")
    features: Optional[List[str]] = Field(default=[], description="Game features (multiplayer, etc.)")
    playtime_seconds: int = Field(default=0, description="Total playtime in seconds")
    play_count: int = Field(default=0, description="Number of times played")
    user_score: Optional[int] = Field(default=None, description="User rating (0-100)")
    community_score: Optional[int] = Field(default=None, description="Community rating (0-100)")
    critic_score: Optional[int] = Field(default=None, description="Critic rating (0-100)")
    completion_status: Optional[str] = Field(default=None, description="Completion status")
    is_installed: bool = Field(default=False, description="Whether game is installed")
    favorite: bool = Field(default=False, description="Whether game is marked as favorite")
    hidden: bool = Field(default=False, description="Whether game is hidden")
    # Explicit filtering fields
    time_to_complete: Optional[int] = Field(
        default=None, description="Average hours to complete (main story)"
    )
    time_to_complete_100: Optional[int] = Field(
        default=None, description="Hours to 100% complete"
    )
    difficulty: Optional[str] = Field(
        default=None, description="Difficulty level: easy, medium, hard, extreme"
    )
    vr_compatible: bool = Field(default=False, description="Supports VR headsets")
    vr_required: bool = Field(default=False, description="Requires VR (VR-exclusive)")


class RecommendationContext(BaseModel):
    """Context for generating recommendations."""

    mood: Optional[str] = Field(
        default=None,
        description="User's current mood (relaxing, challenging, story, social, etc.)",
    )
    time_of_day: Optional[str] = Field(
        default=None,
        description="Time of day (morning, afternoon, evening, night)",
    )
    session_length: Optional[str] = Field(
        default=None, description="Expected session length (short, medium, long)"
    )


class RecommendationFilters(BaseModel):
    """Explicit filters to apply to recommendations."""

    min_completion_hours: Optional[int] = Field(
        default=None, ge=0, description="Minimum hours to complete (e.g., 0 for quick games)"
    )
    max_completion_hours: Optional[int] = Field(
        default=None, ge=1, description="Maximum hours to complete (e.g., 10 for short games)"
    )
    difficulty_levels: Optional[List[str]] = Field(
        default=None, description="Allowed difficulty levels: easy, medium, hard, extreme"
    )
    multiplayer_only: Optional[bool] = Field(
        default=None, description="True: only multiplayer games, False: only single-player"
    )
    vr_compatible: Optional[bool] = Field(
        default=None, description="True: only VR-compatible games, False: exclude VR games"
    )
    vr_required: Optional[bool] = Field(
        default=None, description="True: only VR-exclusive games"
    )
    platforms: Optional[List[str]] = Field(
        default=None, description="Filter by platforms (e.g., ['PC', 'PlayStation 5'])"
    )


class RecommendationRequest(BaseModel):
    """Request to generate game recommendations."""

    user_id: str = Field(..., description="User identifier")
    library: List[GameData] = Field(..., description="User's game library")
    context: Optional[RecommendationContext] = Field(
        default=None, description="Optional context for recommendations"
    )
    filters: Optional[RecommendationFilters] = Field(
        default=None, description="Optional explicit filters for recommendations"
    )
    limit: int = Field(default=10, ge=1, le=50, description="Number of recommendations to return")


class RecommendationResponse(BaseModel):
    """Individual game recommendation."""

    recommendation_id: int = Field(..., description="Database ID for feedback submission")
    game_id: str = Field(..., description="Recommended game ID")
    game_name: Optional[str] = Field(default=None, description="Recommended game name")
    score: float = Field(..., description="Recommendation score (0-1)")
    reason: str = Field(..., description="Human-readable explanation")
    factors: Dict[str, Any] = Field(..., description="Detailed scoring factors")
    sources: Optional[List[str]] = Field(
        default=None, description="Algorithms that contributed to this recommendation"
    )


class RecommendationListResponse(BaseModel):
    """List of recommendations with metadata."""

    recommendations: List[RecommendationResponse]
    count: int = Field(..., description="Number of recommendations returned")
    generated_at: str = Field(..., description="ISO timestamp of generation")
    model_version: str = Field(default="1.0.0", description="Recommendation engine version")
