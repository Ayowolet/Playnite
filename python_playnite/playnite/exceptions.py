"""Shared exception hierarchy for python-playnite.

All domain exceptions inherit from PlayniteError so callers can catch any
library error with a single ``except PlayniteError`` clause.
"""

from __future__ import annotations


class PlayniteError(Exception):
    """Base class for all python-playnite exceptions."""


class BackupError(PlayniteError):
    """Raised on backup operation failures."""


class CompressionError(PlayniteError):
    """Raised when compression or decompression fails."""


class EncryptionError(PlayniteError):
    """Raised on encryption/decryption failures."""


class VerificationError(PlayniteError):
    """Raised when a backup fails verification."""


class DatabaseError(PlayniteError):
    """Raised on database operation failures."""


class AchievementError(PlayniteError):
    """Raised on achievement tracking failures."""


class ConfigError(PlayniteError):
    """Raised on configuration errors."""
