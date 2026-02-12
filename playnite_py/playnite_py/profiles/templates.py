"""
Profile templates for Playnite-Py.

This module provides profile template management including builtin
templates and custom template creation.

Example:
    >>> from playnite_py.profiles.templates import ProfileTemplateManager
    >>> manager = ProfileTemplateManager(repo)
    >>> template = manager.get_template("default")
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
from uuid import UUID

if TYPE_CHECKING:
    from playnite_py.core.database.repositories import ProfileTemplateRepository

from playnite_py.core.models.profile import (
    Profile,
    ProfileSettings,
    ProfileSharing,
    ProfileTemplate,
    DataSharingMode,
)

logger = logging.getLogger(__name__)


def get_builtin_templates() -> list[ProfileTemplate]:
    """
    Get all builtin profile templates.

    Returns a list of predefined templates that are always available
    for creating new profiles.

    Returns:
        List of builtin ProfileTemplate objects

    Example:
        >>> templates = get_builtin_templates()
        >>> for t in templates:
        ...     print(t.name)
        Default
        Kids
        Work
        Testing
    """
    return [
        ProfileTemplate(
            name="Default",
            description="Standard profile with balanced settings for general gaming",
            settings=ProfileSettings(
                theme="default",
                language="en",
                default_view="grid",
                grid_size=200,
                auto_update_library=True,
                enabled_sources=["steam", "epic", "gog"],
            ),
            sharing=ProfileSharing(
                mode=DataSharingMode.NONE,
            ),
            is_builtin=True,
        ),
        ProfileTemplate(
            name="Kids",
            description="Safe profile for children with restricted content and sources",
            settings=ProfileSettings(
                theme="default",
                language="en",
                default_view="grid",
                grid_size=250,  # Larger grid for easier selection
                show_hidden_games=False,
                auto_update_library=False,  # Manual control
                enabled_sources=[],  # Start with no sources, add manually
            ),
            sharing=ProfileSharing(
                mode=DataSharingMode.READ_ONLY,
                share_metadata_cache=True,  # Share downloaded metadata
                share_media_files=True,  # Share images
            ),
            is_builtin=True,
        ),
        ProfileTemplate(
            name="Work",
            description="Professional profile with minimal distractions",
            settings=ProfileSettings(
                theme="default",
                language="en",
                default_view="list",  # Compact view
                grid_size=150,
                show_hidden_games=False,
                auto_update_library=False,
                enabled_sources=[],  # No automatic sources
            ),
            sharing=ProfileSharing(
                mode=DataSharingMode.NONE,
            ),
            is_builtin=True,
        ),
        ProfileTemplate(
            name="Testing",
            description="Profile for testing games and configurations",
            settings=ProfileSettings(
                theme="default",
                language="en",
                default_view="details",
                grid_size=200,
                show_hidden_games=True,  # Show all games
                auto_update_library=True,
                enabled_sources=["steam", "epic", "gog", "manual"],
            ),
            sharing=ProfileSharing(
                mode=DataSharingMode.BIDIRECTIONAL,
                share_categories=True,
                share_tags=True,
                share_metadata_cache=True,
                share_media_files=True,
            ),
            is_builtin=True,
        ),
        ProfileTemplate(
            name="Family",
            description="Shared family profile with content for all ages",
            settings=ProfileSettings(
                theme="default",
                language="en",
                default_view="grid",
                grid_size=220,
                show_hidden_games=False,
                auto_update_library=True,
                enabled_sources=["steam", "epic", "gog"],
            ),
            sharing=ProfileSharing(
                mode=DataSharingMode.SELECTIVE,
                share_categories=True,
                share_tags=True,
                share_metadata_cache=True,
                share_media_files=True,
            ),
            is_builtin=True,
        ),
        ProfileTemplate(
            name="Streaming",
            description="Optimized for game streaming and TV viewing",
            settings=ProfileSettings(
                theme="default",
                language="en",
                default_view="grid",
                grid_size=300,  # Large items for TV viewing
                show_hidden_games=False,
                auto_update_library=True,
                enabled_sources=["steam", "epic", "gog"],
            ),
            sharing=ProfileSharing(
                mode=DataSharingMode.READ_ONLY,
                share_metadata_cache=True,
                share_media_files=True,
            ),
            is_builtin=True,
        ),
    ]


class ProfileTemplateManager:
    """
    Manager for profile templates.

    Handles template retrieval, creation, and management operations.

    Attributes:
        repo: Template repository for database operations

    Example:
        >>> manager = ProfileTemplateManager(repo)
        >>> template = manager.get_template("default")
        >>> profile = manager.create_profile_from_template(template, "My Profile")
    """

    def __init__(self, repo: "ProfileTemplateRepository") -> None:
        """
        Initialize the template manager.

        Args:
            repo: Profile template repository
        """
        self.repo = repo

    def get_template(self, name: str) -> Optional[ProfileTemplate]:
        """
        Get a template by name.

        Args:
            name: Template name (case-insensitive)

        Returns:
            ProfileTemplate if found, None otherwise

        Example:
            >>> template = manager.get_template("default")
        """
        # Try exact match first
        template = self.repo.get_by_name(name)
        if template:
            return template

        # Try case-insensitive match
        for t in self.repo.get_all():
            if t.name.lower() == name.lower():
                return t

        return None

    def get_template_by_id(self, template_id: UUID) -> Optional[ProfileTemplate]:
        """
        Get a template by ID.

        Args:
            template_id: Template UUID

        Returns:
            ProfileTemplate if found, None otherwise
        """
        return self.repo.get_by_id(template_id)

    def list_templates(self) -> list[ProfileTemplate]:
        """
        List all available templates.

        Returns:
            List of all templates (builtin and custom)

        Example:
            >>> templates = manager.list_templates()
        """
        return self.repo.get_all()

    def list_builtin_templates(self) -> list[ProfileTemplate]:
        """
        List only builtin templates.

        Returns:
            List of builtin templates
        """
        return self.repo.get_builtin()

    def list_custom_templates(self) -> list[ProfileTemplate]:
        """
        List only custom (user-created) templates.

        Returns:
            List of custom templates
        """
        return [t for t in self.repo.get_all() if not t.is_builtin]

    def create_template(
        self,
        name: str,
        description: str = "",
        settings: Optional[ProfileSettings] = None,
        sharing: Optional[ProfileSharing] = None,
    ) -> ProfileTemplate:
        """
        Create a new custom template.

        Args:
            name: Unique template name
            description: Template description
            settings: Default settings for profiles created from template
            sharing: Default sharing configuration

        Returns:
            The created template

        Raises:
            ValueError: If template name already exists

        Example:
            >>> template = manager.create_template(
            ...     "My Template",
            ...     description="Custom settings",
            ...     settings=ProfileSettings(theme="dark")
            ... )
        """
        if self.repo.get_by_name(name):
            raise ValueError(f"Template '{name}' already exists")

        template = ProfileTemplate(
            name=name,
            description=description,
            settings=settings or ProfileSettings(),
            sharing=sharing or ProfileSharing(),
            is_builtin=False,
        )

        self.repo.create(template)
        logger.info(f"Created template: {name}")
        return template

    def create_template_from_profile(
        self,
        profile: Profile,
        template_name: str,
        description: Optional[str] = None,
    ) -> ProfileTemplate:
        """
        Create a template from an existing profile.

        Args:
            profile: Source profile
            template_name: Name for the new template
            description: Optional description (defaults to auto-generated)

        Returns:
            The created template

        Raises:
            ValueError: If template name already exists

        Example:
            >>> profile = manager.get_profile("Gaming")
            >>> template = template_mgr.create_template_from_profile(
            ...     profile, "Gaming Template"
            ... )
        """
        if self.repo.get_by_name(template_name):
            raise ValueError(f"Template '{template_name}' already exists")

        template = ProfileTemplate(
            name=template_name,
            description=description or f"Template created from profile '{profile.name}'",
            settings=profile.settings.model_copy(),
            sharing=profile.sharing.model_copy(),
            is_builtin=False,
            source_profile_id=profile.id,
        )

        self.repo.create(template)
        logger.info(f"Created template '{template_name}' from profile '{profile.name}'")
        return template

    def delete_template(self, name: str) -> bool:
        """
        Delete a custom template.

        Builtin templates cannot be deleted.

        Args:
            name: Template name to delete

        Returns:
            True if deleted, False if not found

        Raises:
            ValueError: If trying to delete a builtin template

        Example:
            >>> manager.delete_template("My Template")
        """
        template = self.repo.get_by_name(name)
        if not template:
            return False

        if template.is_builtin:
            raise ValueError(f"Cannot delete builtin template '{name}'")

        self.repo.delete(template.id)
        logger.info(f"Deleted template: {name}")
        return True

    def update_template(
        self,
        name: str,
        description: Optional[str] = None,
        settings: Optional[ProfileSettings] = None,
        sharing: Optional[ProfileSharing] = None,
    ) -> ProfileTemplate:
        """
        Update an existing custom template.

        Builtin templates cannot be modified.

        Args:
            name: Template name to update
            description: New description (if provided)
            settings: New settings (if provided)
            sharing: New sharing configuration (if provided)

        Returns:
            Updated template

        Raises:
            ValueError: If template not found or is builtin

        Example:
            >>> manager.update_template(
            ...     "My Template",
            ...     settings=ProfileSettings(theme="light")
            ... )
        """
        template = self.repo.get_by_name(name)
        if not template:
            raise ValueError(f"Template '{name}' not found")

        if template.is_builtin:
            raise ValueError(f"Cannot modify builtin template '{name}'")

        if description is not None:
            template.description = description
        if settings is not None:
            template.settings = settings
        if sharing is not None:
            template.sharing = sharing

        # Delete and recreate (since templates are immutable in DB)
        self.repo.delete(template.id)
        self.repo.create(template)

        logger.info(f"Updated template: {name}")
        return template
