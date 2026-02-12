"""
Application settings management for Playnite-Py.

This module provides configuration file support with a layered settings
approach: defaults < config file < environment variables < CLI arguments.

Example:
    >>> settings = AppSettings.load()
    >>> print(settings.data_dir)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # Python < 3.11

import logging

logger = logging.getLogger(__name__)


def get_default_data_dir() -> Path:
    """Get the platform-specific default data directory."""
    import platform as plat
    system = plat.system()

    if system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif system == "Darwin":
        base = Path.home() / "Library/Application Support"
    else:  # Linux and others
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))

    return base / "playnite-py"


def get_config_file_path() -> Path:
    """Get the configuration file path."""
    import platform as plat
    system = plat.system()

    if system == "Windows":
        config_home = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif system == "Darwin":
        config_home = Path.home() / "Library/Preferences"
    else:  # Linux and others
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

    return config_home / "playnite-py" / "config.toml"


@dataclass
class LoggingSettings:
    """Logging configuration."""
    level: str = "INFO"
    structured: bool = False
    log_file: Optional[Path] = None


@dataclass
class DatabaseSettings:
    """Database configuration."""
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    echo: bool = False


@dataclass
class LauncherSettings:
    """Launcher configuration."""
    default_timeout: int = 0  # 0 = no timeout
    verify_paths: bool = True
    auto_rollback_display: bool = True


@dataclass
class AppSettings:
    """
    Application settings loaded from config file and environment.

    Settings are loaded in this priority order (later overrides earlier):
    1. Default values
    2. Config file (config.toml)
    3. Environment variables (PLAYNITE_*)
    4. CLI arguments (handled externally)

    Attributes:
        data_dir: Root data directory
        logging: Logging configuration
        database: Database configuration
        launcher: Launcher configuration
    """
    data_dir: Path = field(default_factory=get_default_data_dir)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    launcher: LauncherSettings = field(default_factory=LauncherSettings)

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "AppSettings":
        """
        Load settings from config file and environment.

        Args:
            config_path: Optional custom config file path

        Returns:
            Loaded settings
        """
        settings = cls()

        # Load from config file
        if config_path is None:
            config_path = get_config_file_path()

        if config_path.exists():
            settings = cls._load_from_file(config_path, settings)
            logger.debug(f"Loaded settings from {config_path}")

        # Override from environment
        settings = cls._load_from_env(settings)

        return settings

    @classmethod
    def _load_from_file(cls, path: Path, settings: "AppSettings") -> "AppSettings":
        """Load settings from TOML file."""
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)

            # Apply data_dir
            if "data_dir" in data:
                settings.data_dir = Path(data["data_dir"]).expanduser()

            # Apply logging settings
            if "logging" in data:
                log_data = data["logging"]
                if "level" in log_data:
                    settings.logging.level = log_data["level"]
                if "structured" in log_data:
                    settings.logging.structured = log_data["structured"]
                if "log_file" in log_data:
                    settings.logging.log_file = Path(log_data["log_file"]).expanduser()

            # Apply database settings
            if "database" in data:
                db_data = data["database"]
                if "pool_size" in db_data:
                    settings.database.pool_size = db_data["pool_size"]
                if "max_overflow" in db_data:
                    settings.database.max_overflow = db_data["max_overflow"]
                if "pool_timeout" in db_data:
                    settings.database.pool_timeout = db_data["pool_timeout"]
                if "echo" in db_data:
                    settings.database.echo = db_data["echo"]

            # Apply launcher settings
            if "launcher" in data:
                launch_data = data["launcher"]
                if "default_timeout" in launch_data:
                    settings.launcher.default_timeout = launch_data["default_timeout"]
                if "verify_paths" in launch_data:
                    settings.launcher.verify_paths = launch_data["verify_paths"]
                if "auto_rollback_display" in launch_data:
                    settings.launcher.auto_rollback_display = launch_data["auto_rollback_display"]

        except (OSError, tomllib.TOMLDecodeError) as e:
            logger.warning(f"Could not load config from {path}: {e}")

        return settings

    @classmethod
    def _load_from_env(cls, settings: "AppSettings") -> "AppSettings":
        """Override settings from environment variables."""
        # PLAYNITE_DATA_DIR
        if data_dir := os.environ.get("PLAYNITE_DATA_DIR"):
            settings.data_dir = Path(data_dir).expanduser()

        # PLAYNITE_LOG_LEVEL
        if log_level := os.environ.get("PLAYNITE_LOG_LEVEL"):
            settings.logging.level = log_level.upper()

        # PLAYNITE_LOG_STRUCTURED
        if log_structured := os.environ.get("PLAYNITE_LOG_STRUCTURED"):
            settings.logging.structured = log_structured.lower() in ("1", "true", "yes")

        # PLAYNITE_LOG_FILE
        if log_file := os.environ.get("PLAYNITE_LOG_FILE"):
            settings.logging.log_file = Path(log_file).expanduser()

        # PLAYNITE_DB_POOL_SIZE
        if pool_size := os.environ.get("PLAYNITE_DB_POOL_SIZE"):
            try:
                settings.database.pool_size = int(pool_size)
            except ValueError:
                pass

        return settings

    def save(self, path: Optional[Path] = None) -> None:
        """
        Save settings to a config file.

        Args:
            path: Optional custom config file path
        """
        if path is None:
            path = get_config_file_path()

        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "data_dir": str(self.data_dir),
            "logging": {
                "level": self.logging.level,
                "structured": self.logging.structured,
            },
            "database": {
                "pool_size": self.database.pool_size,
                "max_overflow": self.database.max_overflow,
                "pool_timeout": self.database.pool_timeout,
                "echo": self.database.echo,
            },
            "launcher": {
                "default_timeout": self.launcher.default_timeout,
                "verify_paths": self.launcher.verify_paths,
                "auto_rollback_display": self.launcher.auto_rollback_display,
            },
        }

        if self.logging.log_file:
            data["logging"]["log_file"] = str(self.logging.log_file)

        # Write as TOML
        with open(path, "w") as f:
            f.write("# Playnite-Py Configuration\n")
            f.write("# See documentation for available options\n\n")
            _write_toml(data, f)

        logger.info(f"Saved settings to {path}")

    def to_dict(self) -> dict[str, Any]:
        """Convert settings to dictionary."""
        return {
            "data_dir": str(self.data_dir),
            "logging": {
                "level": self.logging.level,
                "structured": self.logging.structured,
                "log_file": str(self.logging.log_file) if self.logging.log_file else None,
            },
            "database": {
                "pool_size": self.database.pool_size,
                "max_overflow": self.database.max_overflow,
                "pool_timeout": self.database.pool_timeout,
                "echo": self.database.echo,
            },
            "launcher": {
                "default_timeout": self.launcher.default_timeout,
                "verify_paths": self.launcher.verify_paths,
                "auto_rollback_display": self.launcher.auto_rollback_display,
            },
        }


def _write_toml(data: dict, f) -> None:
    """Write dictionary as TOML format."""
    for key, value in data.items():
        if isinstance(value, dict):
            f.write(f"\n[{key}]\n")
            for k, v in value.items():
                _write_toml_value(k, v, f)
        else:
            _write_toml_value(key, value, f)


def _write_toml_value(key: str, value: Any, f) -> None:
    """Write a single TOML key-value pair."""
    if value is None:
        return
    if isinstance(value, bool):
        f.write(f"{key} = {'true' if value else 'false'}\n")
    elif isinstance(value, int):
        f.write(f"{key} = {value}\n")
    elif isinstance(value, str):
        # Escape backslashes and quotes
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        f.write(f'{key} = "{escaped}"\n')
    else:
        f.write(f'{key} = "{value}"\n')
