"""Core game and metadata models."""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, Date, DateTime,
    ForeignKey, Table, Index
)
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


# Association tables for many-to-many relationships
game_platforms = Table(
    'game_platforms',
    Base.metadata,
    Column('game_id', Integer, ForeignKey('games.id', ondelete='CASCADE'), primary_key=True),
    Column('platform_id', Integer, ForeignKey('platforms.id', ondelete='CASCADE'), primary_key=True),
    Index('ix_game_platforms_game_id', 'game_id'),
    Index('ix_game_platforms_platform_id', 'platform_id'),
)

game_genres = Table(
    'game_genres',
    Base.metadata,
    Column('game_id', Integer, ForeignKey('games.id', ondelete='CASCADE'), primary_key=True),
    Column('genre_id', Integer, ForeignKey('genres.id', ondelete='CASCADE'), primary_key=True),
    Index('ix_game_genres_game_id', 'game_id'),
    Index('ix_game_genres_genre_id', 'genre_id'),
)

game_developers = Table(
    'game_developers',
    Base.metadata,
    Column('game_id', Integer, ForeignKey('games.id', ondelete='CASCADE'), primary_key=True),
    Column('developer_id', Integer, ForeignKey('developers.id', ondelete='CASCADE'), primary_key=True),
    Index('ix_game_developers_game_id', 'game_id'),
    Index('ix_game_developers_developer_id', 'developer_id'),
)

game_publishers = Table(
    'game_publishers',
    Base.metadata,
    Column('game_id', Integer, ForeignKey('games.id', ondelete='CASCADE'), primary_key=True),
    Column('publisher_id', Integer, ForeignKey('publishers.id', ondelete='CASCADE'), primary_key=True),
    Index('ix_game_publishers_game_id', 'game_id'),
    Index('ix_game_publishers_publisher_id', 'publisher_id'),
)


class Game(Base, TimestampMixin):
    """Main game model."""

    __tablename__ = 'games'

    id = Column(Integer, primary_key=True)
    name = Column(String(500), nullable=False, index=True)
    sort_name = Column(String(500), index=True)  # For custom sorting
    description = Column(Text)
    notes = Column(Text)  # User notes

    # Dates
    release_date = Column(Date)
    added_date = Column(DateTime, default=datetime.utcnow, index=True)
    modified_date = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_played = Column(DateTime, index=True)

    # Playtime in minutes
    playtime = Column(Integer, default=0)
    play_count = Column(Integer, default=0)

    # Scores and ratings (0-100 or 0-10 scale)
    user_score = Column(Float)
    critic_score = Column(Float)
    community_score = Column(Float)

    # Installation
    install_directory = Column(String(1000))
    install_size = Column(Integer)  # Size in bytes
    is_installed = Column(Boolean, default=False, index=True)

    # Visibility and organization
    is_favorite = Column(Boolean, default=False, index=True)
    is_hidden = Column(Boolean, default=False, index=True)

    # Completion status
    completion_status_id = Column(Integer, ForeignKey('completion_statuses.id'))
    completion_status = relationship('CompletionStatus', back_populates='games')

    # Relationships
    platforms = relationship('Platform', secondary=game_platforms, back_populates='games')
    genres = relationship('Genre', secondary=game_genres, back_populates='games')
    developers = relationship('Developer', secondary=game_developers, back_populates='games')
    publishers = relationship('Publisher', secondary=game_publishers, back_populates='games')

    categories = relationship('Category', secondary='game_categories', back_populates='games')
    tags = relationship('Tag', secondary='game_tags', back_populates='games')
    collections = relationship('Collection', secondary='game_collections', back_populates='games')

    # Indexes for performance
    __table_args__ = (
        Index('ix_games_name_lower', 'name'),
        Index('ix_games_favorite_hidden', 'is_favorite', 'is_hidden'),
        Index('ix_games_playtime', 'playtime'),
        Index('ix_games_release_date', 'release_date'),
    )

    def __repr__(self):
        return f"<Game(id={self.id}, name='{self.name}')>"


class Platform(Base, TimestampMixin):
    """Game platform (PC, PS5, Xbox, etc.)."""

    __tablename__ = 'platforms'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True, index=True)
    icon = Column(String(500))

    games = relationship('Game', secondary=game_platforms, back_populates='platforms')

    def __repr__(self):
        return f"<Platform(id={self.id}, name='{self.name}')>"


class Genre(Base, TimestampMixin):
    """Game genre."""

    __tablename__ = 'genres'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True, index=True)

    games = relationship('Game', secondary=game_genres, back_populates='genres')

    def __repr__(self):
        return f"<Genre(id={self.id}, name='{self.name}')>"


class Developer(Base, TimestampMixin):
    """Game developer."""

    __tablename__ = 'developers'

    id = Column(Integer, primary_key=True)
    name = Column(String(300), nullable=False, unique=True, index=True)

    games = relationship('Game', secondary=game_developers, back_populates='developers')

    def __repr__(self):
        return f"<Developer(id={self.id}, name='{self.name}')>"


class Publisher(Base, TimestampMixin):
    """Game publisher."""

    __tablename__ = 'publishers'

    id = Column(Integer, primary_key=True)
    name = Column(String(300), nullable=False, unique=True, index=True)

    games = relationship('Game', secondary=game_publishers, back_populates='publishers')

    def __repr__(self):
        return f"<Publisher(id={self.id}, name='{self.name}')>"
