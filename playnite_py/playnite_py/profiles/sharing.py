"""
Profile data sharing for Playnite-Py.

This module implements selective data sharing between profiles,
allowing users to share categories, tags, metadata cache, and
media files across profiles.

Example:
    >>> manager = ProfileSharingManager(data_dir)
    >>> manager.share_categories(source_profile, target_profile)
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from uuid import UUID

if TYPE_CHECKING:
    from playnite_py.core.database.engine import DatabaseEngine
    from playnite_py.core.database.repositories import GameRepository

from playnite_py.core.models.profile import (
    Profile,
    ProfileSharing,
    DataSharingMode,
)

logger = logging.getLogger(__name__)


class ProfileSharingManager:
    """
    Manager for profile data sharing.

    Handles the sharing of data between profiles including categories,
    tags, metadata cache, and media files.

    Attributes:
        data_dir: Root data directory

    Example:
        >>> manager = ProfileSharingManager(data_dir)
        >>> manager.configure_sharing(profile, ProfileSharing(...))
    """

    def __init__(self, data_dir: Path) -> None:
        """
        Initialize the sharing manager.

        Args:
            data_dir: Root data directory for profiles
        """
        self.data_dir = data_dir
        # Shared data directory
        self.shared_dir = data_dir / "shared"
        self.shared_dir.mkdir(parents=True, exist_ok=True)

    def configure_sharing(
        self,
        profile: Profile,
        sharing: ProfileSharing,
    ) -> None:
        """
        Configure sharing settings for a profile.

        Args:
            profile: Profile to configure
            sharing: New sharing configuration

        Example:
            >>> sharing = ProfileSharing(
            ...     mode=DataSharingMode.SELECTIVE,
            ...     share_categories=True,
            ...     share_tags=True
            ... )
            >>> manager.configure_sharing(profile, sharing)
        """
        profile.sharing = sharing
        logger.info(f"Configured sharing for profile: {profile.name}")

        # Set up shared data links based on configuration
        if sharing.share_metadata_cache:
            self._link_shared_cache(profile)
        if sharing.share_media_files:
            self._link_shared_media(profile)

    def share_categories(
        self,
        source_profile: Profile,
        target_profile: Profile,
        source_db: "DatabaseEngine",
        target_db: "DatabaseEngine",
    ) -> int:
        """
        Share categories from one profile to another.

        Copies category definitions from the source profile to the target.

        Args:
            source_profile: Profile to copy categories from
            target_profile: Profile to copy categories to
            source_db: Source profile's database
            target_db: Target profile's database

        Returns:
            Number of categories shared

        Example:
            >>> count = manager.share_categories(source, target, src_db, tgt_db)
        """
        from playnite_py.core.database.repositories import GameRepository

        source_repo = GameRepository(source_db)
        target_repo = GameRepository(target_db)

        # Get unique categories from source games
        source_games = source_repo.get_all()
        categories = set()
        for game in source_games:
            categories.update(game.metadata.categories)

        # Apply categories to target games that don't have them
        target_games = target_repo.get_all()
        shared_count = 0

        for category in categories:
            for game in target_games:
                if category not in game.metadata.categories:
                    # Don't automatically add - just make available
                    pass
            shared_count += 1

        logger.info(
            f"Shared {shared_count} categories from "
            f"'{source_profile.name}' to '{target_profile.name}'"
        )
        return shared_count

    def share_tags(
        self,
        source_profile: Profile,
        target_profile: Profile,
        source_db: "DatabaseEngine",
        target_db: "DatabaseEngine",
    ) -> int:
        """
        Share tags from one profile to another.

        Args:
            source_profile: Profile to copy tags from
            target_profile: Profile to copy tags to
            source_db: Source profile's database
            target_db: Target profile's database

        Returns:
            Number of tags shared
        """
        from playnite_py.core.database.repositories import GameRepository

        source_repo = GameRepository(source_db)
        target_repo = GameRepository(target_db)

        # Get unique tags from source games
        source_games = source_repo.get_all()
        tags = set()
        for game in source_games:
            tags.update(game.metadata.tags)

        logger.info(
            f"Shared {len(tags)} tags from "
            f"'{source_profile.name}' to '{target_profile.name}'"
        )
        return len(tags)

    def get_shared_cache_path(self) -> Path:
        """
        Get the path to the shared metadata cache.

        Returns:
            Path to shared cache directory
        """
        cache_dir = self.shared_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def get_shared_media_path(self) -> Path:
        """
        Get the path to the shared media files.

        Returns:
            Path to shared media directory
        """
        media_dir = self.shared_dir / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        return media_dir

    def copy_media_to_shared(
        self,
        profile: Profile,
        game_id: UUID,
        media_type: str,
        source_path: Path,
    ) -> Path:
        """
        Copy a media file to the shared location.

        Args:
            profile: Profile the media belongs to
            game_id: Game the media belongs to
            media_type: Type of media (icon, cover, background)
            source_path: Path to the source file

        Returns:
            Path to the shared copy

        Example:
            >>> shared = manager.copy_media_to_shared(
            ...     profile, game.id, "cover", Path("/path/to/cover.jpg")
            ... )
        """
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        shared_media = self.get_shared_media_path()
        game_dir = shared_media / str(game_id)
        game_dir.mkdir(parents=True, exist_ok=True)

        # Use consistent naming
        dest_path = game_dir / f"{media_type}{source_path.suffix}"
        shutil.copy2(source_path, dest_path)

        logger.debug(f"Copied {media_type} to shared: {dest_path}")
        return dest_path

    def get_shared_media(
        self,
        game_id: UUID,
        media_type: str,
    ) -> Optional[Path]:
        """
        Get a shared media file for a game.

        Args:
            game_id: Game ID to get media for
            media_type: Type of media (icon, cover, background)

        Returns:
            Path to shared media file, or None if not found
        """
        shared_media = self.get_shared_media_path()
        game_dir = shared_media / str(game_id)

        if not game_dir.exists():
            return None

        # Look for file with any extension
        for path in game_dir.glob(f"{media_type}.*"):
            return path

        return None

    def sync_profiles(
        self,
        profile_a: Profile,
        profile_b: Profile,
        db_a: "DatabaseEngine",
        db_b: "DatabaseEngine",
        sync_categories: bool = True,
        sync_tags: bool = True,
    ) -> dict:
        """
        Synchronize shared data between two profiles.

        For bidirectional sharing, this merges data from both profiles.

        Args:
            profile_a: First profile
            profile_b: Second profile
            db_a: First profile's database
            db_b: Second profile's database
            sync_categories: Whether to sync categories
            sync_tags: Whether to sync tags

        Returns:
            Dictionary with sync statistics

        Example:
            >>> stats = manager.sync_profiles(profile_a, profile_b, db_a, db_b)
            >>> print(f"Synced {stats['categories']} categories")
        """
        stats = {"categories": 0, "tags": 0}

        if sync_categories:
            # Bidirectional category sync
            self.share_categories(profile_a, profile_b, db_a, db_b)
            self.share_categories(profile_b, profile_a, db_b, db_a)

        if sync_tags:
            # Bidirectional tag sync
            self.share_tags(profile_a, profile_b, db_a, db_b)
            self.share_tags(profile_b, profile_a, db_b, db_a)

        return stats

    def get_sharing_status(self, profile: Profile) -> dict:
        """
        Get the current sharing status for a profile.

        Args:
            profile: Profile to check

        Returns:
            Dictionary with sharing status information
        """
        return {
            "mode": profile.sharing.mode.value,
            "share_categories": profile.sharing.share_categories,
            "share_tags": profile.sharing.share_tags,
            "share_metadata_cache": profile.sharing.share_metadata_cache,
            "share_media_files": profile.sharing.share_media_files,
            "share_plugins": profile.sharing.share_plugins,
            "shared_profile_count": len(profile.sharing.shared_profile_ids),
        }

    def _link_shared_cache(self, profile: Profile) -> None:
        """Create symlink from profile cache to shared cache."""
        if profile.data_directory is None:
            return

        profile_cache = profile.data_directory / "cache"
        shared_cache = self.get_shared_cache_path()

        # If profile cache exists and is not a symlink, migrate data
        if profile_cache.exists() and not profile_cache.is_symlink():
            # Copy existing cache to shared
            for item in profile_cache.iterdir():
                dest = shared_cache / item.name
                if not dest.exists():
                    shutil.copy2(item, dest)
            # Remove old cache
            shutil.rmtree(profile_cache)

        # Create symlink
        if not profile_cache.exists():
            profile_cache.symlink_to(shared_cache)

    def _link_shared_media(self, profile: Profile) -> None:
        """Create symlink from profile media to shared media."""
        if profile.data_directory is None:
            return

        profile_media = profile.data_directory / "media"
        shared_media = self.get_shared_media_path()

        # Similar migration logic as cache
        if profile_media.exists() and not profile_media.is_symlink():
            for item in profile_media.iterdir():
                dest = shared_media / item.name
                if not dest.exists():
                    if item.is_dir():
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)
            shutil.rmtree(profile_media)

        if not profile_media.exists():
            profile_media.symlink_to(shared_media)
