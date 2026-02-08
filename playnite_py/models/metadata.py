"""Metadata models for filters, views, and completion status."""

import json
from sqlalchemy import Column, Integer, String, Text, Boolean
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class FilterPreset(Base, TimestampMixin):
    """Saved filter configuration."""

    __tablename__ = 'filter_presets'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True, index=True)
    description = Column(Text)

    # JSON-encoded filter configuration
    # Example: {
    #   "platforms": ["PC", "PS5"],
    #   "genres": ["RPG"],
    #   "release_year_min": 2020,
    #   "playtime_min": 600,
    #   "completion_status": ["completed"]
    # }
    filters = Column(Text, nullable=False)

    def get_filters(self):
        """Parse filters from JSON."""
        return json.loads(self.filters)

    def set_filters(self, filters_dict):
        """Set filters as JSON."""
        self.filters = json.dumps(filters_dict)

    def __repr__(self):
        return f"<FilterPreset(id={self.id}, name='{self.name}')>"


class ViewConfig(Base, TimestampMixin):
    """Saved view configuration including sort, group, and display settings."""

    __tablename__ = 'view_configs'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True, index=True)
    description = Column(Text)

    # View mode: grid, list, details
    view_mode = Column(String(50), default='grid')

    # Grid settings
    grid_size = Column(String(50), default='medium')  # small, medium, large, extra_large

    # Sort settings
    sort_field = Column(String(100), default='name')
    sort_direction = Column(String(10), default='asc')

    # Group settings
    group_by = Column(String(100))  # platform, genre, category, etc.

    # JSON-encoded additional display settings
    # Example: {
    #   "show_covers": true,
    #   "show_playtime": true,
    #   "columns": ["name", "platform", "playtime", "last_played"]
    # }
    display_settings = Column(Text)

    # Associated filter preset
    filter_preset_id = Column(Integer)

    # Big Picture mode specific settings
    is_big_picture_mode = Column(Boolean, default=False)

    def get_display_settings(self):
        """Parse display settings from JSON."""
        if self.display_settings:
            return json.loads(self.display_settings)
        return {}

    def set_display_settings(self, settings_dict):
        """Set display settings as JSON."""
        self.display_settings = json.dumps(settings_dict)

    def __repr__(self):
        return f"<ViewConfig(id={self.id}, name='{self.name}', mode='{self.view_mode}')>"


class CompletionStatus(Base, TimestampMixin):
    """Game completion status."""

    __tablename__ = 'completion_statuses'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text)

    games = relationship('Game', back_populates='completion_status')

    def __repr__(self):
        return f"<CompletionStatus(id={self.id}, name='{self.name}')>"
