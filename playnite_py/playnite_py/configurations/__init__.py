"""
Platform configuration module for Playnite-Py.

This module provides comprehensive platform-specific game configuration
management including:
- Platform detection and hardware profiling
- Configuration templates and presets
- Launch argument management
- Environment variable configuration
- Compatibility layer settings (Wine/Proton)
- Display and audio configuration
- Pre/post launch scripts
- Configuration validation and fallback

Example:
    >>> from playnite_py.configurations import ConfigurationManager
    >>> manager = ConfigurationManager(db)
    >>> config = manager.create_configuration(game_id, "Desktop", preset="quality")
    >>> manager.apply_configuration(game_id, "Desktop")
"""

from playnite_py.configurations.manager import ConfigurationManager
from playnite_py.configurations.detection import (
    PlatformDetector,
    HardwareProfile,
    detect_current_platform,
)
from playnite_py.configurations.templates import (
    ConfigTemplateManager,
    get_builtin_config_templates,
)
from playnite_py.configurations.launcher import GameLauncher, LaunchResult
from playnite_py.configurations.compatibility import CompatibilityManager

__all__ = [
    "ConfigurationManager",
    "PlatformDetector",
    "HardwareProfile",
    "detect_current_platform",
    "ConfigTemplateManager",
    "get_builtin_config_templates",
    "GameLauncher",
    "LaunchResult",
    "CompatibilityManager",
]
