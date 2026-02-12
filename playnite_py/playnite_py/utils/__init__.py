"""
Utility functions for Playnite-Py.

This module provides common utility functions used throughout
the application.
"""

from playnite_py.utils.logging import setup_logging, get_logger
from playnite_py.utils.platform import (
    get_app_data_dir,
    get_platform_name,
    is_windows,
    is_linux,
    is_macos,
)

__all__ = [
    "setup_logging",
    "get_logger",
    "get_app_data_dir",
    "get_platform_name",
    "is_windows",
    "is_linux",
    "is_macos",
]
