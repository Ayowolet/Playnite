"""Bulk operations for managing multiple games at once."""

from typing import List, Any
from sqlalchemy.orm import Session
from sqlalchemy import insert, delete, update
from datetime import datetime

from ..models import Game, Tag, Category, CompletionStatus
from ..models.organisation import game_tags, game_categories


class BulkOperations:
    """Perform operations on multiple games efficiently."""

    def __init__(self, session: Session):
        self.session = session

    def bulk_add_tags(self, game_ids: List[int], tag_names: List[str]) -> int:
        """
        Add tags to multiple games using batch SQL.

        Args:
            game_ids: List of game IDs
            tag_names: List of tag names to add

        Returns:
            Number of games updated
        """
        if not game_ids or not tag_names:
            return 0

        # Ensure all tags exist - use batch query to avoid N+1
        existing_tags = self.session.query(Tag).filter(Tag.name.in_(tag_names)).all()
        existing_tag_map = {tag.name: tag for tag in existing_tags}

        for tag_name in tag_names:
            tag = existing_tag_map.get(tag_name)
            if not tag:
                tag = Tag(name=tag_name)
                self.session.add(tag)
                existing_tag_map[tag_name] = tag

        # Flush to get IDs for new tags
        if len(existing_tags) < len(tag_names):
            self.session.flush()

        # Now collect tag IDs after flush
        tag_ids = [existing_tag_map[tag_name].id for tag_name in tag_names]

        # Get existing associations to avoid duplicates
        existing = self.session.execute(
            game_tags.select().where(
                game_tags.c.game_id.in_(game_ids),
                game_tags.c.tag_id.in_(tag_ids)
            )
        ).fetchall()
        existing_pairs = {(row.game_id, row.tag_id) for row in existing}

        # Prepare batch inserts
        values_to_insert = [
            {'game_id': game_id, 'tag_id': tag_id}
            for game_id in game_ids
            for tag_id in tag_ids
            if (game_id, tag_id) not in existing_pairs
        ]

        if values_to_insert:
            self.session.execute(insert(game_tags), values_to_insert)

        # Update modified_date for affected games
        self.session.execute(
            update(Game)
            .where(Game.id.in_(game_ids))
            .values(modified_date=datetime.utcnow())
        )

        self.session.commit()
        return len(game_ids)

    def bulk_remove_tags(self, game_ids: List[int], tag_names: List[str]) -> int:
        """
        Remove tags from multiple games using batch SQL.

        Args:
            game_ids: List of game IDs
            tag_names: List of tag names to remove

        Returns:
            Number of games updated
        """
        if not game_ids or not tag_names:
            return 0

        # Get tag IDs
        tags = self.session.query(Tag).filter(Tag.name.in_(tag_names)).all()
        if not tags:
            return 0

        tag_ids = [tag.id for tag in tags]

        # Batch delete associations
        self.session.execute(
            delete(game_tags).where(
                game_tags.c.game_id.in_(game_ids),
                game_tags.c.tag_id.in_(tag_ids)
            )
        )

        # Update modified_date for affected games
        self.session.execute(
            update(Game)
            .where(Game.id.in_(game_ids))
            .values(modified_date=datetime.utcnow())
        )

        self.session.commit()
        return len(game_ids)

    def bulk_add_categories(self, game_ids: List[int], category_names: List[str]) -> int:
        """
        Add categories to multiple games using batch SQL.

        Args:
            game_ids: List of game IDs
            category_names: List of category names to add

        Returns:
            Number of games updated
        """
        if not game_ids or not category_names:
            return 0

        # Ensure all categories exist - use batch query to avoid N+1
        existing_categories = self.session.query(Category).filter(
            Category.name.in_(category_names)
        ).all()
        existing_category_map = {cat.name: cat for cat in existing_categories}

        for category_name in category_names:
            category = existing_category_map.get(category_name)
            if not category:
                category = Category(name=category_name)
                self.session.add(category)
                existing_category_map[category_name] = category

        # Flush to get IDs for new categories
        if len(existing_categories) < len(category_names):
            self.session.flush()

        # Now collect category IDs after flush
        category_ids = [existing_category_map[category_name].id for category_name in category_names]

        # Get existing associations to avoid duplicates
        existing = self.session.execute(
            game_categories.select().where(
                game_categories.c.game_id.in_(game_ids),
                game_categories.c.category_id.in_(category_ids)
            )
        ).fetchall()
        existing_pairs = {(row.game_id, row.category_id) for row in existing}

        # Prepare batch inserts
        values_to_insert = [
            {'game_id': game_id, 'category_id': category_id}
            for game_id in game_ids
            for category_id in category_ids
            if (game_id, category_id) not in existing_pairs
        ]

        if values_to_insert:
            self.session.execute(insert(game_categories), values_to_insert)

        # Update modified_date for affected games
        self.session.execute(
            update(Game)
            .where(Game.id.in_(game_ids))
            .values(modified_date=datetime.utcnow())
        )

        self.session.commit()
        return len(game_ids)

    def bulk_set_completion_status(self, game_ids: List[int], status_name: str) -> int:
        """
        Set completion status for multiple games using batch SQL.

        Args:
            game_ids: List of game IDs
            status_name: Completion status name

        Returns:
            Number of games updated
        """
        if not game_ids:
            return 0

        status = self.session.query(CompletionStatus).filter(
            CompletionStatus.name == status_name
        ).first()
        if not status:
            status = CompletionStatus(name=status_name)
            self.session.add(status)
            self.session.flush()

        # Batch update
        count = self.session.execute(
            update(Game)
            .where(Game.id.in_(game_ids))
            .values(
                completion_status_id=status.id,
                modified_date=datetime.utcnow()
            )
        ).rowcount

        self.session.commit()
        return count

    def bulk_update_field(self, game_ids: List[int], field: str, value: Any) -> int:
        """
        Update a single field for multiple games using batch SQL.

        Args:
            game_ids: List of game IDs
            field: Field name to update
            value: New value

        Returns:
            Number of games updated
        """
        if not game_ids or not hasattr(Game, field):
            return 0

        # Batch update
        updates = {field: value, 'modified_date': datetime.utcnow()}
        count = self.session.execute(
            update(Game)
            .where(Game.id.in_(game_ids))
            .values(**updates)
        ).rowcount

        self.session.commit()
        return count

    def bulk_set_favorite(self, game_ids: List[int], is_favorite: bool = True) -> int:
        """Set favorite status for multiple games."""
        return self.bulk_update_field(game_ids, 'is_favorite', is_favorite)

    def bulk_set_hidden(self, game_ids: List[int], is_hidden: bool = True) -> int:
        """Set hidden status for multiple games."""
        return self.bulk_update_field(game_ids, 'is_hidden', is_hidden)

    def bulk_delete(self, game_ids: List[int]) -> int:
        """
        Delete multiple games.

        Args:
            game_ids: List of game IDs to delete

        Returns:
            Number of games deleted
        """
        count = self.session.query(Game).filter(Game.id.in_(game_ids)).delete(
            synchronize_session=False
        )
        self.session.commit()
        return count
