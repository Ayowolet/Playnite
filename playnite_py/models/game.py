"""
Core Game and Platform data models.

These are plain dataclasses that map 1-to-1 with the database schema and
are used as the shared currency throughout the library, recommendation
engine, and capture system.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Platform:
    """A gaming platform (PC, PlayStation, Nintendo Switch, etc.)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    specification_id: Optional[str] = None  # e.g. "sony_playstation5"
    icon: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Platform":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Game:
    """
    Full game record.  All list fields accept plain strings so the model
    stays serialisable without nested objects.
    """

    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    sort_name: Optional[str] = None         # override for sorting (e.g. "Witcher 3, The")

    # Library classification
    platforms: List[str] = field(default_factory=list)
    genres: List[str] = field(default_factory=list)
    developers: List[str] = field(default_factory=list)
    publishers: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    features: List[str] = field(default_factory=list)     # VR, co-op, achievements…
    series: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    release_year: Optional[int] = None

    # Extended recommendation attributes
    themes: List[str] = field(default_factory=list)        # war, sci-fi, fantasy…
    mechanics: List[str] = field(default_factory=list)     # turn-based, first-person…
    art_style: Optional[str] = None                        # pixel, realistic, cel-shaded…

    # Ownership / status
    is_installed: bool = False
    is_owned: bool = True
    in_wishlist: bool = False
    source: Optional[str] = None            # "Steam" | "GOG" | "Epic" | "Manual" …
    hidden: bool = False
    favorite: bool = False

    # Play statistics
    play_count: int = 0
    playtime_seconds: int = 0
    last_played: Optional[datetime] = None
    completed: bool = False
    completion_status: Optional[str] = None  # "completed" | "playing" | "backlog" …

    # Session / difficulty metadata
    completion_hours: Optional[float] = None          # main-story completion time in hours
    typical_session_minutes: Optional[int] = None     # typical single-session length in minutes
    difficulty: Optional[str] = None                  # "easy" | "medium" | "hard" | "very hard"
    multiplayer_support: bool = False                 # True if the game has any multiplayer mode
    vr_compatible: bool = False                       # True if the game supports VR headsets

    # Scores (0-100)
    user_score: Optional[float] = None
    critic_score: Optional[float] = None
    community_score: Optional[float] = None

    # Content
    description: Optional[str] = None
    notes: Optional[str] = None

    # Media paths (relative to data_dir / "files")
    cover_image: Optional[str] = None
    background_image: Optional[str] = None
    icon: Optional[str] = None

    # Library metadata
    added: Optional[datetime] = field(default_factory=datetime.utcnow)
    modified: Optional[datetime] = field(default_factory=datetime.utcnow)

    # Capture / media
    capture_directory: Optional[str] = None  # relative path under captures_dir

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @property
    def display_name(self) -> str:
        return self.name

    @property
    def playtime_hours(self) -> float:
        return self.playtime_seconds / 3600

    @property
    def is_played(self) -> bool:
        return self.play_count > 0 or self.playtime_seconds > 0

    def feature_tokens(self) -> List[str]:
        """
        Return a flat list of strings representing all content attributes.
        Used by the recommendation engine to build TF-IDF feature vectors.
        """
        tokens: List[str] = []
        tokens.extend(g.lower().replace(" ", "_") for g in self.genres)
        tokens.extend(t.lower().replace(" ", "_") for t in self.themes)
        tokens.extend(m.lower().replace(" ", "_") for m in self.mechanics)
        tokens.extend(f.lower().replace(" ", "_") for f in self.features)
        tokens.extend(tg.lower().replace(" ", "_") for tg in self.tags)
        tokens.extend(d.lower().replace(" ", "_") for d in self.developers)
        if self.art_style:
            tokens.append(f"art_{self.art_style.lower().replace(' ', '_')}")
        if self.series:
            tokens.append(f"series_{self.series.lower().replace(' ', '_')}")
        for platform in self.platforms:
            tokens.append(f"platform_{platform.lower().replace(' ', '_')}")
        if self.typical_session_minutes is not None:
            if self.typical_session_minutes < 60:
                tokens.append("quick_session")
            elif self.typical_session_minutes >= 180:
                tokens.append("long_session")
        if self.difficulty:
            tokens.append(self.difficulty.lower().replace(" ", "_"))
        if self.multiplayer_support:
            tokens.append("multiplayer_support")
        if self.vr_compatible:
            tokens.append("vr_compatible")
        return tokens

    def feature_string(self) -> str:
        """Space-joined feature token string for TF-IDF vectorisation."""
        return " ".join(self.feature_tokens())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Convert datetimes to ISO strings for JSON serialisation
        for key in ("last_played", "added", "modified"):
            if d[key] is not None:
                d[key] = d[key].isoformat() if hasattr(d[key], "isoformat") else str(d[key])
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Game":
        filtered = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        for key in ("last_played", "added", "modified"):
            if filtered.get(key) and isinstance(filtered[key], str):
                try:
                    from dateutil.parser import parse as parse_dt
                    filtered[key] = parse_dt(filtered[key])
                except Exception:
                    filtered[key] = None
        return cls(**filtered)

    def __repr__(self) -> str:
        hours = f"{self.playtime_hours:.1f}h" if self.is_played else "unplayed"
        return f"<Game id={self.id[:8]}… name={self.name!r} playtime={hours}>"
