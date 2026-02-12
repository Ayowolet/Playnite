"""
Platform utilities for Playnite-Py.

This module provides cross-platform utility functions.
"""

import platform
from pathlib import Path

from platformdirs import user_data_dir


def get_platform_name() -> str:
    """
    Get the current platform name.

    Returns:
        Platform name (Windows, Linux, Darwin)
    """
    return platform.system()


def is_windows() -> bool:
    """Check if running on Windows."""
    return platform.system() == "Windows"


def is_linux() -> bool:
    """Check if running on Linux."""
    return platform.system() == "Linux"


def is_macos() -> bool:
    """Check if running on macOS."""
    return platform.system() == "Darwin"


def get_app_data_dir(app_name: str = "PlaynitePy") -> Path:
    """
    Get the application data directory.

    Args:
        app_name: Application name

    Returns:
        Path to the application data directory
    """
    return Path(user_data_dir(app_name))
