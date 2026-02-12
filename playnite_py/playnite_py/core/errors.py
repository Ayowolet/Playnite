"""
Structured error codes for Playnite-Py.

Provides error codes for programmatic error handling and
clear error messages for users.

Example:
    >>> from playnite_py.core.errors import ErrorCode, PlayniteError
    >>> raise PlayniteError(ErrorCode.PROFILE_NOT_FOUND, "Profile 'gaming' not found")
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Optional


class ErrorCategory(str, Enum):
    """Error category for grouping related errors."""
    PROFILE = "profile"
    GAME = "game"
    CONFIGURATION = "config"
    LAUNCH = "launch"
    DATABASE = "database"
    COMPATIBILITY = "compat"
    DISPLAY = "display"
    SECURITY = "security"
    SYSTEM = "system"


class ErrorCode(Enum):
    """
    Structured error codes for programmatic handling.

    Error codes are grouped by category:
    - 1xxx: Profile errors
    - 2xxx: Game errors
    - 3xxx: Configuration errors
    - 4xxx: Launch errors
    - 5xxx: Database errors
    - 6xxx: Compatibility layer errors
    - 7xxx: Display errors
    - 8xxx: Security errors
    - 9xxx: System errors
    """
    # Profile errors (1xxx)
    PROFILE_NOT_FOUND = 1001
    PROFILE_ALREADY_EXISTS = 1002
    PROFILE_LOCKED = 1003
    PROFILE_SWITCH_FAILED = 1004
    PROFILE_INVALID_NAME = 1005
    PROFILE_INHERITANCE_CYCLE = 1006
    PROFILE_EXPORT_FAILED = 1007
    PROFILE_IMPORT_FAILED = 1008

    # Game errors (2xxx)
    GAME_NOT_FOUND = 2001
    GAME_ALREADY_EXISTS = 2002
    GAME_INVALID_ACTION = 2003
    GAME_NO_DEFAULT_ACTION = 2004
    GAME_METADATA_FETCH_FAILED = 2005

    # Configuration errors (3xxx)
    CONFIG_NOT_FOUND = 3001
    CONFIG_INVALID = 3002
    CONFIG_TEMPLATE_NOT_FOUND = 3003
    CONFIG_VALIDATION_FAILED = 3004

    # Launch errors (4xxx)
    LAUNCH_PATH_NOT_FOUND = 4001
    LAUNCH_PATH_INVALID = 4002
    LAUNCH_PERMISSION_DENIED = 4003
    LAUNCH_TIMEOUT = 4004
    LAUNCH_SCRIPT_FAILED = 4005
    LAUNCH_URL_INVALID = 4006
    LAUNCH_ARGUMENT_INVALID = 4007

    # Database errors (5xxx)
    DATABASE_CONNECTION_FAILED = 5001
    DATABASE_MIGRATION_FAILED = 5002
    DATABASE_QUERY_FAILED = 5003
    DATABASE_INTEGRITY_ERROR = 5004

    # Compatibility layer errors (6xxx)
    COMPAT_LAYER_NOT_FOUND = 6001
    COMPAT_PREFIX_INVALID = 6002
    COMPAT_ENVIRONMENT_SETUP_FAILED = 6003
    COMPAT_WINE_NOT_FOUND = 6004
    COMPAT_PROTON_NOT_FOUND = 6005

    # Display errors (7xxx)
    DISPLAY_MONITOR_NOT_FOUND = 7001
    DISPLAY_RESOLUTION_INVALID = 7002
    DISPLAY_CHANGE_FAILED = 7003
    DISPLAY_ROLLBACK_FAILED = 7004

    # Security errors (8xxx)
    SECURITY_PASSWORD_INCORRECT = 8001
    SECURITY_PROFILE_LOCKED_OUT = 8002
    SECURITY_SANDBOX_FAILED = 8003
    SECURITY_PATH_TRAVERSAL = 8004
    SECURITY_INJECTION_DETECTED = 8005

    # System errors (9xxx)
    SYSTEM_PLATFORM_UNSUPPORTED = 9001
    SYSTEM_DEPENDENCY_MISSING = 9002
    SYSTEM_PERMISSION_DENIED = 9003
    SYSTEM_IO_ERROR = 9004
    SYSTEM_TIMEOUT = 9005

    @property
    def category(self) -> ErrorCategory:
        """Get the error category."""
        code = self.value
        if 1000 <= code < 2000:
            return ErrorCategory.PROFILE
        elif 2000 <= code < 3000:
            return ErrorCategory.GAME
        elif 3000 <= code < 4000:
            return ErrorCategory.CONFIGURATION
        elif 4000 <= code < 5000:
            return ErrorCategory.LAUNCH
        elif 5000 <= code < 6000:
            return ErrorCategory.DATABASE
        elif 6000 <= code < 7000:
            return ErrorCategory.COMPATIBILITY
        elif 7000 <= code < 8000:
            return ErrorCategory.DISPLAY
        elif 8000 <= code < 9000:
            return ErrorCategory.SECURITY
        else:
            return ErrorCategory.SYSTEM


@dataclass
class ErrorDetail:
    """Detailed error information."""
    code: ErrorCode
    message: str
    details: Optional[dict[str, Any]] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "code": self.code.value,
            "code_name": self.code.name,
            "category": self.code.category.value,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result


class PlayniteError(Exception):
    """
    Base exception for Playnite-Py with structured error codes.

    Provides programmatic error handling through error codes and
    user-friendly error messages.

    Attributes:
        code: Structured error code
        message: Human-readable error message
        details: Optional additional details
        suggestion: Optional suggestion for resolution

    Example:
        >>> try:
        ...     raise PlayniteError(
        ...         ErrorCode.PROFILE_NOT_FOUND,
        ...         "Profile 'gaming' not found",
        ...         suggestion="Create the profile with 'playnite profile create gaming'"
        ...     )
        ... except PlayniteError as e:
        ...     print(f"Error {e.code.value}: {e.message}")
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[dict[str, Any]] = None,
        suggestion: Optional[str] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details
        self.suggestion = suggestion
        super().__init__(self.message)

    @property
    def category(self) -> ErrorCategory:
        """Get the error category."""
        return self.code.category

    def to_error_detail(self) -> ErrorDetail:
        """Convert to ErrorDetail."""
        return ErrorDetail(
            code=self.code,
            message=self.message,
            details=self.details,
            suggestion=self.suggestion,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.to_error_detail().to_dict()


# Convenience exception classes
class ProfileError(PlayniteError):
    """Profile-related errors."""
    pass


class GameError(PlayniteError):
    """Game-related errors."""
    pass


class ConfigurationError(PlayniteError):
    """Configuration-related errors."""
    pass


class LaunchError(PlayniteError):
    """Launch-related errors."""
    pass


class DatabaseError(PlayniteError):
    """Database-related errors."""
    pass


class CompatibilityError(PlayniteError):
    """Compatibility layer errors."""
    pass


class DisplayError(PlayniteError):
    """Display-related errors."""
    pass


class SecurityError(PlayniteError):
    """Security-related errors."""
    pass


class SystemError(PlayniteError):
    """System-related errors."""
    pass
