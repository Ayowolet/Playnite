"""
Application-wide configuration, paths, and defaults.
All settings can be overridden via a JSON config file located at
``{data_dir}/config.json`` or passed programmatically.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)


def _default_data_dir() -> Path:
    """Return platform-appropriate application data directory."""
    home = Path.home()
    if os.name == "nt":  # Windows
        base = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    elif os.uname().sysname == "Darwin":  # macOS
        base = home / "Library" / "Application Support"
    else:  # Linux / BSD
        base = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    return base / "PlaynitePy"


@dataclass
class CaptureConfig:
    """Screenshot and video capture settings."""
    # Screenshot
    screenshot_format: str = "png"          # png | jpeg | webp
    screenshot_quality: int = 95            # JPEG quality 1-100
    screenshot_hotkey: str = "f12"

    # Video recording
    video_codec: str = "libx264"
    video_crf: int = 23                     # Constant Rate Factor 0-51 (lower=better)
    video_fps: int = 30
    video_resolution: Optional[str] = None  # None = native, or "1920x1080"
    video_audio: bool = True
    video_audio_codec: str = "aac"
    record_hotkey: str = "f9"

    # Instant replay buffer
    buffer_duration_seconds: int = 60
    save_replay_hotkey: str = "f10"

    # Storage
    captures_dir: Optional[str] = None      # None = {data_dir}/captures
    max_storage_gb: float = 50.0
    auto_cleanup_days: int = 90             # Delete captures older than N days
    cleanup_enabled: bool = True

    # Overlays
    show_overlay: bool = False
    overlay_opacity: float = 0.8


@dataclass
class RecommendationConfig:
    """Recommendation engine settings."""
    # Scoring weights (should sum to ~1.0)
    content_weight: float = 0.60
    collaborative_weight: float = 0.25
    temporal_weight: float = 0.10
    popularity_weight: float = 0.05

    # Filtering
    min_score_threshold: float = 0.05
    max_recommendations: int = 20
    exclude_played: bool = True
    exclude_hidden: bool = True

    # Learning
    feedback_learning_rate: float = 0.1
    min_feedback_count: int = 5             # feedback needed before adjusting weights

    # Cold-start
    cold_start_strategy: str = "popular"    # popular | genre_diverse | random

    # Export
    history_export_dir: Optional[str] = None  # None = {data_dir}/recommendation_history


@dataclass
class AppConfig:
    """Top-level application configuration."""
    # Identity
    default_profile_id: Optional[str] = None

    # Paths
    data_dir: str = field(default_factory=lambda: str(_default_data_dir()))

    # Sub-configs
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    recommendations: RecommendationConfig = field(default_factory=RecommendationConfig)

    # CLI
    default_output_format: str = "table"    # table | json | plain

    # Misc
    log_level: str = "INFO"
    check_game_detection_interval: float = 5.0  # seconds between process scans

    @property
    def database_path(self) -> Path:
        return Path(self.data_dir) / "library.db"

    @property
    def captures_dir(self) -> Path:
        override = self.capture.captures_dir
        return Path(override) if override else Path(self.data_dir) / "captures"

    @property
    def history_dir(self) -> Path:
        override = self.recommendations.history_export_dir
        return Path(override) if override else Path(self.data_dir) / "recommendation_history"

    def ensure_dirs(self) -> None:
        """Create all required directories."""
        for d in [Path(self.data_dir), self.captures_dir, self.history_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AppConfig":
        """Load config from JSON file, falling back to defaults."""
        if path is None:
            path = _default_data_dir() / "config.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                capture_data = data.pop("capture", {})
                rec_data = data.pop("recommendations", {})
                cfg = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
                cfg.capture = CaptureConfig(**{k: v for k, v in capture_data.items() if k in CaptureConfig.__dataclass_fields__})
                cfg.recommendations = RecommendationConfig(**{k: v for k, v in rec_data.items() if k in RecommendationConfig.__dataclass_fields__})
                try:
                    cfg.validate()
                except ValueError as exc:
                    log.warning("Config file %s has invalid values (%s); falling back to defaults", path, exc)
                    return cls()
                return cfg
            except Exception:
                pass
        return cls()

    def save(self, path: Optional[Path] = None) -> None:
        """Persist config to JSON."""
        if path is None:
            path = Path(self.data_dir) / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, default=str), encoding="utf-8")

    def validate(self) -> None:
        """Validate all config values; raises ValueError for out-of-range settings."""
        cap = self.capture
        rec = self.recommendations

        if not (1 <= cap.screenshot_quality <= 100):
            raise ValueError(f"screenshot_quality must be 1–100, got {cap.screenshot_quality}")
        if not (0 <= cap.video_crf <= 51):
            raise ValueError(f"video_crf must be 0–51, got {cap.video_crf}")
        if cap.video_fps <= 0:
            raise ValueError(f"video_fps must be positive, got {cap.video_fps}")
        if cap.buffer_duration_seconds <= 0:
            raise ValueError(
                f"buffer_duration_seconds must be positive, got {cap.buffer_duration_seconds}"
            )
        if cap.max_storage_gb <= 0:
            raise ValueError(f"max_storage_gb must be positive, got {cap.max_storage_gb}")
        if not (0.0 < cap.overlay_opacity <= 1.0):
            raise ValueError(f"overlay_opacity must be 0.1–1.0, got {cap.overlay_opacity}")

        total_weight = (
            rec.content_weight
            + rec.collaborative_weight
            + rec.temporal_weight
            + rec.popularity_weight
        )
        if not (0.9 <= total_weight <= 1.1):
            raise ValueError(
                f"Recommendation weights must sum to ~1.0, got {total_weight:.3f}"
            )
        if not (0.0 <= rec.min_score_threshold < 1.0):
            raise ValueError(
                f"min_score_threshold must be in [0, 1), got {rec.min_score_threshold}"
            )
        if rec.max_recommendations <= 0:
            raise ValueError(
                f"max_recommendations must be positive, got {rec.max_recommendations}"
            )

        valid_formats = {"table", "json", "plain"}
        if self.default_output_format not in valid_formats:
            raise ValueError(
                f"default_output_format must be one of {valid_formats}, "
                f"got {self.default_output_format!r}"
            )
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in valid_levels:
            raise ValueError(
                f"log_level must be one of {valid_levels}, got {self.log_level!r}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
