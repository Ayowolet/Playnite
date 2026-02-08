"""SQLAlchemy event handlers for automatic smart collection updates."""

from typing import Set
from threading import Lock
from sqlalchemy import event
from sqlalchemy.orm import Session
import logging

from ..models import Game, Collection

logger = logging.getLogger(__name__)


# Map field changes to affected rule types
FIELD_TO_RULE_MAP = {
    'is_favorite': ['is_favorite'],
    'is_hidden': ['is_hidden'],
    'playtime': ['playtime_min', 'playtime_max'],
    'user_score': ['rating_min', 'rating_max'],
    'critic_score': ['rating_min', 'rating_max'],
    'community_score': ['rating_min', 'rating_max'],
    'is_installed': ['is_installed'],
    'completion_status_id': ['completion_statuses'],
}

# Relationship changes that affect collections
RELATIONSHIP_TO_RULE_MAP = {
    'platforms': ['platforms'],
    'genres': ['genres'],
    'tags': ['tags'],
    'categories': ['categories'],
}


class SmartCollectionUpdateQueue:
    """Thread-safe queue for batching smart collection updates."""

    def __init__(self):
        self._queue: Set[int] = set()
        self._lock = Lock()

    def add(self, collection_id: int):
        """Add collection to update queue."""
        with self._lock:
            self._queue.add(collection_id)

    def get_and_clear(self) -> Set[int]:
        """Get all queued collection IDs and clear the queue."""
        with self._lock:
            queued = self._queue.copy()
            self._queue.clear()
            return queued

    def clear(self):
        """Clear the queue."""
        with self._lock:
            self._queue.clear()


class SmartCollectionEventHandler:
    """Handles database events to automatically update smart collections."""

    def __init__(self, session: Session, enabled: bool = True):
        """
        Initialize event handler.

        Args:
            session: SQLAlchemy session
            enabled: Whether auto-updates are enabled
        """
        self.session = session
        self.engine = session.bind  # Store engine for creating new sessions
        self.enabled = enabled
        self.update_queue = SmartCollectionUpdateQueue()
        self._processing = False  # Prevent infinite loops

    def on_game_created(self, mapper, connection, target):
        """Handle game creation - all smart collections might be affected."""
        if not self.enabled or self._processing:
            return

        # New games could match any collection
        self._queue_all_smart_collections()

    def on_game_updated(self, mapper, connection, target):
        """Handle game updates - check which collections are affected."""
        if not self.enabled or self._processing:
            return

        # Get changed attributes
        history = {}

        # Check SQLAlchemy history for changed attributes
        from sqlalchemy import inspect
        insp = inspect(target)

        for attr in insp.attrs:
            hist = attr.load_history()
            if hist.has_changes():
                history[attr.key] = hist

        if not history:
            return

        # Determine which rule types are affected
        affected_rule_types = set()

        for field_name in history.keys():
            if field_name in FIELD_TO_RULE_MAP:
                affected_rule_types.update(FIELD_TO_RULE_MAP[field_name])
            elif field_name in RELATIONSHIP_TO_RULE_MAP:
                affected_rule_types.update(RELATIONSHIP_TO_RULE_MAP[field_name])

        # Queue affected collections
        if affected_rule_types:
            self._queue_collections_by_rule_types(affected_rule_types)

    def on_game_deleted(self, mapper, connection, target):
        """Handle game deletion - all smart collections might be affected."""
        if not self.enabled or self._processing:
            return

        # Deleted games could have been in any collection
        self._queue_all_smart_collections()

    def on_relationship_changed(self, target, value, initiator):
        """Handle relationship changes (tags, genres, etc.)."""
        if not self.enabled or self._processing:
            return

        # Determine relationship type from initiator
        relationship_name = initiator.key

        if relationship_name in RELATIONSHIP_TO_RULE_MAP:
            affected_rule_types = RELATIONSHIP_TO_RULE_MAP[relationship_name]
            self._queue_collections_by_rule_types(affected_rule_types)

    def _queue_all_smart_collections(self):
        """Queue all smart collections for update."""
        try:
            collections = self.session.query(Collection).filter(
                Collection.is_smart
            ).all()

            for collection in collections:
                self.update_queue.add(collection.id)
        except Exception as e:
            logger.error(f"Error queuing smart collections: {e}", exc_info=True)

    def _queue_collections_by_rule_types(self, rule_types: Set[str]):
        """Queue smart collections that use specific rule types."""
        try:
            collections = self.session.query(Collection).filter(
                Collection.is_smart
            ).all()

            for collection in collections:
                rules = collection.get_rules()

                # Check if collection uses any of the affected rule types
                for rule_type in rule_types:
                    if rule_type in rules:
                        self.update_queue.add(collection.id)
                        break
        except Exception as e:
            logger.error(f"Error queuing collections by rule types: {e}", exc_info=True)

    def process_queue(self):
        """Process all queued collection updates."""
        if self._processing:
            return  # Prevent recursion

        self._processing = True
        new_session = None
        try:
            from ..organisation.smart_collections import SmartCollectionManager
            from sqlalchemy.orm import Session

            collection_ids = self.update_queue.get_and_clear()

            if collection_ids:
                # Create a new session for updates if current session is closed
                try:
                    # Test if session is active
                    from sqlalchemy import text
                    from sqlalchemy.exc import ResourceClosedError, InvalidRequestError
                    self.session.execute(text("SELECT 1"))
                    work_session = self.session
                except (ResourceClosedError, InvalidRequestError, AttributeError):
                    # Session is closed or not usable, create new one
                    new_session = Session(bind=self.engine)
                    work_session = new_session

                manager = SmartCollectionManager(work_session, auto_update=False)

                for collection_id in collection_ids:
                    try:
                        manager.update_smart_collection(collection_id)
                    except Exception as e:
                        logger.error(f"Error updating collection {collection_id}: {e}", exc_info=True)

                if new_session:
                    new_session.close()
        finally:
            self._processing = False


class EventHandlerManager:
    """
    Thread-safe singleton manager for event handler lifecycle.

    Manages SQLAlchemy event listeners for smart collection updates.
    """

    _instance = None
    _lock = None

    def __new__(cls):
        """Ensure only one instance exists (thread-safe singleton)."""
        if cls._lock is None:
            import threading
            cls._lock = threading.Lock()

        with cls._lock:
            if cls._instance is None:
                cls._instance = super(EventHandlerManager, cls).__new__(cls)
                cls._instance._handler = None
                cls._instance._registered = False

        return cls._instance

    def register(self, session: Session, enabled: bool = True):
        """
        Register SQLAlchemy event listeners for smart collections.

        Args:
            session: SQLAlchemy session
            enabled: Whether to enable auto-updates

        Returns:
            SmartCollectionEventHandler instance
        """
        if self._registered and self._handler is not None:
            logger.info("Event handlers already registered")
            return self._handler

        self._handler = SmartCollectionEventHandler(session, enabled)

        # Register events on Game model
        event.listen(Game, 'after_insert', self._handler.on_game_created)
        event.listen(Game, 'after_update', self._handler.on_game_updated)
        event.listen(Game, 'after_delete', self._handler.on_game_deleted)

        # Register relationship events
        event.listen(Game.platforms, 'append', self._handler.on_relationship_changed)
        event.listen(Game.platforms, 'remove', self._handler.on_relationship_changed)
        event.listen(Game.genres, 'append', self._handler.on_relationship_changed)
        event.listen(Game.genres, 'remove', self._handler.on_relationship_changed)
        event.listen(Game.tags, 'append', self._handler.on_relationship_changed)
        event.listen(Game.tags, 'remove', self._handler.on_relationship_changed)
        event.listen(Game.categories, 'append', self._handler.on_relationship_changed)
        event.listen(Game.categories, 'remove', self._handler.on_relationship_changed)

        # Register after_commit event to automatically process queued updates
        @event.listens_for(session, 'after_commit')
        def auto_process_queue(session):
            """Automatically process smart collection updates after commit."""
            if enabled and self._handler:
                self._handler.process_queue()

        self._registered = True
        logger.info("Smart collection event handlers registered")
        return self._handler

    def get_handler(self):
        """
        Get the event handler instance.

        Returns:
            SmartCollectionEventHandler instance or None if not registered
        """
        return self._handler

    def unregister(self):
        """
        Unregister all event listeners (useful for testing).

        Note: SQLAlchemy event removal requires explicit listener removal.
        """
        if self._handler is not None and self._registered:
            try:
                # Remove events from Game model
                event.remove(Game, 'after_insert', self._handler.on_game_created)
                event.remove(Game, 'after_update', self._handler.on_game_updated)
                event.remove(Game, 'after_delete', self._handler.on_game_deleted)

                # Remove relationship events
                event.remove(Game.platforms, 'append', self._handler.on_relationship_changed)
                event.remove(Game.platforms, 'remove', self._handler.on_relationship_changed)
                event.remove(Game.genres, 'append', self._handler.on_relationship_changed)
                event.remove(Game.genres, 'remove', self._handler.on_relationship_changed)
                event.remove(Game.tags, 'append', self._handler.on_relationship_changed)
                event.remove(Game.tags, 'remove', self._handler.on_relationship_changed)
                event.remove(Game.categories, 'append', self._handler.on_relationship_changed)
                event.remove(Game.categories, 'remove', self._handler.on_relationship_changed)

                logger.info("Event handlers unregistered")
            except (ValueError, AttributeError) as e:
                logger.warning(f"Error unregistering event handlers: {e}")

        self._handler = None
        self._registered = False

    @classmethod
    def reset_instance(cls):
        """
        Reset the singleton instance (for testing).

        Warning: This is intended for testing only.
        """
        if cls._lock is not None:
            with cls._lock:
                if cls._instance is not None:
                    cls._instance.unregister()
                cls._instance = None


# Convenience functions for backward compatibility
def register_smart_collection_events(session: Session, enabled: bool = True):
    """
    Register SQLAlchemy event listeners for smart collections (convenience function).

    Args:
        session: SQLAlchemy session
        enabled: Whether to enable auto-updates

    Returns:
        SmartCollectionEventHandler instance
    """
    manager = EventHandlerManager()
    return manager.register(session, enabled)


def get_event_handler():
    """
    Get the event handler instance (convenience function).

    Returns:
        SmartCollectionEventHandler instance or None
    """
    manager = EventHandlerManager()
    return manager.get_handler()


def process_smart_collection_updates(session: Session):
    """
    Process any pending smart collection updates (convenience function).

    Args:
        session: SQLAlchemy session
    """
    manager = EventHandlerManager()
    handler = manager.get_handler()
    if handler:
        handler.process_queue()
