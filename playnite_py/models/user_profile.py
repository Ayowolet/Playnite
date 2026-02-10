"""
User profile, play session, recommendation feedback, and mood models.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class Mood(str, Enum):
    """
    Player mood categories used to filter recommendations.
    Each mood maps to genre/tag preferences in the MoodFilter.
    """
    RELAXED = "relaxed"           # walking sims, puzzles, cozy games
    EXCITED = "excited"           # action, fighting, racing
    CREATIVE = "creative"         # city builders, sandbox, crafting
    COMPETITIVE = "competitive"   # multiplayer, sports, strategy
    NOSTALGIC = "nostalgic"       # retro, classics, pixel-art
    ADVENTUROUS = "adventurous"   # open-world, exploration, RPG
    CASUAL = "casual"             # party games, mobile-style, quick sessions
    FOCUSED = "focused"           # strategy, simulation, management
    SOCIAL = "social"             # co-op, party, multiplayer
    SPOOKY = "spooky"             # horror, dark, survival
    CHALLENGING = "challenging"   # difficult, hardcore, souls-like games


@dataclass
class PlaySession:
    """A single continuous play session for a game."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    game_id: str = ""
    user_id: str = ""
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    duration_seconds: int = 0

    @property
    def is_active(self) -> bool:
        return self.end_time is None

    def finish(self) -> None:
        """Mark the session as finished and compute duration."""
        self.end_time = datetime.utcnow()
        delta = self.end_time - self.start_time
        self.duration_seconds = max(0, int(delta.total_seconds()))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for key in ("start_time", "end_time"):
            if d[key] is not None and hasattr(d[key], "isoformat"):
                d[key] = d[key].isoformat()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlaySession":
        filtered = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        for key in ("start_time", "end_time"):
            if filtered.get(key) and isinstance(filtered[key], str):
                try:
                    from dateutil.parser import parse as parse_dt
                    filtered[key] = parse_dt(filtered[key])
                except Exception:
                    filtered[key] = None
        return cls(**filtered)


@dataclass
class RecommendationFeedback:
    """
    Records a user's reaction to a recommendation.
    The feedback engine uses these to adjust scoring weights over time.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    recommendation_id: str = ""       # links back to the recommendation batch
    game_id: str = ""
    action: str = ""
    # action values:
    #   "played"           — user started playing after recommendation
    #   "liked"            — user explicitly liked the suggestion
    #   "disliked"         — user explicitly disliked the suggestion
    #   "dismissed"        — user dismissed without playing
    #   "added_to_wishlist"— added to wishlist
    #   "ignored"          — no action taken (implicit negative signal)

    timestamp: datetime = field(default_factory=datetime.utcnow)
    notes: Optional[str] = None

    # Scores at recommendation time (for accuracy tracking)
    content_score: Optional[float] = None
    collaborative_score: Optional[float] = None
    final_score: Optional[float] = None

    @property
    def is_positive(self) -> bool:
        return self.action in ("played", "liked", "added_to_wishlist")

    @property
    def is_negative(self) -> bool:
        return self.action in ("disliked", "dismissed")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d["timestamp"] is not None and hasattr(d["timestamp"], "isoformat"):
            d["timestamp"] = d["timestamp"].isoformat()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecommendationFeedback":
        filtered = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if filtered.get("timestamp") and isinstance(filtered["timestamp"], str):
            try:
                from dateutil.parser import parse as parse_dt
                filtered["timestamp"] = parse_dt(filtered["timestamp"])
            except Exception:
                filtered["timestamp"] = datetime.utcnow()
        return cls(**filtered)


@dataclass
class UserProfile:
    """
    Complete user profile including preferences, history, and settings.

    Preference weights (genre_weights, mechanic_weights, etc.) are
    automatically updated by the FeedbackEngine as the user interacts
    with recommendations and the library.
    """

    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    username: str = "default"

    # ------------------------------------------------------------------ #
    # Learned preference weights — values in [0, 1], higher = stronger   #
    # preference.  Keys are the lowercase, underscore-normalised labels.  #
    # ------------------------------------------------------------------ #
    genre_weights: Dict[str, float] = field(default_factory=dict)
    developer_weights: Dict[str, float] = field(default_factory=dict)
    mechanic_weights: Dict[str, float] = field(default_factory=dict)
    theme_weights: Dict[str, float] = field(default_factory=dict)
    tag_weights: Dict[str, float] = field(default_factory=dict)
    platform_weights: Dict[str, float] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Wishlist — list of game IDs                                         #
    # ------------------------------------------------------------------ #
    wishlist: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Explicit ratings — game_id -> score in [0, 10]                     #
    # ------------------------------------------------------------------ #
    ratings: Dict[str, float] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Current contextual state                                            #
    # ------------------------------------------------------------------ #
    current_mood: Optional[str] = None           # Mood enum value or None

    # ------------------------------------------------------------------ #
    # Recommendation settings (override global config per-user)          #
    # ------------------------------------------------------------------ #
    recommendation_settings: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Metadata                                                            #
    # ------------------------------------------------------------------ #
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # ------------------------------------------------------------------ #
    # Derived helpers                                                     #
    # ------------------------------------------------------------------ #
    def get_top_genres(self, n: int = 5) -> List[str]:
        """Return the n most-preferred genre names."""
        return sorted(self.genre_weights, key=self.genre_weights.get, reverse=True)[:n]  # type: ignore[arg-type]

    def get_top_mechanics(self, n: int = 5) -> List[str]:
        return sorted(self.mechanic_weights, key=self.mechanic_weights.get, reverse=True)[:n]  # type: ignore[arg-type]

    def set_mood(self, mood: Optional[str]) -> None:
        """Set current mood (accepts Mood enum value or string)."""
        if mood is None:
            self.current_mood = None
        else:
            if isinstance(mood, Mood):
                self.current_mood = mood.value
            else:
                self.current_mood = str(mood)
        self.updated_at = datetime.utcnow()

    def rate_game(self, game_id: str, score: float) -> None:
        """Record an explicit rating for a game."""
        if not 0.0 <= score <= 10.0:
            raise ValueError(f"Rating must be between 0 and 10, got {score}")
        self.ratings[game_id] = score
        self.updated_at = datetime.utcnow()

    def add_to_wishlist(self, game_id: str) -> None:
        if game_id not in self.wishlist:
            self.wishlist.append(game_id)
            self.updated_at = datetime.utcnow()

    def remove_from_wishlist(self, game_id: str) -> None:
        if game_id in self.wishlist:
            self.wishlist.remove(game_id)
            self.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for key in ("created_at", "updated_at"):
            if d[key] is not None and hasattr(d[key], "isoformat"):
                d[key] = d[key].isoformat()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserProfile":
        filtered = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        for key in ("created_at", "updated_at"):
            if filtered.get(key) and isinstance(filtered[key], str):
                try:
                    from dateutil.parser import parse as parse_dt
                    filtered[key] = parse_dt(filtered[key])
                except Exception:
                    filtered[key] = datetime.utcnow()
        return cls(**filtered)

    def __repr__(self) -> str:
        return f"<UserProfile id={self.id[:8]}… username={self.username!r}>"
