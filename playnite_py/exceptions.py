"""
Custom exception hierarchy for playnite_py.

All public exceptions inherit from PlayniteError so callers can catch
the entire family with a single ``except PlayniteError``.
"""

from __future__ import annotations


class PlayniteError(Exception):
    """Base exception for all playnite_py errors."""


class CaptureError(PlayniteError):
    """Raised when a screen capture operation fails."""


class RecordingError(PlayniteError):
    """Raised when a video recording operation fails."""


class BufferError(PlayniteError):
    """Raised when the replay buffer encounters an error."""


class ConfigurationError(PlayniteError):
    """Raised when configuration values are invalid."""


class DatabaseError(PlayniteError):
    """Raised when a database operation fails unexpectedly."""


class MediaEditError(PlayniteError):
    """Raised when a media editing operation (trim, crop, etc.) fails."""


class StorageError(PlayniteError):
    """Raised when a storage or file-system operation fails."""
