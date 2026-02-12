"""
Command-line interface module for Playnite-Py.

This module provides a comprehensive CLI for managing game library
profiles and platform-specific configurations.

Example:
    $ playnite profile create "Gaming"
    $ playnite profile switch "Gaming"
    $ playnite config create --game "Cyberpunk 2077" --preset quality
"""

from playnite_py.cli.main import cli
from playnite_py.cli.profile_commands import profile_cli
from playnite_py.cli.config_commands import config_cli

__all__ = [
    "cli",
    "profile_cli",
    "config_cli",
]
