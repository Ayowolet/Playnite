"""
Profile locking for Playnite-Py.

This module provides file-based locking to prevent multiple
application instances from accessing the same profile simultaneously.

Example:
    >>> lock_manager = ProfileLockManager("/path/to/data")
    >>> lock = lock_manager.acquire_lock(profile_id, profile_path)
    >>> # ... use profile ...
    >>> lock_manager.release_lock(profile_id)
"""

from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from filelock import FileLock, Timeout

logger = logging.getLogger(__name__)


@dataclass
class ProfileLock:
    """
    Represents an acquired lock on a profile.

    Attributes:
        profile_id: ID of the locked profile
        lock_file: Path to the lock file
        lock: FileLock instance
        acquired_at: When the lock was acquired
        hostname: Host that acquired the lock
        pid: Process ID that acquired the lock
    """
    profile_id: UUID
    lock_file: Path
    lock: FileLock
    acquired_at: datetime
    hostname: str
    pid: int


class ProfileLockManager:
    """
    Manager for profile locks.

    Uses file-based locking to ensure only one application instance
    can access a profile at a time.

    Attributes:
        data_dir: Root data directory for lock files
        locks: Dictionary of active locks by profile ID

    Example:
        >>> manager = ProfileLockManager(Path("/data"))
        >>> lock = manager.acquire_lock(profile.id, profile_path)
        >>> manager.release_lock(profile.id)
    """

    def __init__(self, data_dir: Path) -> None:
        """
        Initialize the lock manager.

        Args:
            data_dir: Root directory for storing lock files
        """
        self.data_dir = data_dir
        self.locks: dict[UUID, ProfileLock] = {}

        # Create locks directory
        self.locks_dir = data_dir / "locks"
        self.locks_dir.mkdir(parents=True, exist_ok=True)

    def acquire_lock(
        self,
        profile_id: UUID,
        profile_path: Path,
        timeout: float = 5.0,
        force: bool = False,
    ) -> ProfileLock:
        """
        Acquire a lock on a profile.

        Creates a lock file and attempts to acquire an exclusive lock.
        If the lock is already held by another process, either waits
        for the specified timeout or raises an error.

        Args:
            profile_id: ID of the profile to lock
            profile_path: Path to the profile data directory
            timeout: Seconds to wait for lock acquisition
            force: If True, steal the lock from another process

        Returns:
            ProfileLock instance

        Raises:
            RuntimeError: If lock cannot be acquired within timeout

        Example:
            >>> lock = manager.acquire_lock(profile.id, profile_path)
        """
        lock_file = self._get_lock_file_path(profile_id)

        # If we already hold this lock, return it
        if profile_id in self.locks:
            return self.locks[profile_id]

        # Create lock file
        file_lock = FileLock(str(lock_file), timeout=timeout)

        if force:
            # Remove existing lock file
            if lock_file.exists():
                try:
                    lock_file.unlink()
                except OSError:
                    pass

        try:
            file_lock.acquire(timeout=timeout)
        except Timeout:
            # Read lock info to report who holds it
            lock_info = self._read_lock_info(lock_file)
            if lock_info:
                raise RuntimeError(
                    f"Profile is locked by {lock_info['hostname']} "
                    f"(PID: {lock_info['pid']}) since {lock_info['acquired_at']}"
                )
            raise RuntimeError("Profile is locked by another process")

        # Write lock info
        lock = ProfileLock(
            profile_id=profile_id,
            lock_file=lock_file,
            lock=file_lock,
            acquired_at=datetime.now(),
            hostname=socket.gethostname(),
            pid=os.getpid(),
        )
        self._write_lock_info(lock)
        self.locks[profile_id] = lock

        logger.debug(f"Acquired lock for profile {profile_id}")
        return lock

    def release_lock(self, profile_id: UUID) -> bool:
        """
        Release a lock on a profile.

        Args:
            profile_id: ID of the profile to unlock

        Returns:
            True if lock was released, False if not held

        Example:
            >>> manager.release_lock(profile.id)
        """
        if profile_id not in self.locks:
            return False

        lock = self.locks[profile_id]
        lock.lock.release()

        # Remove lock info file
        info_file = lock.lock_file.with_suffix(".info")
        if info_file.exists():
            try:
                info_file.unlink()
            except OSError:
                pass

        del self.locks[profile_id]
        logger.debug(f"Released lock for profile {profile_id}")
        return True

    def is_locked(self, profile_id: UUID, profile_path: Path) -> bool:
        """
        Check if a profile is currently locked.

        Args:
            profile_id: ID of the profile to check
            profile_path: Path to the profile data directory

        Returns:
            True if locked, False otherwise

        Example:
            >>> if manager.is_locked(profile.id, profile_path):
            ...     print("Profile is in use")
        """
        # If we hold the lock, it's locked by us
        if profile_id in self.locks:
            return True

        lock_file = self._get_lock_file_path(profile_id)

        # Try to acquire the lock with zero timeout
        test_lock = FileLock(str(lock_file), timeout=0)
        try:
            test_lock.acquire(timeout=0)
            test_lock.release()
            return False
        except Timeout:
            return True

    def get_lock_info(self, profile_id: UUID) -> Optional[dict]:
        """
        Get information about who holds a lock.

        Args:
            profile_id: ID of the profile

        Returns:
            Dictionary with lock info, or None if not locked

        Example:
            >>> info = manager.get_lock_info(profile.id)
            >>> if info:
            ...     print(f"Locked by {info['hostname']}")
        """
        lock_file = self._get_lock_file_path(profile_id)
        return self._read_lock_info(lock_file)

    def release_all(self) -> int:
        """
        Release all locks held by this manager.

        Returns:
            Number of locks released
        """
        profile_ids = list(self.locks.keys())
        count = 0
        for profile_id in profile_ids:
            if self.release_lock(profile_id):
                count += 1
        logger.info(f"Released {count} profile locks")
        return count

    def cleanup_stale_locks(self, max_age_hours: int = 24) -> int:
        """
        Remove stale lock files that are older than max_age.

        Stale locks can occur if the application crashes without
        properly releasing locks.

        Args:
            max_age_hours: Maximum age of lock files in hours

        Returns:
            Number of stale locks cleaned up
        """
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        cleaned = 0

        for lock_file in self.locks_dir.glob("*.lock"):
            info = self._read_lock_info(lock_file)
            if info and info.get("acquired_at"):
                try:
                    acquired = datetime.fromisoformat(info["acquired_at"])
                    if acquired < cutoff:
                        lock_file.unlink()
                        info_file = lock_file.with_suffix(".info")
                        if info_file.exists():
                            info_file.unlink()
                        cleaned += 1
                except (ValueError, OSError):
                    pass

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} stale lock files")
        return cleaned

    def _get_lock_file_path(self, profile_id: UUID) -> Path:
        """Get the path to a profile's lock file."""
        return self.locks_dir / f"{profile_id}.lock"

    def _write_lock_info(self, lock: ProfileLock) -> None:
        """Write lock information to a sidecar file."""
        info_file = lock.lock_file.with_suffix(".info")
        info = {
            "profile_id": str(lock.profile_id),
            "hostname": lock.hostname,
            "pid": lock.pid,
            "acquired_at": lock.acquired_at.isoformat(),
        }
        info_file.write_text(str(info))

    def _read_lock_info(self, lock_file: Path) -> Optional[dict]:
        """Read lock information from a sidecar file."""
        info_file = lock_file.with_suffix(".info")
        if not info_file.exists():
            return None

        try:
            import ast
            content = info_file.read_text()
            return ast.literal_eval(content)
        except (ValueError, SyntaxError, OSError):
            return None
