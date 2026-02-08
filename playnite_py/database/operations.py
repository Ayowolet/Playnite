"""Database operations for games and library management."""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from ..models import (
    Game, Platform, Genre, Category, Tag, Collection, CompletionStatus
)
from ..validation import (
    validate_game_name, validate_string_field, validate_playtime,
    validate_rating, ValidationError
)

logger = logging.getLogger(__name__)


class GameOperations:
    """Operations for managing games in the database."""

    def __init__(self, session: Session):
        self.session = session

    def create_game(self, name: str, **kwargs) -> Game:
        """Create a new game with validated inputs."""
        try:
            # Validate required fields
            name = validate_game_name(name)

            # Validate optional string fields if provided
            if 'description' in kwargs:
                kwargs['description'] = validate_string_field(
                    kwargs['description'], 'Description', max_length=2000, allow_empty=True, allow_none=True
                )
            if 'notes' in kwargs:
                kwargs['notes'] = validate_string_field(
                    kwargs['notes'], 'Notes', max_length=5000, allow_empty=True, allow_none=True
                )
            if 'install_directory' in kwargs:
                kwargs['install_directory'] = validate_string_field(
                    kwargs['install_directory'], 'Install directory', max_length=500, allow_none=True
                )

            # Validate numeric fields
            if 'playtime' in kwargs:
                kwargs['playtime'] = validate_playtime(kwargs['playtime'])
            if 'user_score' in kwargs:
                kwargs['user_score'] = validate_rating(kwargs['user_score'], 'User score')
            if 'critic_score' in kwargs:
                kwargs['critic_score'] = validate_rating(kwargs['critic_score'], 'Critic score')
            if 'community_score' in kwargs:
                kwargs['community_score'] = validate_rating(kwargs['community_score'], 'Community score')

            game = Game(name=name, **kwargs)
            self.session.add(game)
            self.session.commit()
            logger.info(f"Created game: {name} (ID: {game.id})")
            return game
        except ValidationError as e:
            logger.error(f"Validation error creating game: {e}")
            raise

    def get_game(self, game_id: int) -> Optional[Game]:
        """Get a game by ID."""
        return self.session.query(Game).filter(Game.id == game_id).first()

    def get_game_by_name(self, name: str) -> Optional[Game]:
        """Get a game by exact name match."""
        return self.session.query(Game).filter(Game.name == name).first()

    def get_all_games(self) -> List[Game]:
        """Get all games."""
        return self.session.query(Game).all()

    def update_game(self, game_id: int, **kwargs) -> Optional[Game]:
        """Update a game with validated inputs."""
        game = self.get_game(game_id)
        if not game:
            logger.warning(f"Attempted to update non-existent game ID: {game_id}")
            return None

        try:
            # Validate fields before applying updates
            validated_kwargs = {}

            for key, value in kwargs.items():
                if key == 'name':
                    validated_kwargs[key] = validate_game_name(value)
                elif key in ['description', 'notes', 'install_directory']:
                    max_len = {'description': 2000, 'notes': 5000, 'install_directory': 500}.get(key, 500)
                    validated_kwargs[key] = validate_string_field(
                        value, key.replace('_', ' ').title(), max_length=max_len, allow_none=True
                    )
                elif key == 'playtime':
                    validated_kwargs[key] = validate_playtime(value)
                elif key in ['user_score', 'critic_score', 'community_score']:
                    validated_kwargs[key] = validate_rating(value, key.replace('_', ' ').title())
                else:
                    # Pass through unvalidated (for relationships, dates, etc.)
                    validated_kwargs[key] = value

            for key, value in validated_kwargs.items():
                setattr(game, key, value)

            game.modified_date = datetime.utcnow()
            self.session.commit()
            logger.info(f"Updated game: {game.name} (ID: {game_id})")
            return game
        except ValidationError as e:
            logger.error(f"Validation error updating game {game_id}: {e}")
            raise

    def delete_game(self, game_id: int) -> bool:
        """Delete a game."""
        game = self.get_game(game_id)
        if game:
            self.session.delete(game)
            self.session.commit()
            return True
        return False

    def _add_relationship_to_game(self, game_id: int, entity_name: str,
                                   entity_class: type, relationship_attr: str) -> bool:
        """
        Generic method to add a relationship entity to a game.

        Args:
            game_id: ID of the game
            entity_name: Name of the entity to add (e.g., "Action" for a genre)
            entity_class: The model class (e.g., Genre, Platform, Tag)
            relationship_attr: Name of the relationship attribute on Game (e.g., 'genres', 'platforms')

        Returns:
            True if successful, False if game not found
        """
        try:
            entity_name = validate_string_field(
                entity_name, f'{entity_class.__name__} name', max_length=200, allow_empty=False
            )

            game = self.get_game(game_id)
            if not game:
                logger.warning(f"Attempted to add {entity_class.__name__} to non-existent game ID: {game_id}")
                return False

            # Query for existing entity
            entity = self.session.query(entity_class).filter(
                entity_class.name == entity_name
            ).first()

            # Create if doesn't exist
            if not entity:
                entity = entity_class(name=entity_name)
                self.session.add(entity)

            # Get the relationship collection from the game
            relationship_collection = getattr(game, relationship_attr)

            # Add if not already present
            if entity not in relationship_collection:
                relationship_collection.append(entity)
                self.session.commit()
                logger.info(f"Added {entity_class.__name__.lower()} '{entity_name}' to game '{game.name}'")

            return True
        except ValidationError as e:
            logger.error(f"Validation error adding {entity_class.__name__} to game {game_id}: {e}")
            raise

    def add_platform_to_game(self, game_id: int, platform_name: str) -> bool:
        """Add a platform to a game with validated input."""
        return self._add_relationship_to_game(game_id, platform_name, Platform, 'platforms')

    def add_genre_to_game(self, game_id: int, genre_name: str) -> bool:
        """Add a genre to a game with validated input."""
        return self._add_relationship_to_game(game_id, genre_name, Genre, 'genres')

    def add_tag_to_game(self, game_id: int, tag_name: str) -> bool:
        """Add a tag to a game with validated input."""
        return self._add_relationship_to_game(game_id, tag_name, Tag, 'tags')

    def add_category_to_game(self, game_id: int, category_name: str) -> bool:
        """Add a category to a game with validated input."""
        return self._add_relationship_to_game(game_id, category_name, Category, 'categories')

    def set_completion_status(self, game_id: int, status_name: str) -> bool:
        """Set completion status for a game with validated input."""
        try:
            status_name = validate_string_field(
                status_name, 'Completion status name', max_length=200, allow_empty=False
            )

            game = self.get_game(game_id)
            if not game:
                logger.warning(f"Attempted to set completion status for non-existent game ID: {game_id}")
                return False

            status = self.session.query(CompletionStatus).filter(
                CompletionStatus.name == status_name
            ).first()
            if not status:
                status = CompletionStatus(name=status_name)
                self.session.add(status)
                self.session.commit()

            game.completion_status = status
            self.session.commit()
            logger.info(f"Set completion status '{status_name}' for game '{game.name}'")
            return True
        except ValidationError as e:
            logger.error(f"Validation error setting completion status for game {game_id}: {e}")
            raise

    def toggle_favorite(self, game_id: int) -> Optional[bool]:
        """Toggle favorite status of a game."""
        game = self.get_game(game_id)
        if game:
            game.is_favorite = not game.is_favorite
            self.session.commit()
            return game.is_favorite
        return None

    def toggle_hidden(self, game_id: int) -> Optional[bool]:
        """Toggle hidden status of a game."""
        game = self.get_game(game_id)
        if game:
            game.is_hidden = not game.is_hidden
            self.session.commit()
            return game.is_hidden
        return None

    def bulk_update(self, game_ids: List[int], updates: Dict[str, Any]) -> int:
        """
        Apply updates to multiple games.

        Args:
            game_ids: List of game IDs to update
            updates: Dictionary of field names to values

        Returns:
            Number of games updated
        """
        count = 0
        for game_id in game_ids:
            game = self.get_game(game_id)
            if game:
                for key, value in updates.items():
                    setattr(game, key, value)
                game.modified_date = datetime.utcnow()
                count += 1
        self.session.commit()
        return count

    def bulk_add_tags(self, game_ids: List[int], tag_names: List[str]) -> int:
        """Add tags to multiple games."""
        count = 0
        for tag_name in tag_names:
            tag = self.session.query(Tag).filter(Tag.name == tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                self.session.add(tag)

        self.session.flush()

        for game_id in game_ids:
            game = self.get_game(game_id)
            if game:
                for tag_name in tag_names:
                    tag = self.session.query(Tag).filter(Tag.name == tag_name).first()
                    if tag and tag not in game.tags:
                        game.tags.append(tag)
                count += 1

        self.session.commit()
        return count


class LibraryOperations:
    """Operations for managing library metadata (platforms, genres, tags, etc.)."""

    def __init__(self, session: Session):
        self.session = session

    # Platform operations
    def create_platform(self, name: str, icon: Optional[str] = None) -> Platform:
        """Create a new platform with validated inputs."""
        try:
            name = validate_string_field(name, 'Platform name', max_length=200, allow_empty=False)
            if icon:
                icon = validate_string_field(icon, 'Platform icon', max_length=500, allow_none=True)

            platform = Platform(name=name, icon=icon)
            self.session.add(platform)
            self.session.commit()
            logger.info(f"Created platform: {name} (ID: {platform.id})")
            return platform
        except ValidationError as e:
            logger.error(f"Validation error creating platform: {e}")
            raise

    def get_all_platforms(self) -> List[Platform]:
        """Get all platforms."""
        return self.session.query(Platform).all()

    # Genre operations
    def create_genre(self, name: str) -> Genre:
        """Create a new genre with validated inputs."""
        try:
            name = validate_string_field(name, 'Genre name', max_length=200, allow_empty=False)

            genre = Genre(name=name)
            self.session.add(genre)
            self.session.commit()
            logger.info(f"Created genre: {name} (ID: {genre.id})")
            return genre
        except ValidationError as e:
            logger.error(f"Validation error creating genre: {e}")
            raise

    def get_all_genres(self) -> List[Genre]:
        """Get all genres."""
        return self.session.query(Genre).all()

    # Tag operations
    def create_tag(self, name: str) -> Tag:
        """Create a new tag with validated inputs."""
        try:
            name = validate_string_field(name, 'Tag name', max_length=200, allow_empty=False)

            tag = Tag(name=name)
            self.session.add(tag)
            self.session.commit()
            logger.info(f"Created tag: {name} (ID: {tag.id})")
            return tag
        except ValidationError as e:
            logger.error(f"Validation error creating tag: {e}")
            raise

    def get_all_tags(self) -> List[Tag]:
        """Get all tags."""
        return self.session.query(Tag).all()

    def get_tag_by_name(self, name: str) -> Optional[Tag]:
        """Get tag by name."""
        return self.session.query(Tag).filter(Tag.name == name).first()

    def delete_tag(self, tag_id: int) -> bool:
        """Delete a tag."""
        tag = self.session.query(Tag).filter(Tag.id == tag_id).first()
        if tag:
            self.session.delete(tag)
            self.session.commit()
            return True
        return False

    # Category operations
    def create_category(self, name: str, description: Optional[str] = None,
                        color: Optional[str] = None) -> Category:
        """Create a new category with validated inputs."""
        try:
            name = validate_string_field(name, 'Category name', max_length=200, allow_empty=False)
            if description:
                description = validate_string_field(
                    description, 'Category description', max_length=1000, allow_none=True
                )
            if color:
                color = validate_string_field(color, 'Category color', max_length=50, allow_none=True)

            category = Category(name=name, description=description, color=color)
            self.session.add(category)
            self.session.commit()
            logger.info(f"Created category: {name} (ID: {category.id})")
            return category
        except ValidationError as e:
            logger.error(f"Validation error creating category: {e}")
            raise

    def get_all_categories(self) -> List[Category]:
        """Get all categories."""
        return self.session.query(Category).all()

    def get_category_by_name(self, name: str) -> Optional[Category]:
        """Get category by name."""
        return self.session.query(Category).filter(Category.name == name).first()

    def delete_category(self, category_id: int) -> bool:
        """Delete a category."""
        category = self.session.query(Category).filter(Category.id == category_id).first()
        if category:
            self.session.delete(category)
            self.session.commit()
            return True
        return False

    # Collection operations
    def create_collection(self, name: str, description: Optional[str] = None,
                          is_smart: bool = False, rules: Optional[Dict] = None) -> Collection:
        """Create a new collection with validated inputs."""
        try:
            name = validate_string_field(name, 'Collection name', max_length=200, allow_empty=False)
            if description:
                description = validate_string_field(
                    description, 'Collection description', max_length=1000, allow_none=True
                )

            collection = Collection(name=name, description=description, is_smart=is_smart)
            if rules:
                collection.set_rules(rules)
            self.session.add(collection)
            self.session.commit()
            logger.info(f"Created collection: {name} (ID: {collection.id})")
            return collection
        except ValidationError as e:
            logger.error(f"Validation error creating collection: {e}")
            raise

    def get_all_collections(self) -> List[Collection]:
        """Get all collections."""
        return self.session.query(Collection).all()

    def get_collection(self, collection_id: int) -> Optional[Collection]:
        """Get collection by ID."""
        return self.session.query(Collection).filter(Collection.id == collection_id).first()

    def delete_collection(self, collection_id: int) -> bool:
        """Delete a collection."""
        collection = self.session.query(Collection).filter(Collection.id == collection_id).first()
        if collection:
            self.session.delete(collection)
            self.session.commit()
            return True
        return False

    # Completion status operations
    def create_completion_status(self, name: str, description: Optional[str] = None) -> CompletionStatus:
        """Create a new completion status with validated inputs."""
        try:
            name = validate_string_field(name, 'Completion status name', max_length=200, allow_empty=False)
            if description:
                description = validate_string_field(
                    description, 'Completion status description', max_length=1000, allow_none=True
                )

            status = CompletionStatus(name=name, description=description)
            self.session.add(status)
            self.session.commit()
            logger.info(f"Created completion status: {name} (ID: {status.id})")
            return status
        except ValidationError as e:
            logger.error(f"Validation error creating completion status: {e}")
            raise

    def get_all_completion_statuses(self) -> List[CompletionStatus]:
        """Get all completion statuses."""
        return self.session.query(CompletionStatus).all()
