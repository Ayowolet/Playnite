"""
Profile manager for Playnite-Py.

This module provides the main ProfileManager class that handles all
profile lifecycle operations including creation, switching, deletion,
and management.

Example:
    >>> from playnite_py.profiles import ProfileManager
    >>> manager = ProfileManager("/path/to/data")
    >>> profile = manager.create_profile("Gaming")
    >>> manager.switch_profile("Gaming")
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import UUID

from platformdirs import user_data_dir

from playnite_py.core.database.engine import DatabaseEngine
from playnite_py.core.database.repositories import (
    ProfileRepository,
    ProfileTemplateRepository,
    GameRepository,
    ConfigurationRepository,
)
from playnite_py.core.models.profile import (
    Profile,
    ProfileSettings,
    ProfileStatistics,
    ProfileTemplate,
    ProfileSharing,
    DataSharingMode,
)
from playnite_py.profiles.locking import ProfileLockManager, ProfileLock
from playnite_py.profiles.templates import ProfileTemplateManager, get_builtin_templates
from playnite_py.profiles.inheritance import ProfileInheritanceResolver
from playnite_py.profiles.security import ProfileSecurityManager
from playnite_py.profiles.export import ProfileExporter, ProfileImporter

logger = logging.getLogger(__name__)


class ProfileManager:
    """
    Central manager for all profile operations.

    The ProfileManager is the primary interface for managing game library
    profiles. It handles profile creation, switching, deletion, and
    coordinates with other subsystems like security, locking, and sharing.

    Attributes:
        data_dir: Root directory for all profile data
        current_profile: Currently active profile (or None)
        master_db: Master database for profile metadata
        profile_repo: Repository for profile operations
        template_repo: Repository for template operations
        lock_manager: Manager for profile locking
        template_manager: Manager for profile templates
        security_manager: Manager for profile security
        inheritance_resolver: Resolver for profile inheritance

    Example:
        >>> manager = ProfileManager()
        >>> profile = manager.create_profile("My Games")
        >>> manager.switch_profile("My Games")
        >>> manager.list_profiles()
        [Profile(name='My Games', ...)]
    """

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        app_name: str = "PlaynitePy",
    ) -> None:
        """
        Initialize the ProfileManager.

        Args:
            data_dir: Root directory for profile data. If None, uses
                     platform-specific user data directory.
            app_name: Application name for directory creation

        Example:
            >>> manager = ProfileManager()  # Uses default location
            >>> manager = ProfileManager(Path("/custom/data"))
        """
        if data_dir is None:
            self.data_dir = Path(user_data_dir(app_name))
        else:
            self.data_dir = data_dir

        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize master database for profile metadata
        self.master_db = DatabaseEngine.create_for_profile(
            self.data_dir, db_name="master.db"
        )

        # Initialize repositories
        self.profile_repo = ProfileRepository(self.master_db)
        self.template_repo = ProfileTemplateRepository(self.master_db)

        # Initialize subsystem managers
        self.lock_manager = ProfileLockManager(self.data_dir)
        self.template_manager = ProfileTemplateManager(self.template_repo)
        self.security_manager = ProfileSecurityManager()
        self.inheritance_resolver = ProfileInheritanceResolver(self.profile_repo)

        # Current active profile
        self.current_profile: Optional[Profile] = None
        self._current_profile_db: Optional[DatabaseEngine] = None
        self._current_lock: Optional[ProfileLock] = None

        # Profile switch callbacks
        self._switch_callbacks: list[Callable[[Optional[Profile], Profile], None]] = []

        # Initialize builtin templates
        self._ensure_builtin_templates()

        # Auto-load previously active profile
        self._restore_active_profile()

        logger.info(f"ProfileManager initialized with data directory: {self.data_dir}")

    def _restore_active_profile(self) -> None:
        """Restore the previously active profile from database."""
        active_profile = self.profile_repo.get_active()
        if active_profile:
            try:
                profile_path = self._get_profile_path(active_profile)
                if profile_path.exists():
                    lock = self.lock_manager.acquire_lock(active_profile.id, profile_path)
                    self.current_profile = active_profile
                    self._current_lock = lock
                    self._current_profile_db = DatabaseEngine.create_for_profile(profile_path)
                    logger.debug(f"Restored active profile: {active_profile.name}")
            except Exception as e:
                logger.warning(f"Could not restore active profile: {e}")
                # Mark as inactive if restoration fails
                active_profile.is_active = False
                self.profile_repo.update(active_profile)

    def _ensure_builtin_templates(self) -> None:
        """Ensure builtin profile templates exist."""
        existing = {t.name for t in self.template_repo.get_all()}
        for template in get_builtin_templates():
            if template.name not in existing:
                self.template_repo.create(template)
                logger.debug(f"Created builtin template: {template.name}")

    def _get_profile_path(self, profile: Profile) -> Path:
        """Get the data directory path for a profile."""
        return self.data_dir / "profiles" / str(profile.id)

    def create_profile(
        self,
        name: str,
        description: str = "",
        template: Optional[str] = None,
        parent_profile: Optional[str] = None,
        settings: Optional[ProfileSettings] = None,
        sharing: Optional[ProfileSharing] = None,
        set_as_default: bool = False,
    ) -> Profile:
        """
        Create a new profile.

        Creates a new isolated profile with its own database, configuration,
        and media directories. Can be based on a template or inherit from
        a parent profile.

        Args:
            name: Unique name for the profile
            description: Optional profile description
            template: Name of template to use for initial settings
            parent_profile: Name of parent profile for inheritance
            settings: Custom settings (overrides template)
            sharing: Data sharing configuration
            set_as_default: Whether to set as default startup profile

        Returns:
            The newly created Profile

        Raises:
            ValueError: If profile name already exists or is invalid
            FileExistsError: If profile directory already exists

        Example:
            >>> profile = manager.create_profile(
            ...     "Kids Gaming",
            ...     description="Safe games for children",
            ...     template="default"
            ... )
        """
        # Check for existing profile with same name
        if self.profile_repo.get_by_name(name):
            raise ValueError(f"Profile '{name}' already exists")

        # Start with template settings if specified
        if template:
            template_obj = self.template_manager.get_template(template)
            if template_obj:
                profile = Profile.from_template(template_obj, name)
            else:
                raise ValueError(f"Template '{template}' not found")
        else:
            profile = Profile(name=name)

        # Set description
        profile.description = description

        # Apply custom settings if provided
        if settings:
            profile.settings = settings
        if sharing:
            profile.sharing = sharing

        # Set up parent profile for inheritance
        if parent_profile:
            parent = self.profile_repo.get_by_name(parent_profile)
            if not parent:
                raise ValueError(f"Parent profile '{parent_profile}' not found")
            profile.parent_profile_id = parent.id

        # Create profile directory
        profile_path = self._get_profile_path(profile)
        if profile_path.exists():
            raise FileExistsError(f"Profile directory already exists: {profile_path}")

        profile_path.mkdir(parents=True)
        profile.data_directory = profile_path

        # Create subdirectories
        (profile_path / "media").mkdir()
        (profile_path / "cache").mkdir()
        (profile_path / "plugins").mkdir()

        # Create profile database
        DatabaseEngine.create_for_profile(profile_path)

        # Save to master database
        self.profile_repo.create(profile)

        # Set as default if requested
        if set_as_default:
            self.set_default_profile(profile.name)

        logger.info(f"Created profile: {name}")
        return profile

    def get_profile(self, name: str) -> Optional[Profile]:
        """
        Get a profile by name.

        Args:
            name: Profile name

        Returns:
            Profile if found, None otherwise

        Example:
            >>> profile = manager.get_profile("Gaming")
        """
        return self.profile_repo.get_by_name(name)

    def get_profile_by_id(self, profile_id: UUID) -> Optional[Profile]:
        """
        Get a profile by its ID.

        Args:
            profile_id: Profile UUID

        Returns:
            Profile if found, None otherwise
        """
        return self.profile_repo.get_by_id(profile_id)

    def list_profiles(self) -> list[Profile]:
        """
        List all profiles.

        Returns:
            List of all profiles

        Example:
            >>> profiles = manager.list_profiles()
            >>> for p in profiles:
            ...     print(p.name)
        """
        return self.profile_repo.get_all()

    def switch_profile(
        self,
        name: str,
        password: Optional[str] = None,
        force: bool = False,
    ) -> Profile:
        """
        Switch to a different profile.

        Deactivates the current profile (if any) and activates the
        specified profile. This operation does not require application
        restart.

        Args:
            name: Name of profile to switch to
            password: Password if profile is protected
            force: Force switch even if profile is locked

        Returns:
            The newly activated profile

        Raises:
            ValueError: If profile not found
            PermissionError: If profile is password protected and wrong password
            RuntimeError: If profile is locked by another instance

        Example:
            >>> manager.switch_profile("Work")
            >>> manager.switch_profile("Personal", password="secret")
        """
        profile = self.profile_repo.get_by_name(name)
        if not profile:
            raise ValueError(f"Profile '{name}' not found")

        # Check password protection
        if profile.security.password_protected:
            if not password:
                raise PermissionError(f"Profile '{name}' is password protected")
            if not self.security_manager.verify_password(profile, password):
                self.profile_repo.log_access(
                    profile.id, "switch_attempt", success=False
                )
                raise PermissionError("Invalid password")

        # Try to acquire lock
        profile_path = self._get_profile_path(profile)
        try:
            lock = self.lock_manager.acquire_lock(profile.id, profile_path, force=force)
        except RuntimeError as e:
            raise RuntimeError(f"Cannot switch to profile '{name}': {e}")

        # Release current profile if any
        old_profile = self.current_profile
        if self.current_profile:
            self._deactivate_current_profile()

        # Activate new profile
        self.current_profile = profile
        self._current_lock = lock
        self._current_profile_db = DatabaseEngine.create_for_profile(profile_path)

        # Update profile statistics
        profile.statistics.record_session()
        self.profile_repo.update(profile)

        # Update active status in database
        self.profile_repo.set_active(profile.id)

        # Log access
        if profile.security.access_log_enabled:
            self.profile_repo.log_access(profile.id, "switch", success=True)

        # Notify callbacks
        for callback in self._switch_callbacks:
            try:
                callback(old_profile, profile)
            except Exception as e:
                logger.error(f"Profile switch callback error: {e}")

        logger.info(f"Switched to profile: {name}")
        return profile

    def _deactivate_current_profile(self) -> None:
        """Deactivate the current profile."""
        if self.current_profile:
            # Update active status
            self.current_profile.is_active = False
            self.profile_repo.update(self.current_profile)

            # Close database
            if self._current_profile_db:
                self._current_profile_db.close()
                self._current_profile_db = None

            # Release lock
            if self._current_lock:
                self.lock_manager.release_lock(self.current_profile.id)
                self._current_lock = None

            logger.debug(f"Deactivated profile: {self.current_profile.name}")
            self.current_profile = None

    def delete_profile(
        self,
        name: str,
        delete_data: bool = False,
        password: Optional[str] = None,
    ) -> bool:
        """
        Delete a profile.

        Args:
            name: Profile name to delete
            delete_data: Whether to delete all profile data files
            password: Password if profile is protected

        Returns:
            True if deleted successfully

        Raises:
            ValueError: If profile not found or is currently active
            PermissionError: If profile is protected and wrong password

        Example:
            >>> manager.delete_profile("Old Profile", delete_data=True)
        """
        profile = self.profile_repo.get_by_name(name)
        if not profile:
            raise ValueError(f"Profile '{name}' not found")

        # Cannot delete active profile
        if self.current_profile and self.current_profile.id == profile.id:
            raise ValueError("Cannot delete currently active profile")

        # Check password
        if profile.security.password_protected:
            if not password:
                if profile.security.access_log_enabled:
                    self.profile_repo.log_access(
                        profile.id, "delete_attempt", success=False,
                        details={"reason": "password_required"}
                    )
                raise PermissionError(f"Profile '{name}' is password protected")
            if not self.security_manager.verify_password(profile, password):
                if profile.security.access_log_enabled:
                    self.profile_repo.log_access(
                        profile.id, "delete_attempt", success=False,
                        details={"reason": "invalid_password"}
                    )
                raise PermissionError("Invalid password")

        # Check if locked by another instance
        profile_path = self._get_profile_path(profile)
        if self.lock_manager.is_locked(profile.id, profile_path):
            raise RuntimeError(f"Profile '{name}' is locked by another instance")

        # Log successful delete before removal
        if profile.security.access_log_enabled:
            self.profile_repo.log_access(
                profile.id, "delete", success=True
            )

        # Delete from database
        self.profile_repo.delete(profile.id)

        # Delete data files if requested
        if delete_data and profile_path.exists():
            shutil.rmtree(profile_path)
            logger.info(f"Deleted profile data: {profile_path}")

        logger.info(f"Deleted profile: {name}")
        return True

    def rename_profile(self, old_name: str, new_name: str) -> Profile:
        """
        Rename a profile.

        Args:
            old_name: Current profile name
            new_name: New profile name

        Returns:
            Updated profile

        Raises:
            ValueError: If profile not found or new name exists

        Example:
            >>> manager.rename_profile("Gaming", "My Games")
        """
        profile = self.profile_repo.get_by_name(old_name)
        if not profile:
            raise ValueError(f"Profile '{old_name}' not found")

        if self.profile_repo.get_by_name(new_name):
            raise ValueError(f"Profile '{new_name}' already exists")

        profile.name = new_name
        self.profile_repo.update(profile)

        logger.info(f"Renamed profile: {old_name} -> {new_name}")
        return profile

    def duplicate_profile(
        self,
        source_name: str,
        new_name: str,
        copy_games: bool = True,
        copy_configurations: bool = True,
    ) -> Profile:
        """
        Create a copy of an existing profile.

        Args:
            source_name: Profile to copy
            new_name: Name for the new profile
            copy_games: Whether to copy game entries
            copy_configurations: Whether to copy configurations

        Returns:
            The newly created profile

        Raises:
            ValueError: If source profile not found or new name exists

        Example:
            >>> manager.duplicate_profile("Gaming", "Gaming Backup")
        """
        source = self.profile_repo.get_by_name(source_name)
        if not source:
            raise ValueError(f"Profile '{source_name}' not found")

        # Create new profile with same settings
        new_profile = self.create_profile(
            name=new_name,
            description=f"Copy of {source_name}",
            settings=source.settings.model_copy(),
            sharing=source.sharing.model_copy(),
        )

        # Copy games and configurations if requested
        if copy_games or copy_configurations:
            source_path = self._get_profile_path(source)
            source_db = DatabaseEngine.create_for_profile(source_path)
            source_game_repo = GameRepository(source_db)
            source_config_repo = ConfigurationRepository(source_db)

            new_path = self._get_profile_path(new_profile)
            new_db = DatabaseEngine.create_for_profile(new_path)
            new_game_repo = GameRepository(new_db)
            new_config_repo = ConfigurationRepository(new_db)

            if copy_games:
                for game in source_game_repo.get_all():
                    new_game_repo.create(game.model_copy(update={"id": None}))

            if copy_configurations:
                for config in source_config_repo.get_all():
                    new_config_repo.create(config.model_copy(update={"id": None}))

            source_db.close()
            new_db.close()

        logger.info(f"Duplicated profile: {source_name} -> {new_name}")
        return new_profile

    def set_default_profile(self, name: str) -> None:
        """
        Set a profile as the default startup profile.

        Args:
            name: Profile name to set as default

        Raises:
            ValueError: If profile not found

        Example:
            >>> manager.set_default_profile("Personal")
        """
        profile = self.profile_repo.get_by_name(name)
        if not profile:
            raise ValueError(f"Profile '{name}' not found")

        self.profile_repo.set_default(profile.id)
        logger.info(f"Set default profile: {name}")

    def get_default_profile(self) -> Optional[Profile]:
        """
        Get the default profile.

        Returns:
            Default profile if set, None otherwise
        """
        return self.profile_repo.get_default()

    def get_current_profile(self) -> Optional[Profile]:
        """
        Get the currently active profile.

        Returns:
            Current profile or None if no profile is active
        """
        return self.current_profile

    def get_profile_database(self) -> Optional[DatabaseEngine]:
        """
        Get the database engine for the current profile.

        Returns:
            DatabaseEngine for current profile, None if no profile active
        """
        return self._current_profile_db

    def get_profile_statistics(self, name: str) -> Optional[ProfileStatistics]:
        """
        Get statistics for a profile.

        Args:
            name: Profile name

        Returns:
            ProfileStatistics if found, None otherwise
        """
        profile = self.profile_repo.get_by_name(name)
        if profile:
            return profile.statistics
        return None

    def update_profile_settings(
        self,
        name: str,
        settings: ProfileSettings,
    ) -> Profile:
        """
        Update settings for a profile.

        Args:
            name: Profile name
            settings: New settings

        Returns:
            Updated profile

        Raises:
            ValueError: If profile not found
        """
        profile = self.profile_repo.get_by_name(name)
        if not profile:
            raise ValueError(f"Profile '{name}' not found")

        profile.settings = settings
        self.profile_repo.update(profile)

        # Update current profile reference if active
        if self.current_profile and self.current_profile.id == profile.id:
            self.current_profile = profile

        logger.info(f"Updated settings for profile: {name}")
        return profile

    def get_effective_settings(self, name: str) -> ProfileSettings:
        """
        Get effective settings for a profile with inheritance applied.

        Args:
            name: Profile name

        Returns:
            Merged settings with inheritance

        Raises:
            ValueError: If profile not found
        """
        profile = self.profile_repo.get_by_name(name)
        if not profile:
            raise ValueError(f"Profile '{name}' not found")

        return self.inheritance_resolver.get_effective_settings(profile)

    def set_profile_password(
        self,
        name: str,
        password: str,
        current_password: Optional[str] = None,
    ) -> None:
        """
        Set or change password for a profile.

        Args:
            name: Profile name
            password: New password
            current_password: Current password (if already protected)

        Raises:
            ValueError: If profile not found
            PermissionError: If current password is wrong
        """
        profile = self.profile_repo.get_by_name(name)
        if not profile:
            raise ValueError(f"Profile '{name}' not found")

        # Verify current password if profile is already protected
        if profile.security.password_protected:
            if not current_password:
                if profile.security.access_log_enabled:
                    self.profile_repo.log_access(
                        profile.id, "password_change_attempt", success=False,
                        details={"reason": "current_password_required"}
                    )
                raise PermissionError("Current password required")
            if not self.security_manager.verify_password(profile, current_password):
                if profile.security.access_log_enabled:
                    self.profile_repo.log_access(
                        profile.id, "password_change_attempt", success=False,
                        details={"reason": "invalid_current_password"}
                    )
                raise PermissionError("Invalid current password")

        self.security_manager.set_password(profile, password)
        self.profile_repo.update(profile)

        # Log successful password change
        if profile.security.access_log_enabled:
            self.profile_repo.log_access(
                profile.id, "password_set", success=True
            )

        logger.info(f"Set password for profile: {name}")

    def remove_profile_password(
        self,
        name: str,
        current_password: str,
    ) -> None:
        """
        Remove password protection from a profile.

        Args:
            name: Profile name
            current_password: Current password

        Raises:
            ValueError: If profile not found or not protected
            PermissionError: If password is wrong
        """
        profile = self.profile_repo.get_by_name(name)
        if not profile:
            raise ValueError(f"Profile '{name}' not found")

        if not profile.security.password_protected:
            raise ValueError(f"Profile '{name}' is not password protected")

        if not self.security_manager.verify_password(profile, current_password):
            if profile.security.access_log_enabled:
                self.profile_repo.log_access(
                    profile.id, "password_remove_attempt", success=False,
                    details={"reason": "invalid_password"}
                )
            raise PermissionError("Invalid password")

        self.security_manager.clear_password(profile)
        self.profile_repo.update(profile)

        # Log successful password removal
        if profile.security.access_log_enabled:
            self.profile_repo.log_access(
                profile.id, "password_removed", success=True
            )

        logger.info(f"Removed password from profile: {name}")

    def export_profile(
        self,
        name: str,
        output_path: Path,
        include_games: bool = True,
        include_media: bool = True,
        include_configurations: bool = True,
        password: Optional[str] = None,
    ) -> Path:
        """
        Export a profile to a file for backup or migration.

        Args:
            name: Profile name to export
            output_path: Path for the export file
            include_games: Include game library
            include_media: Include media files (covers, icons)
            include_configurations: Include platform configurations
            password: Optional encryption password for export

        Returns:
            Path to the created export file

        Raises:
            ValueError: If profile not found

        Example:
            >>> manager.export_profile("Gaming", Path("~/backup/gaming.ppf"))
        """
        profile = self.profile_repo.get_by_name(name)
        if not profile:
            raise ValueError(f"Profile '{name}' not found")

        profile_path = self._get_profile_path(profile)
        exporter = ProfileExporter()

        export_path = exporter.export_profile(
            profile=profile,
            profile_path=profile_path,
            output_path=output_path,
            include_games=include_games,
            include_media=include_media,
            include_configurations=include_configurations,
            password=password,
        )

        logger.info(f"Exported profile '{name}' to {export_path}")
        return export_path

    def import_profile(
        self,
        import_path: Path,
        new_name: Optional[str] = None,
        password: Optional[str] = None,
        overwrite: bool = False,
    ) -> Profile:
        """
        Import a profile from an export file.

        Args:
            import_path: Path to the export file
            new_name: Override the profile name
            password: Decryption password (if encrypted)
            overwrite: Overwrite existing profile with same name

        Returns:
            The imported profile

        Raises:
            FileNotFoundError: If import file not found
            ValueError: If profile with same name exists (without overwrite)

        Example:
            >>> profile = manager.import_profile(Path("~/backup/gaming.ppf"))
        """
        if not import_path.exists():
            raise FileNotFoundError(f"Import file not found: {import_path}")

        importer = ProfileImporter()
        profile_data = importer.read_export(import_path, password)

        # Determine profile name
        profile_name = new_name or profile_data["name"]

        # Check for existing profile
        existing = self.profile_repo.get_by_name(profile_name)
        if existing:
            if overwrite:
                self.delete_profile(profile_name, delete_data=True)
            else:
                raise ValueError(
                    f"Profile '{profile_name}' already exists. Use overwrite=True to replace."
                )

        # Create profile from import data
        profile = Profile(
            name=profile_name,
            description=profile_data.get("description", ""),
            settings=ProfileSettings(**profile_data.get("settings", {})),
            sharing=ProfileSharing(**profile_data.get("sharing", {})),
        )

        # Create profile directory and copy data
        profile_path = self._get_profile_path(profile)
        profile_path.mkdir(parents=True)
        profile.data_directory = profile_path

        # Import profile data
        importer.import_to_path(import_path, profile_path, password)

        # Save to database
        self.profile_repo.create(profile)

        logger.info(f"Imported profile '{profile_name}' from {import_path}")
        return profile

    def add_switch_callback(
        self,
        callback: Callable[[Optional[Profile], Profile], None],
    ) -> None:
        """
        Register a callback for profile switch events.

        The callback will be called after a successful profile switch
        with the old profile (or None) and the new profile.

        Args:
            callback: Function to call on profile switch

        Example:
            >>> def on_switch(old, new):
            ...     print(f"Switched from {old.name if old else 'None'} to {new.name}")
            >>> manager.add_switch_callback(on_switch)
        """
        self._switch_callbacks.append(callback)

    def remove_switch_callback(
        self,
        callback: Callable[[Optional[Profile], Profile], None],
    ) -> None:
        """
        Remove a profile switch callback.

        Args:
            callback: Callback to remove
        """
        if callback in self._switch_callbacks:
            self._switch_callbacks.remove(callback)

    def get_profile_game_count(self, name: str) -> int:
        """
        Get the number of games in a profile.

        Args:
            name: Profile name

        Returns:
            Number of games in the profile

        Raises:
            ValueError: If profile not found
        """
        profile = self.profile_repo.get_by_name(name)
        if not profile:
            raise ValueError(f"Profile '{name}' not found")

        profile_path = self._get_profile_path(profile)
        db = DatabaseEngine.create_for_profile(profile_path)
        game_repo = GameRepository(db)
        count = game_repo.count()
        db.close()
        return count

    def cleanup_unused_profiles(
        self,
        days_unused: int = 90,
        dry_run: bool = True,
    ) -> list[Profile]:
        """
        Identify profiles that haven't been used recently.

        Args:
            days_unused: Consider unused if not accessed in this many days
            dry_run: If True, only report profiles without deleting

        Returns:
            List of unused profiles

        Example:
            >>> unused = manager.cleanup_unused_profiles(days_unused=180)
            >>> for p in unused:
            ...     print(f"Unused: {p.name}")
        """
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days_unused)
        unused = []

        for profile in self.profile_repo.get_all():
            # Skip default profile
            if profile.is_default:
                continue

            # Check last used date
            last_used = profile.statistics.last_used
            if last_used is None or last_used < cutoff:
                unused.append(profile)

                if not dry_run:
                    self.delete_profile(profile.name, delete_data=True)

        if unused:
            logger.info(
                f"Found {len(unused)} unused profiles "
                f"({'deleted' if not dry_run else 'dry run'})"
            )

        return unused

    def close(self) -> None:
        """
        Close the profile manager and release all resources.

        Should be called when the application is shutting down.
        """
        if self.current_profile:
            self._deactivate_current_profile()

        self.master_db.close()
        logger.info("ProfileManager closed")

    def to_dict(self, name: str) -> dict[str, Any]:
        """
        Get profile data as a dictionary (for CLI JSON output).

        Args:
            name: Profile name

        Returns:
            Dictionary representation of the profile

        Raises:
            ValueError: If profile not found
        """
        profile = self.profile_repo.get_by_name(name)
        if not profile:
            raise ValueError(f"Profile '{name}' not found")
        return profile.to_dict()

    def __enter__(self) -> "ProfileManager":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
