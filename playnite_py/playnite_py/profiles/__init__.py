"""
Profile management module for Playnite-Py.

This module provides comprehensive multi-profile management including:
- Profile creation, switching, and deletion
- Profile templates and inheritance
- Selective data sharing between profiles
- Profile security (password protection)
- Profile import/export for backup and migration
- Profile locking for concurrent access prevention

Example:
    >>> from playnite_py.profiles import ProfileManager
    >>> manager = ProfileManager()
    >>> profile = manager.create_profile("Gaming", template="default")
    >>> manager.switch_profile("Gaming")
"""

from playnite_py.profiles.manager import ProfileManager
from playnite_py.profiles.templates import (
    ProfileTemplateManager,
    get_builtin_templates,
)
from playnite_py.profiles.inheritance import ProfileInheritanceResolver
from playnite_py.profiles.security import ProfileSecurityManager
from playnite_py.profiles.sharing import ProfileSharingManager
from playnite_py.profiles.locking import ProfileLock, ProfileLockManager
from playnite_py.profiles.export import ProfileExporter, ProfileImporter

__all__ = [
    "ProfileManager",
    "ProfileTemplateManager",
    "get_builtin_templates",
    "ProfileInheritanceResolver",
    "ProfileSecurityManager",
    "ProfileSharingManager",
    "ProfileLock",
    "ProfileLockManager",
    "ProfileExporter",
    "ProfileImporter",
]
