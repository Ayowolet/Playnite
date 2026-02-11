"""Python SDK / API that scripts use to interact with the game library."""

from __future__ import annotations

import logging
from typing import Any, Callable

from playnite_py.models.game import Game, Tag, Category, Feature, Platform, Genre
from playnite_py.models.action import GameAction, ActionType, ActionPhase
from playnite_py.models.database import GameDatabase
from playnite_py.utils import BoundedList


class DatabaseAPI:
    """Read/write access to the game database for scripts."""

    # Fields that scripts are allowed to modify via update_game().
    # Internal/structural fields (id, added, action_ids, etc.) are excluded.
    _MUTABLE_FIELDS: frozenset[str] = frozenset({
        "name", "description", "source", "is_installed", "install_directory",
        "completion_status", "playtime", "play_count", "last_activity",
        "version", "user_score", "critic_score", "community_score",
        "cover_image", "background_image", "icon", "notes",
        "hidden", "favorite", "release_date",
    })

    def __init__(self, db: GameDatabase):
        self._db = db

    def get_games(self) -> list[dict[str, Any]]:
        """Return all games in the database as dictionaries."""
        return [g.to_dict() for g in self._db.get_all_games()]

    def get_game(self, game_id: str) -> dict[str, Any] | None:
        """Return a single game by ID, or None if not found."""
        game = self._db.get_game(game_id)
        return game.to_dict() if game else None

    def query_games(self, **filters: Any) -> list[dict[str, Any]]:
        """Return games matching the given filter criteria."""
        return [g.to_dict() for g in self._db.query_games(**filters)]

    def update_game(self, game_id: str, **fields: Any) -> bool:
        """Update mutable fields on a game.

        Only fields in ``_MUTABLE_FIELDS`` can be changed. Attempts to modify
        internal fields (``id``, ``added``, ``action_ids``, etc.) are silently
        ignored to protect database integrity.
        """
        game = self._db.get_game(game_id)
        if not game:
            return False
        for key, value in fields.items():
            if key in self._MUTABLE_FIELDS and hasattr(game, key):
                setattr(game, key, value)
        self._db.update_game(game)
        return True

    def add_game(self, **fields: Any) -> dict[str, Any]:
        """Create a new game from the given fields and add it to the database."""
        game = Game(**{k: v for k, v in fields.items() if k in Game.__dataclass_fields__})
        self._db.add_game(game)
        return game.to_dict()

    def remove_game(self, game_id: str) -> bool:
        """Remove a game from the database by ID."""
        return self._db.remove_game(game_id)

    def add_tag_to_game(self, game_id: str, tag_name: str) -> bool:
        """Add a tag to a game, creating the tag if it does not exist."""
        game = self._db.get_game(game_id)
        if not game:
            return False
        existing = {t.name: t for t in self._db.get_tags()}
        if tag_name in existing:
            tag = existing[tag_name]
        else:
            tag = self._db.add_tag(Tag(name=tag_name))
        if tag.id not in game.tag_ids:
            game.tag_ids.append(tag.id)
            self._db.update_game(game)
        return True

    def remove_tag_from_game(self, game_id: str, tag_name: str) -> bool:
        """Remove a tag from a game by tag name."""
        game = self._db.get_game(game_id)
        if not game:
            return False
        existing = {t.name: t for t in self._db.get_tags()}
        if tag_name not in existing:
            return False
        tag = existing[tag_name]
        if tag.id in game.tag_ids:
            game.tag_ids.remove(tag.id)
            self._db.update_game(game)
        return True

    def get_platforms(self) -> list[dict[str, Any]]:
        """Return all platforms in the database as dictionaries."""
        return [p.to_dict() for p in self._db.get_platforms()]

    def get_genres(self) -> list[dict[str, Any]]:
        """Return all genres in the database as dictionaries."""
        return [g.to_dict() for g in self._db.get_genres()]

    def get_tags(self) -> list[dict[str, Any]]:
        """Return all tags in the database as dictionaries."""
        return [t.to_dict() for t in self._db.get_tags()]

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics about the game database."""
        return self._db.get_stats()


class NotificationAPI:
    """Notification display for scripts (headless-compatible via logging)."""

    def __init__(self, logger: logging.Logger, max_notifications: int = 500):
        self._log = logger
        self._notifications: BoundedList[dict[str, str]] = BoundedList(max_notifications)

    def show(self, message: str, title: str = "") -> None:
        """Display an informational notification."""
        entry = {"type": "info", "title": title, "message": message}
        self._notifications.append(entry)
        self._log.info("Notification: %s - %s", title, message)

    def show_error(self, message: str, title: str = "Error") -> None:
        """Display an error notification."""
        entry = {"type": "error", "title": title, "message": message}
        self._notifications.append(entry)
        self._log.error("Error notification: %s - %s", title, message)

    def show_warning(self, message: str, title: str = "Warning") -> None:
        """Display a warning notification."""
        entry = {"type": "warning", "title": title, "message": message}
        self._notifications.append(entry)
        self._log.warning("Warning notification: %s - %s", title, message)

    def get_pending(self) -> list[dict[str, str]]:
        """Return and clear all pending notifications."""
        pending = list(self._notifications)
        self._notifications.clear()
        return pending


class DialogAPI:
    """Headless-compatible dialog system for scripts.

    In headless/CLI mode, dialogs record their calls and return defaults.
    A GUI layer can override the response mechanism.
    """

    def __init__(self, max_history: int = 100):
        self._history: BoundedList[dict[str, Any]] = BoundedList(max_history)
        self._response_overrides: dict[str, Any] = {}

    def set_response(self, dialog_type: str, response: Any) -> None:
        """Pre-set responses for testing/automation."""
        self._response_overrides[dialog_type] = response

    def show_message(
        self,
        message: str,
        title: str = "",
        buttons: list[str] | None = None,
    ) -> str | None:
        """Show a message dialog and return the selected button."""
        buttons = buttons or ["OK"]
        entry = {"type": "message", "title": title, "message": message, "buttons": buttons}
        self._history.append(entry)
        return self._response_overrides.get("message", buttons[0] if buttons else None)

    def show_input(
        self, message: str, title: str = "", default: str = ""
    ) -> str | None:
        """Show an input dialog and return the entered text."""
        entry = {"type": "input", "title": title, "message": message, "default": default}
        self._history.append(entry)
        return self._response_overrides.get("input", default)

    def show_select(self, message: str, options: list[str]) -> str | None:
        """Show a selection dialog and return the chosen option."""
        entry = {"type": "select", "message": message, "options": options}
        self._history.append(entry)
        override = self._response_overrides.get("select")
        if override is not None:
            return override
        return options[0] if options else None

    def get_history(self) -> list[dict[str, Any]]:
        """Return all dialog interactions."""
        return list(self._history)


class MenuAPI:
    """Allows scripts to register custom menu entries."""

    def __init__(self):
        self._main_menu: dict[str, dict[str, Any]] = {}
        self._game_menu: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def add_main_menu_item(
        self,
        name: str,
        callback: Callable,
        icon: str = "",
        description: str = "",
        menu_section: str = "",
    ) -> str:
        """Register a new main menu item and return its ID."""
        self._counter += 1
        item_id = f"main_menu_{self._counter}"
        self._main_menu[item_id] = {
            "id": item_id,
            "name": name,
            "callback": callback,
            "icon": icon,
            "description": description,
            "menu_section": menu_section,
        }
        return item_id

    def add_game_menu_item(
        self,
        name: str,
        callback: Callable,
        icon: str = "",
        description: str = "",
        menu_section: str = "",
    ) -> str:
        """Register a new game context menu item and return its ID."""
        self._counter += 1
        item_id = f"game_menu_{self._counter}"
        self._game_menu[item_id] = {
            "id": item_id,
            "name": name,
            "callback": callback,
            "icon": icon,
            "description": description,
            "menu_section": menu_section,
        }
        return item_id

    def remove_menu_item(self, item_id: str) -> bool:
        """Remove a menu item by ID from either menu registry."""
        if item_id in self._main_menu:
            del self._main_menu[item_id]
            return True
        if item_id in self._game_menu:
            del self._game_menu[item_id]
            return True
        return False

    def get_main_menu_items(self) -> list[dict[str, Any]]:
        """Return all registered main menu items without callbacks."""
        return [
            {k: v for k, v in item.items() if k != "callback"}
            for item in self._main_menu.values()
        ]

    def get_game_menu_items(self) -> list[dict[str, Any]]:
        """Return all registered game context menu items without callbacks."""
        return [
            {k: v for k, v in item.items() if k != "callback"}
            for item in self._game_menu.values()
        ]

    def invoke_menu_item(self, item_id: str, *args: Any, **kwargs: Any) -> Any:
        """Invoke the callback of a registered menu item by ID."""
        item = self._main_menu.get(item_id) or self._game_menu.get(item_id)
        if not item:
            raise KeyError(f"Menu item '{item_id}' not found")
        return item["callback"](*args, **kwargs)


class ActionAPI:
    """Allows scripts to inject game actions."""

    def __init__(self, db: GameDatabase, source_script_id: str = ""):
        self._db = db
        self._source_script_id = source_script_id

    def add_action(
        self,
        name: str,
        script: str,
        game_id: str | None = None,
        action_type: str = "custom",
        phase: str = "pre_launch",
        priority: int = 50,
        is_async: bool = False,
        timeout: int = 30,
        conditions: list[dict[str, str]] | None = None,
        is_script_path: bool = False,
        rollback_script: str = "",
    ) -> str:
        """Create a new game action and return its ID."""
        from playnite_py.models.action import ActionCondition

        conds = [ActionCondition.from_dict(c) for c in (conditions or [])]
        action = GameAction(
            name=name,
            script=script,
            game_id=game_id,
            action_type=ActionType(action_type),
            phase=ActionPhase(phase),
            priority=priority,
            is_async=is_async,
            timeout=timeout,
            conditions=conds,
            is_script_path=is_script_path,
            source_script_id=self._source_script_id,
            rollback_script=rollback_script,
        )
        self._db.add_action(action)
        return action.id

    def remove_action(self, action_id: str) -> bool:
        """Remove an action from the database by ID."""
        return self._db.remove_action(action_id)

    def get_actions(
        self, game_id: str | None = None, phase: str | None = None
    ) -> list[dict[str, Any]]:
        """Return actions filtered by game ID and/or phase."""
        actions = self._db.get_actions_for_game(game_id, phase)
        return [a.to_dict() for a in actions]


class PathsAPI:
    """Provides access to application paths."""

    def __init__(
        self,
        extensions_dir: str = "",
        data_dir: str = "",
        log_dir: str = "",
    ):
        self.extensions_dir = extensions_dir
        self.data_dir = data_dir
        self.log_dir = log_dir


class PlayniteAPI:
    """Main API object passed to scripts as `playnite`."""

    def __init__(
        self,
        database: GameDatabase,
        script_id: str = "",
        logger: logging.Logger | None = None,
        extensions_dir: str = "",
        data_dir: str = "",
        log_dir: str = "",
    ):
        self.log = logger or logging.getLogger(f"script.{script_id}")
        self.database = DatabaseAPI(database)
        self.notifications = NotificationAPI(self.log)
        self.dialogs = DialogAPI()
        self.menus = MenuAPI()
        self.actions = ActionAPI(database, source_script_id=script_id)
        self.paths = PathsAPI(
            extensions_dir=extensions_dir,
            data_dir=data_dir,
            log_dir=log_dir,
        )
        self.script_id = script_id
        self._app_version = "0.1.0"

    @property
    def app_version(self) -> str:
        """Return the application version string."""
        return self._app_version
