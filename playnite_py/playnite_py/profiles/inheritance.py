"""
Profile inheritance resolution for Playnite-Py.

This module handles the resolution of inherited settings between
parent and child profiles, allowing profiles to inherit settings
from a parent profile while overriding specific values.

Example:
    >>> resolver = ProfileInheritanceResolver(repo)
    >>> effective = resolver.get_effective_settings(child_profile)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
from uuid import UUID

if TYPE_CHECKING:
    from playnite_py.core.database.repositories import ProfileRepository

from playnite_py.core.models.profile import (
    Profile,
    ProfileSettings,
    ProfileSharing,
)

logger = logging.getLogger(__name__)


class ProfileInheritanceResolver:
    """
    Resolves inherited settings for profiles.

    Handles the inheritance chain from child to parent profiles,
    merging settings with proper precedence.

    Attributes:
        repo: Profile repository for loading parent profiles

    Example:
        >>> resolver = ProfileInheritanceResolver(repo)
        >>> parent = Profile(name="Parent", settings=ProfileSettings(theme="dark"))
        >>> child = Profile(name="Child", parent_profile_id=parent.id)
        >>> effective = resolver.get_effective_settings(child)
        >>> effective.theme
        'dark'
    """

    def __init__(self, repo: "ProfileRepository") -> None:
        """
        Initialize the inheritance resolver.

        Args:
            repo: Profile repository for loading profiles
        """
        self.repo = repo
        # Cache for loaded profiles to avoid repeated database queries
        self._cache: dict[UUID, Profile] = {}

    def get_effective_settings(self, profile: Profile) -> ProfileSettings:
        """
        Get effective settings with inheritance applied.

        Walks up the inheritance chain from child to root parent,
        merging settings with child settings taking precedence.

        Args:
            profile: Profile to get effective settings for

        Returns:
            Merged ProfileSettings with inheritance applied

        Example:
            >>> parent = Profile(name="Parent")
            >>> parent.settings.theme = "dark"
            >>> child = Profile(name="Child", parent_profile_id=parent.id)
            >>> effective = resolver.get_effective_settings(child)
            >>> effective.theme  # Inherited from parent
            'dark'
        """
        # Build inheritance chain (child -> ... -> root)
        chain = self._build_inheritance_chain(profile)

        if len(chain) == 1:
            # No inheritance, return copy of own settings
            return profile.settings.model_copy()

        # Start with root parent settings and merge down
        # chain is [child, parent, grandparent, ...], reverse to start from root
        chain.reverse()

        # Start with the root's settings
        effective_data = chain[0].settings.model_dump()

        # Merge each subsequent profile's settings
        defaults = ProfileSettings().model_dump()
        for ancestor in chain[1:]:
            ancestor_data = ancestor.settings.model_dump()
            for key, value in ancestor_data.items():
                # Only override if the ancestor explicitly set a non-default value
                if value != defaults.get(key):
                    effective_data[key] = value

        return ProfileSettings(**effective_data)

    def get_effective_sharing(self, profile: Profile) -> ProfileSharing:
        """
        Get effective sharing configuration with inheritance.

        Sharing settings are typically not inherited but can be
        configured to do so. By default, sharing is profile-specific.

        Args:
            profile: Profile to get sharing config for

        Returns:
            ProfileSharing configuration
        """
        # For now, sharing is not inherited
        return profile.sharing.model_copy()

    def get_inheritance_chain(self, profile: Profile) -> list[Profile]:
        """
        Get the full inheritance chain for a profile.

        Returns the list of profiles from child to root ancestor.

        Args:
            profile: Starting profile

        Returns:
            List of profiles from child to root

        Example:
            >>> chain = resolver.get_inheritance_chain(child)
            >>> [p.name for p in chain]
            ['child', 'parent', 'grandparent']
        """
        return self._build_inheritance_chain(profile)

    def get_root_profile(self, profile: Profile) -> Profile:
        """
        Get the root ancestor of a profile's inheritance chain.

        Args:
            profile: Profile to find root for

        Returns:
            Root profile (profile without parent)
        """
        chain = self._build_inheritance_chain(profile)
        return chain[-1]

    def has_circular_inheritance(self, profile: Profile) -> bool:
        """
        Check if a profile has circular inheritance.

        Args:
            profile: Profile to check

        Returns:
            True if circular inheritance detected
        """
        try:
            self._build_inheritance_chain(profile)
            return False
        except RecursionError:
            return True

    def validate_parent(
        self,
        profile: Profile,
        new_parent_id: UUID,
    ) -> tuple[bool, str]:
        """
        Validate that setting a new parent won't create circular inheritance.

        Args:
            profile: Profile being modified
            new_parent_id: Proposed parent profile ID

        Returns:
            Tuple of (is_valid, error_message)

        Example:
            >>> valid, error = resolver.validate_parent(child, grandchild.id)
            >>> valid
            False
            >>> error
            'Would create circular inheritance'
        """
        # Can't be your own parent
        if new_parent_id == profile.id:
            return False, "Profile cannot be its own parent"

        # Load the proposed parent
        new_parent = self._get_profile(new_parent_id)
        if not new_parent:
            return False, f"Parent profile not found: {new_parent_id}"

        # Check if proposed parent has this profile in its ancestry
        parent_chain = self._build_inheritance_chain(new_parent)
        if any(p.id == profile.id for p in parent_chain):
            return False, "Would create circular inheritance"

        return True, ""

    def get_children(self, profile: Profile) -> list[Profile]:
        """
        Get all profiles that inherit from this profile.

        Args:
            profile: Profile to find children for

        Returns:
            List of child profiles
        """
        children = []
        for p in self.repo.get_all():
            if p.parent_profile_id == profile.id:
                children.append(p)
        return children

    def get_all_descendants(self, profile: Profile) -> list[Profile]:
        """
        Get all profiles that inherit from this profile (recursively).

        Args:
            profile: Profile to find descendants for

        Returns:
            List of all descendant profiles
        """
        descendants = []
        for child in self.get_children(profile):
            descendants.append(child)
            descendants.extend(self.get_all_descendants(child))
        return descendants

    def clear_cache(self) -> None:
        """Clear the profile cache."""
        self._cache.clear()

    def _build_inheritance_chain(
        self,
        profile: Profile,
        seen: Optional[set[UUID]] = None,
    ) -> list[Profile]:
        """
        Build the inheritance chain from child to root.

        Args:
            profile: Starting profile
            seen: Set of already-seen profile IDs (for cycle detection)

        Returns:
            List of profiles from child to root

        Raises:
            RecursionError: If circular inheritance is detected
        """
        if seen is None:
            seen = set()

        if profile.id in seen:
            raise RecursionError(
                f"Circular inheritance detected for profile: {profile.name}"
            )

        seen.add(profile.id)
        chain = [profile]

        if profile.parent_profile_id:
            parent = self._get_profile(profile.parent_profile_id)
            if parent:
                chain.extend(self._build_inheritance_chain(parent, seen))

        return chain

    def _get_profile(self, profile_id: UUID) -> Optional[Profile]:
        """Get a profile by ID, using cache if available."""
        if profile_id in self._cache:
            return self._cache[profile_id]

        profile = self.repo.get_by_id(profile_id)
        if profile:
            self._cache[profile_id] = profile
        return profile
