"""Configuration management for Playnite Python service."""
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Server Configuration
    host: str = "127.0.0.1"
    port: int = 5555
    reload: bool = False

    # Database Configuration
    database_url: str = "sqlite:///./data/playnite_python.db"

    # Capture Configuration
    capture_base_path: Optional[Path] = None
    default_screenshot_hotkey: str = "f8"
    default_video_hotkey: str = "f9"
    default_instant_replay_seconds: int = 30
    default_video_quality: str = "high"
    default_capture_backend: str = "direct"

    # Recommendation Configuration
    recommendation_limit_default: int = 10
    min_playtime_for_preference_seconds: int = 3600
    similarity_threshold: float = 0.3

    # Logging Configuration
    log_level: str = "INFO"
    log_file: Optional[Path] = None

    # Cache Configuration
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600

    # Security Configuration
    api_key: str = "dev-key-change-in-production"
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    enable_api_key_auth: bool = False  # Disabled by default for dev

    # Rate Limiting
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000
    rate_limit_enabled: bool = True

    # Monitoring
    enable_metrics: bool = True
    metrics_port: int = 9090

    # CORS
    allowed_origins: str = "http://localhost:*,http://127.0.0.1:*"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Set default capture path if not specified
        if self.capture_base_path is None:
            self.capture_base_path = Path.home() / "Playnite" / "Captures"

        # Ensure capture directory exists
        self.capture_base_path.mkdir(parents=True, exist_ok=True)

        # Set default log file if not specified
        if self.log_file is None:
            log_dir = Path("./data/logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            self.log_file = log_dir / "playnite_python.log"


# Global settings instance
settings = Settings()
