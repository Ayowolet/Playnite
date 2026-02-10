"""Configuration management for Python Playnite."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Fields that must never be persisted to disk in plaintext.
# They are supplied exclusively via environment variables at runtime.
_SENSITIVE_FIELDS: dict[str, set[str]] = {
    "steam": {"api_key"},
    "xbox": {"api_key"},
    "psn": {"npsso_token"},
    "gog": {"client_secret", "access_token", "refresh_token"},
}


def get_data_dir() -> Path:
    """Return platform-appropriate application data directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
        return base / "Playnite"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Playnite"
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(xdg) / "playnite"


DEFAULT_DATA_DIR = get_data_dir()


@dataclass
class SteamConfig:
    api_key: str = ""
    steam_id: str = ""
    enabled: bool = False


@dataclass
class XboxConfig:
    api_key: str = ""
    xuid: str = ""
    enabled: bool = False


@dataclass
class PSNConfig:
    npsso_token: str = ""
    account_id: str = ""
    enabled: bool = False


@dataclass
class GOGConfig:
    client_id: str = ""
    client_secret: str = ""
    access_token: str = ""
    refresh_token: str = ""
    user_id: str = ""
    enabled: bool = False


@dataclass
class BackupConfig:
    default_destination: str = ""
    auto_backup_enabled: bool = False
    auto_backup_schedule: str = "0 2 * * *"  # Daily at 02:00
    max_backups: int = 10
    retention_days: int = 30
    encrypt_by_default: bool = False
    compress: bool = True


@dataclass
class CloudStorageConfig:
    gdrive_sync_path: str = ""     # e.g. ~/Google Drive/My Drive
    dropbox_sync_path: str = ""    # e.g. ~/Dropbox
    onedrive_sync_path: str = ""   # e.g. ~/OneDrive
    subfolder: str = "playnite_backups"


@dataclass
class AchievementConfig:
    auto_sync_enabled: bool = False
    auto_sync_interval_hours: int = 6
    # Global completion % below which an achievement is considered rare
    rare_threshold: float = 10.0
    notify_on_unlock: bool = True


@dataclass
class Config:
    data_dir: str = str(DEFAULT_DATA_DIR)
    database_path: str = ""
    steam: SteamConfig = field(default_factory=SteamConfig)
    xbox: XboxConfig = field(default_factory=XboxConfig)
    psn: PSNConfig = field(default_factory=PSNConfig)
    gog: GOGConfig = field(default_factory=GOGConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    cloud: CloudStorageConfig = field(default_factory=CloudStorageConfig)
    achievements: AchievementConfig = field(default_factory=AchievementConfig)

    def __post_init__(self) -> None:
        if not self.database_path:
            self.database_path = str(Path(self.data_dir) / "playnite.db")

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, config_path: Path | None = None) -> Config:
        """Load config from *config_path*, applying env-var overrides."""
        if config_path is None:
            config_path = Path(DEFAULT_DATA_DIR) / "config.json"

        config = cls()
        if config_path.exists():
            with open(config_path) as fh:
                data = json.load(fh)
            config._update_from_dict(data)

        config._apply_env_overrides()
        return config

    def save(self, config_path: Path | None = None) -> None:
        """Persist config to *config_path*.

        Sensitive credential fields (API keys, tokens, secrets) are **never**
        written to the JSON file.  They must be supplied via environment
        variables at runtime (see _apply_env_overrides).
        """
        if config_path is None:
            config_path = Path(self.data_dir) / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        data = asdict(self)
        # Strip sensitive fields before writing to disk
        for section, fields in _SENSITIVE_FIELDS.items():
            if section in data and isinstance(data[section], dict):
                for field_name in fields:
                    if field_name in data[section]:
                        data[section][field_name] = ""

        with open(config_path, "w") as fh:
            json.dump(data, fh, indent=2)

    def ensure_dirs(self) -> None:
        """Create all required application directories."""
        for sub in ("backups", "themes", "plugins", "configs", "controller_mappings"):
            Path(self.data_dir, sub).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_from_dict(self, data: dict) -> None:
        for key, value in data.items():
            if not hasattr(self, key):
                continue
            attr = getattr(self, key)
            if hasattr(attr, "__dataclass_fields__") and isinstance(value, dict):
                for subkey, subval in value.items():
                    if hasattr(attr, subkey):
                        setattr(attr, subkey, subval)
            else:
                setattr(self, key, value)

    def _apply_env_overrides(self) -> None:
        mapping = {
            "STEAM_API_KEY": ("steam", "api_key"),
            "STEAM_ID": ("steam", "steam_id"),
            "XBOX_API_KEY": ("xbox", "api_key"),
            "XBOX_XUID": ("xbox", "xuid"),
            "PSN_NPSSO": ("psn", "npsso_token"),
            "GOG_CLIENT_ID": ("gog", "client_id"),
            "GOG_CLIENT_SECRET": ("gog", "client_secret"),
            "PLAYNITE_DATA_DIR": (None, "data_dir"),
        }
        for env_var, (section, attr) in mapping.items():
            value = os.environ.get(env_var)
            if value:
                if section:
                    setattr(getattr(self, section), attr, value)
                else:
                    setattr(self, attr, value)
