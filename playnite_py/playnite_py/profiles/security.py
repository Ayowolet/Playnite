"""
Profile security management for Playnite-Py.

This module provides security features for profiles including
password protection, access logging, and lockout management.

Example:
    >>> manager = ProfileSecurityManager()
    >>> manager.set_password(profile, "secret123")
    >>> if manager.verify_password(profile, "secret123"):
    ...     print("Access granted")
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from playnite_py.core.models.profile import Profile, ProfileSecurity

logger = logging.getLogger(__name__)


class ProfileSecurityManager:
    """
    Manager for profile security operations.

    Handles password management, verification, lockout enforcement,
    and security policy configuration.

    Example:
        >>> manager = ProfileSecurityManager()
        >>> manager.set_password(profile, "my_password")
        >>> manager.verify_password(profile, "my_password")
        True
    """

    def __init__(
        self,
        default_iterations: int = 100000,
        default_max_attempts: int = 5,
        default_lockout_minutes: int = 15,
    ) -> None:
        """
        Initialize the security manager.

        Args:
            default_iterations: Default PBKDF2 iterations for password hashing
            default_max_attempts: Default max failed attempts before lockout
            default_lockout_minutes: Default lockout duration in minutes
        """
        self.default_iterations = default_iterations
        self.default_max_attempts = default_max_attempts
        self.default_lockout_minutes = default_lockout_minutes

    def set_password(
        self,
        profile: Profile,
        password: str,
        iterations: Optional[int] = None,
    ) -> None:
        """
        Set a password for a profile.

        Hashes the password using PBKDF2-SHA256 and stores it in the
        profile's security settings.

        Args:
            profile: Profile to set password for
            password: Plaintext password
            iterations: Optional custom iteration count

        Raises:
            ValueError: If password is too short

        Example:
            >>> manager.set_password(profile, "secure_password_123")
        """
        if len(password) < 4:
            raise ValueError("Password must be at least 4 characters")

        profile.security.set_password(
            password,
            iterations=iterations or self.default_iterations
        )
        profile.security.max_failed_attempts = self.default_max_attempts
        profile.security.lockout_duration_minutes = self.default_lockout_minutes

        logger.info(f"Password set for profile: {profile.name}")

    def verify_password(
        self,
        profile: Profile,
        password: str,
        iterations: Optional[int] = None,
    ) -> bool:
        """
        Verify a password for a profile.

        Checks the password against the stored hash and handles
        failed attempt tracking and lockout.

        Args:
            profile: Profile to verify password for
            password: Password to verify
            iterations: Optional custom iteration count

        Returns:
            True if password is correct, False otherwise

        Raises:
            ValueError: If profile has no password set
            PermissionError: If profile is locked due to failed attempts

        Example:
            >>> if manager.verify_password(profile, "my_password"):
            ...     print("Access granted")
        """
        if not profile.security.password_protected:
            raise ValueError(f"Profile '{profile.name}' is not password protected")

        # Check if locked out
        if self.is_locked_out(profile):
            remaining = self.get_lockout_remaining(profile)
            raise PermissionError(
                f"Profile is locked. Try again in {remaining.seconds // 60} minutes."
            )

        is_valid = profile.security.verify_password(
            password,
            iterations=iterations or self.default_iterations
        )

        if not is_valid:
            # Check if we need to apply lockout
            if profile.security.failed_attempts >= profile.security.max_failed_attempts:
                self._apply_lockout(profile)
                logger.warning(
                    f"Profile '{profile.name}' locked after "
                    f"{profile.security.failed_attempts} failed attempts"
                )

        return is_valid

    def clear_password(self, profile: Profile) -> None:
        """
        Remove password protection from a profile.

        Args:
            profile: Profile to remove password from

        Example:
            >>> manager.clear_password(profile)
        """
        profile.security.clear_password()
        logger.info(f"Password removed from profile: {profile.name}")

    def is_password_protected(self, profile: Profile) -> bool:
        """
        Check if a profile is password protected.

        Args:
            profile: Profile to check

        Returns:
            True if password protected, False otherwise
        """
        return profile.security.password_protected

    def is_locked_out(self, profile: Profile) -> bool:
        """
        Check if a profile is currently locked out.

        Args:
            profile: Profile to check

        Returns:
            True if locked out, False otherwise
        """
        return profile.security.is_locked()

    def get_lockout_remaining(self, profile: Profile) -> timedelta:
        """
        Get remaining lockout time.

        Args:
            profile: Profile to check

        Returns:
            Timedelta of remaining lockout time (zero if not locked)
        """
        if not profile.security.locked_until:
            return timedelta(0)

        remaining = profile.security.locked_until - datetime.now()
        if remaining.total_seconds() < 0:
            return timedelta(0)
        return remaining

    def reset_lockout(self, profile: Profile) -> None:
        """
        Reset the lockout for a profile.

        Clears failed attempts and lockout time. Should only be
        used by administrators.

        Args:
            profile: Profile to reset

        Example:
            >>> manager.reset_lockout(profile)
        """
        profile.security.failed_attempts = 0
        profile.security.locked_until = None
        logger.info(f"Lockout reset for profile: {profile.name}")

    def get_failed_attempts(self, profile: Profile) -> int:
        """
        Get the number of failed password attempts.

        Args:
            profile: Profile to check

        Returns:
            Number of failed attempts
        """
        return profile.security.failed_attempts

    def enable_access_logging(self, profile: Profile) -> None:
        """
        Enable access logging for a profile.

        Args:
            profile: Profile to enable logging for
        """
        profile.security.access_log_enabled = True
        logger.info(f"Access logging enabled for profile: {profile.name}")

    def disable_access_logging(self, profile: Profile) -> None:
        """
        Disable access logging for a profile.

        Args:
            profile: Profile to disable logging for
        """
        profile.security.access_log_enabled = False
        logger.info(f"Access logging disabled for profile: {profile.name}")

    def update_security_policy(
        self,
        profile: Profile,
        max_failed_attempts: Optional[int] = None,
        lockout_duration_minutes: Optional[int] = None,
    ) -> None:
        """
        Update the security policy for a profile.

        Args:
            profile: Profile to update
            max_failed_attempts: New max failed attempts (if provided)
            lockout_duration_minutes: New lockout duration (if provided)

        Example:
            >>> manager.update_security_policy(
            ...     profile,
            ...     max_failed_attempts=3,
            ...     lockout_duration_minutes=30
            ... )
        """
        if max_failed_attempts is not None:
            profile.security.max_failed_attempts = max_failed_attempts
        if lockout_duration_minutes is not None:
            profile.security.lockout_duration_minutes = lockout_duration_minutes

        logger.info(f"Security policy updated for profile: {profile.name}")

    def get_security_status(self, profile: Profile) -> dict:
        """
        Get a summary of the profile's security status.

        Args:
            profile: Profile to check

        Returns:
            Dictionary with security status information
        """
        return {
            "password_protected": profile.security.password_protected,
            "access_log_enabled": profile.security.access_log_enabled,
            "failed_attempts": profile.security.failed_attempts,
            "max_failed_attempts": profile.security.max_failed_attempts,
            "is_locked": self.is_locked_out(profile),
            "lockout_remaining_seconds": self.get_lockout_remaining(profile).total_seconds(),
            "lockout_duration_minutes": profile.security.lockout_duration_minutes,
        }

    def _apply_lockout(self, profile: Profile) -> None:
        """Apply lockout to a profile."""
        profile.security.locked_until = datetime.now() + timedelta(
            minutes=profile.security.lockout_duration_minutes
        )
