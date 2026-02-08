"""Smart collections that auto-update based on rules."""

from typing import List, Dict, Any
from sqlalchemy.orm import Session

from ..models import Collection, Game
from .filter import GameFilter


class SmartCollectionManager:
    """Manager for smart collections with auto-update functionality."""

    def __init__(self, session: Session, auto_update: bool = True):
        """
        Initialize smart collection manager.

        Args:
            session: SQLAlchemy session
            auto_update: Whether automatic updates are enabled (for event handlers)
        """
        self.session = session
        self.game_filter = GameFilter(session)
        self.auto_update_enabled = auto_update

    def create_smart_collection(self, name: str, rules: Dict[str, Any],
                                 description: str = None) -> Collection:
        """
        Create a new smart collection with filter rules.

        Args:
            name: Collection name
            rules: Filter rules dictionary
            description: Optional description

        Returns:
            Created collection
        """
        collection = Collection(
            name=name,
            description=description,
            is_smart=True
        )
        collection.set_rules(rules)
        self.session.add(collection)
        self.session.commit()

        # Populate with matching games
        self.update_smart_collection(collection.id)

        return collection

    def update_smart_collection(self, collection_id: int) -> int:
        """
        Update a smart collection by re-evaluating rules.

        Args:
            collection_id: ID of collection to update

        Returns:
            Number of games in collection after update
        """
        collection = self.session.query(Collection).filter(
            Collection.id == collection_id
        ).first()

        if not collection or not collection.is_smart:
            return 0

        # Get rules and find matching games
        rules = collection.get_rules()
        matching_games = self.game_filter.filter_games(rules)

        # Clear existing games and add new ones
        collection.games.clear()
        collection.games.extend(matching_games)
        self.session.commit()

        return len(matching_games)

    def update_all_smart_collections(self) -> Dict[str, int]:
        """
        Update all smart collections.

        Returns:
            Dictionary mapping collection names to game counts
        """
        collections = self.session.query(Collection).filter(
            Collection.is_smart
        ).all()

        results = {}
        for collection in collections:
            count = self.update_smart_collection(collection.id)
            results[collection.name] = count

        return results

    def get_smart_collection_preview(self, rules: Dict[str, Any]) -> List[Game]:
        """
        Preview games that would match smart collection rules.

        Args:
            rules: Filter rules dictionary

        Returns:
            List of matching games
        """
        return self.game_filter.filter_games(rules)

    def modify_smart_collection_rules(self, collection_id: int,
                                       new_rules: Dict[str, Any]) -> int:
        """
        Modify rules of a smart collection and update it.

        Args:
            collection_id: ID of collection to modify
            new_rules: New filter rules

        Returns:
            Number of games after update
        """
        collection = self.session.query(Collection).filter(
            Collection.id == collection_id
        ).first()

        if not collection or not collection.is_smart:
            return 0

        collection.set_rules(new_rules)
        self.session.commit()

        return self.update_smart_collection(collection_id)

    def get_collections_with_rule_type(self, rule_type: str) -> List[Collection]:
        """
        Get smart collections that use a specific rule type.

        Args:
            rule_type: Rule type to search for (e.g., 'platforms', 'genres', 'tags')

        Returns:
            List of collections using this rule type
        """
        collections = self.session.query(Collection).filter(
            Collection.is_smart
        ).all()

        matching = []
        for collection in collections:
            rules = collection.get_rules()
            if rule_type in rules:
                matching.append(collection)

        return matching

    def update_collections_batch(self, collection_ids: List[int]) -> Dict[int, int]:
        """
        Update multiple collections in a batch.

        Args:
            collection_ids: List of collection IDs to update

        Returns:
            Dictionary mapping collection ID to game count
        """
        results = {}
        for collection_id in collection_ids:
            count = self.update_smart_collection(collection_id)
            results[collection_id] = count

        return results
