"""Organization models for categories, tags, and collections."""

import json
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, Table, Index
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


# Association tables
game_categories = Table(
    'game_categories',
    Base.metadata,
    Column('game_id', Integer, ForeignKey('games.id', ondelete='CASCADE'), primary_key=True),
    Column('category_id', Integer, ForeignKey('categories.id', ondelete='CASCADE'), primary_key=True),
    Index('ix_game_categories_game_id', 'game_id'),
    Index('ix_game_categories_category_id', 'category_id'),
)

game_tags = Table(
    'game_tags',
    Base.metadata,
    Column('game_id', Integer, ForeignKey('games.id', ondelete='CASCADE'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
    Index('ix_game_tags_game_id', 'game_id'),
    Index('ix_game_tags_tag_id', 'tag_id'),
)

game_collections = Table(
    'game_collections',
    Base.metadata,
    Column('game_id', Integer, ForeignKey('games.id', ondelete='CASCADE'), primary_key=True),
    Column('collection_id', Integer, ForeignKey('collections.id', ondelete='CASCADE'), primary_key=True),
    Index('ix_game_collections_game_id', 'game_id'),
    Index('ix_game_collections_collection_id', 'collection_id'),
)


class Category(Base, TimestampMixin):
    """User-defined category for organizing games."""

    __tablename__ = 'categories'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True, index=True)
    description = Column(Text)
    color = Column(String(50))  # Hex color code

    games = relationship('Game', secondary=game_categories, back_populates='categories')

    def __repr__(self):
        return f"<Category(id={self.id}, name='{self.name}')>"


class Tag(Base, TimestampMixin):
    """User-defined tag for games."""

    __tablename__ = 'tags'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True, index=True)

    games = relationship('Game', secondary=game_tags, back_populates='tags')

    def __repr__(self):
        return f"<Tag(id={self.id}, name='{self.name}')>"


class Collection(Base, TimestampMixin):
    """Collection of games, can be manual or smart (rule-based)."""

    __tablename__ = 'collections'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True, index=True)
    description = Column(Text)
    is_smart = Column(Boolean, default=False, index=True)

    # For smart collections: JSON-encoded filter rules
    # Example: {"filters": [{"field": "genre", "operator": "contains", "value": "RPG"}]}
    rules = Column(Text)

    games = relationship('Game', secondary=game_collections, back_populates='collections')

    def get_rules(self):
        """Parse rules from JSON."""
        if self.rules:
            return json.loads(self.rules)
        return {}

    def set_rules(self, rules_dict):
        """Set rules as JSON."""
        self.rules = json.dumps(rules_dict)

    def __repr__(self):
        return f"<Collection(id={self.id}, name='{self.name}', smart={self.is_smart})>"
