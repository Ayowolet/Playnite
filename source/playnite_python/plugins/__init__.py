"""
Playnite Python plugin system.

Import the classes you need::

    from playnite_python.plugins import Plugin, LibraryPlugin, MetadataPlugin, PluginManager
"""

from .base import (
    Plugin,
    PluginProperties,
    MainMenuItem,
    GameMenuItem,
    GetMainMenuItemsArgs,
    GetGameMenuItemsArgs,
)
from .library import (
    LibraryPlugin,
    LibraryPluginProperties,
    LibraryGetGamesArgs,
    GameMetadata,
)
from .metadata import (
    MetadataPlugin,
    MetadataField,
    OnDemandMetadataProvider,
    MetadataRequestOptions,
    GetMetadataFieldArgs,
)
from .manager import PluginManager

__all__ = [
    "Plugin",
    "PluginProperties",
    "MainMenuItem",
    "GameMenuItem",
    "GetMainMenuItemsArgs",
    "GetGameMenuItemsArgs",
    "LibraryPlugin",
    "LibraryPluginProperties",
    "LibraryGetGamesArgs",
    "GameMetadata",
    "MetadataPlugin",
    "MetadataField",
    "OnDemandMetadataProvider",
    "MetadataRequestOptions",
    "GetMetadataFieldArgs",
    "PluginManager",
]
