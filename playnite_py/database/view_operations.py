"""View configuration operations for managing view presets."""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from ..models import ViewConfig


class ViewConfigOperations:
    """Operations for managing view configurations/presets."""

    def __init__(self, session: Session):
        self.session = session

    def create_view_config(self, name: str, description: Optional[str] = None,
                           view_mode: str = 'grid', grid_size: str = 'medium',
                           sort_field: str = 'name', sort_direction: str = 'asc',
                           group_by: Optional[str] = None,
                           display_settings: Optional[Dict[str, Any]] = None,
                           filter_preset_id: Optional[int] = None,
                           is_big_picture_mode: bool = False) -> ViewConfig:
        """
        Create a new view configuration preset.

        Args:
            name: Unique name for the preset
            description: Optional description
            view_mode: View mode (grid, list, details)
            grid_size: Grid size (small, medium, large, extra_large)
            sort_field: Field to sort by
            sort_direction: Sort direction (asc, desc)
            group_by: Field to group by (optional)
            display_settings: Dictionary of display settings
            filter_preset_id: Optional filter preset to link
            is_big_picture_mode: Whether this is for big picture mode

        Returns:
            Created ViewConfig
        """
        config = ViewConfig(
            name=name,
            description=description,
            view_mode=view_mode,
            grid_size=grid_size,
            sort_field=sort_field,
            sort_direction=sort_direction,
            group_by=group_by,
            filter_preset_id=filter_preset_id,
            is_big_picture_mode=is_big_picture_mode
        )

        if display_settings:
            config.set_display_settings(display_settings)

        self.session.add(config)
        self.session.commit()
        return config

    def get_view_config(self, config_id: int) -> Optional[ViewConfig]:
        """Get view configuration by ID."""
        return self.session.query(ViewConfig).filter(ViewConfig.id == config_id).first()

    def get_view_config_by_name(self, name: str) -> Optional[ViewConfig]:
        """Get view configuration by name."""
        return self.session.query(ViewConfig).filter(ViewConfig.name == name).first()

    def get_all_view_configs(self, big_picture_only: bool = False) -> List[ViewConfig]:
        """
        Get all view configurations.

        Args:
            big_picture_only: If True, only return big picture mode configs

        Returns:
            List of view configurations
        """
        query = self.session.query(ViewConfig)

        if big_picture_only:
            query = query.filter(ViewConfig.is_big_picture_mode)

        return query.order_by(ViewConfig.name).all()

    def update_view_config(self, config_id: int, **kwargs) -> Optional[ViewConfig]:
        """
        Update a view configuration.

        Args:
            config_id: ID of configuration to update
            **kwargs: Fields to update

        Returns:
            Updated configuration or None if not found
        """
        config = self.get_view_config(config_id)
        if not config:
            return None

        # Handle display_settings specially
        if 'display_settings' in kwargs:
            config.set_display_settings(kwargs.pop('display_settings'))

        # Update other fields
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)

        self.session.commit()
        return config

    def delete_view_config(self, config_id: int) -> bool:
        """
        Delete a view configuration.

        Args:
            config_id: ID of configuration to delete

        Returns:
            True if deleted, False if not found
        """
        config = self.get_view_config(config_id)
        if config:
            self.session.delete(config)
            self.session.commit()
            return True
        return False

    def apply_view_config(self, config_id: int) -> Optional[Dict[str, Any]]:
        """
        Get view configuration as dictionary for applying to UI/navigation.

        Args:
            config_id: ID of configuration to apply

        Returns:
            Configuration dictionary or None if not found
        """
        config = self.get_view_config(config_id)
        if not config:
            return None

        result = {
            'view_mode': config.view_mode,
            'grid_size': config.grid_size,
            'sort_field': config.sort_field,
            'sort_direction': config.sort_direction,
            'group_by': config.group_by,
            'filter_preset_id': config.filter_preset_id,
            'is_big_picture_mode': config.is_big_picture_mode,
            'display_settings': config.get_display_settings()
        }

        return result
