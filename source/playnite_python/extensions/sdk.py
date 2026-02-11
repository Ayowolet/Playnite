"""
Playnite Python SDK — the public API available to extension scripts.

Scripts receive a ``PlayniteSDK`` instance as ``__api__`` in their global
namespace.  They can also use the convenience alias ``api``.

Quick-start example (inside a script)
--------------------------------------
::

    def on_game_started(game):
        api.notifications.show(f"Now playing: {game.name}")
        games = api.database.get_games()
        api.logger.Info(f"Library has {len(games)} games")
"""

from __future__ import annotations

import re
import sys
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Iterator, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..database.game_database import Collection, GameDatabase
    from ..models.game import (
        AgeRating, Category, Company, CompletionStatus, Game, GameFeature,
        GameSource, Genre, Platform, Region, Series, Tag,
    )
    from .lifecycle import LifecycleDispatcher
    from .logger import ScriptLogger


# ---------------------------------------------------------------------------
# Sub-API: Notifications
# ---------------------------------------------------------------------------

class NotificationType(Enum):
    """Severity level for a notification message."""
    INFO = "info"
    ERROR = "error"


@dataclass
class NotificationMessage:
    """A single notification held in the notification queue."""
    id: str
    text: str
    type: NotificationType = NotificationType.INFO
    activation_action: Optional[Callable[[], None]] = None


class NotificationAPI:
    """
    Send notifications to the user.

    In GUI mode these appear as toast notifications.  In headless/CLI mode
    they are printed to stdout.
    """

    def __init__(self) -> None:
        self._callbacks: List[Callable[[str, str], None]] = []
        self._messages: List[NotificationMessage] = []

    def add(
        self,
        notification_id: str,
        text: str,
        ntype: NotificationType = NotificationType.INFO,
        action: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Add a notification with an explicit ID.

        Parameters
        ----------
        notification_id:
            Unique identifier; used to remove the notification later.
        text:
            Display text.
        ntype:
            ``NotificationType.INFO`` (default) or ``NotificationType.ERROR``.
        action:
            Optional callable invoked when the notification is activated.
        """
        msg = NotificationMessage(
            id=notification_id, text=text, type=ntype, activation_action=action
        )
        self._messages.append(msg)
        for cb in self._callbacks:
            cb(text, ntype.value)
        if not self._callbacks:
            print(f"[NOTIFICATION:{ntype.value.upper()}] {text}", file=sys.stderr)

    def show(self, message: str, notification_type: str = "info") -> None:
        """
        Show a notification (backward-compatible convenience wrapper).

        Delegates to :meth:`add` with an auto-generated UUID as the ID.

        Parameters
        ----------
        message:
            The text to display.
        notification_type:
            ``"info"`` (default) or ``"error"``.
        """
        self.add(str(uuid.uuid4()), message, NotificationType(notification_type))

    def remove(self, notification_id: str) -> None:
        """Remove the notification with the given *notification_id*."""
        self._messages = [m for m in self._messages if m.id != notification_id]

    def remove_all(self) -> None:
        """Remove all notifications from the queue."""
        self._messages.clear()

    @property
    def messages(self) -> List[NotificationMessage]:
        """Snapshot of all current notification messages."""
        return list(self._messages)

    @property
    def count(self) -> int:
        """Number of notifications currently in the queue."""
        return len(self._messages)

    def _register_handler(self, callback: Callable[[str, str], None]) -> None:
        self._callbacks.append(callback)

    def clear_callbacks(self) -> None:
        """Release all registered handlers, breaking callback → namespace refs."""
        self._callbacks.clear()


# ---------------------------------------------------------------------------
# Sub-API: Dialogs (headless-compatible)
# ---------------------------------------------------------------------------

class DialogAPI:
    """
    Display interactive dialogs.

    In headless/CLI mode all dialogs fall back to stdin/stdout.
    """

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._show_message_handler: Optional[Callable[[str, str], None]] = None
        self._show_input_handler: Optional[Callable[[str, str], Optional[str]]] = None
        self._show_yes_no_handler: Optional[Callable[[str, str], bool]] = None

    def show_message(self, message: str, title: str = "Playnite") -> None:
        """Display an informational message."""
        if self._show_message_handler:
            self._show_message_handler(message, title)
        else:
            print(f"[DIALOG] {title}: {message}")

    def show_input(self, prompt: str, title: str = "Input", default: str = "") -> Optional[str]:
        """Prompt the user for text input; returns *None* if cancelled."""
        if self._show_input_handler:
            return self._show_input_handler(prompt, title)
        # CLI fallback
        try:
            value = input(f"[INPUT] {title} — {prompt} [{default}]: ").strip()
            return value if value else (default or None)
        except (EOFError, KeyboardInterrupt):
            return None

    def show_yes_no(self, message: str, title: str = "Confirm") -> bool:
        """Ask a yes/no question; returns *True* if the user confirms."""
        if self._show_yes_no_handler:
            return self._show_yes_no_handler(message, title)
        try:
            answer = input(f"[CONFIRM] {title} — {message} [y/N]: ").strip().lower()
            return answer in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    def show_file_picker(self, title: str = "Select file", extensions: Optional[List[str]] = None) -> Optional[str]:
        """Open a file picker; returns the selected path or *None*."""
        # CLI fallback: just ask for a path
        try:
            path = input(f"[FILE] {title}: ").strip()
            return path if path else None
        except (EOFError, KeyboardInterrupt):
            return None

    def show_folder_picker(self, title: str = "Select folder") -> Optional[str]:
        try:
            path = input(f"[FOLDER] {title}: ").strip()
            return path if path else None
        except (EOFError, KeyboardInterrupt):
            return None

    def set_headless(self, value: bool) -> None:
        self._headless = value


# ---------------------------------------------------------------------------
# Sub-API: Paths
# ---------------------------------------------------------------------------

class PathsAPI:
    """Provides resolved filesystem paths for common locations."""

    def __init__(
        self,
        app_path: str,
        config_path: str,
        database_path: str,
        extension_path: str,
        extension_data_path: str,
        log_path: str,
    ) -> None:
        self._app_path = app_path
        self._config_path = config_path
        self._database_path = database_path
        self._extension_path = extension_path
        self._extension_data_path = extension_data_path
        self._log_path = log_path

    @property
    def application_path(self) -> str:
        """Root directory of the Playnite Python installation."""
        return self._app_path

    @property
    def config_path(self) -> str:
        """User configuration directory."""
        return self._config_path

    @property
    def database_path(self) -> str:
        """Path to the SQLite database file."""
        return self._database_path

    @property
    def extension_path(self) -> str:
        """Directory containing all installed extensions/scripts."""
        return self._extension_path

    @property
    def extension_data_path(self) -> str:
        """Writable data directory for the current script."""
        return self._extension_data_path

    @property
    def log_path(self) -> str:
        """Directory for script log files."""
        return self._log_path


# ---------------------------------------------------------------------------
# Sub-API: Database access
# ---------------------------------------------------------------------------

class GameDatabaseAPI:
    """
    Read/write access to the game library database.

    All mutating methods call ``notify_change`` so that the UI (if any) can
    refresh.  Entity lookup collections (platforms, genres, tags, …) are
    exposed as pass-through properties so scripts can use
    ``api.database.tags.all()`` etc.
    """

    def __init__(self, db: "GameDatabase") -> None:
        self._db = db
        self._change_callbacks: List[Callable[[], None]] = []

    # -- Games CRUD ------------------------------------------------------------

    def get_games(
        self,
        filter_func: Optional[Callable[["Game"], bool]] = None,
    ) -> List["Game"]:
        """
        Return all games, optionally filtered.

        Parameters
        ----------
        filter_func:
            Optional callable receiving a :class:`~models.game.Game` and
            returning *True* to include it.
        """
        games = self._db.games.all()
        if filter_func:
            games = [g for g in games if filter_func(g)]
        return games

    def get_game(self, game_id: str) -> Optional["Game"]:
        """Return a single game by ID or *None*."""
        return self._db.games.get(game_id)

    def update_game(self, game: "Game") -> None:
        """Persist changes to an existing game record."""
        self._db.games.update(game)
        self._notify_change()

    def add_game(self, game: "Game") -> "Game":
        """Add a new game to the library."""
        result = self._db.games.add(game)
        self._notify_change()
        return result

    def remove_game(self, game_id: str) -> None:
        """Permanently delete a game from the library."""
        self._db.games.remove(game_id)
        self._notify_change()

    def search_games(self, query: str) -> List["Game"]:
        """Full-text search across name, description, and notes."""
        return self._db.games.search(query)

    def get_installed_games(self) -> List["Game"]:
        return self._db.games.get_installed()

    def get_recently_played(self, limit: int = 10) -> List["Game"]:
        return self._db.games.get_recently_played(limit)

    def get_favorites(self) -> List["Game"]:
        return self._db.games.get_favorites()

    # -- Entity collection pass-throughs ---------------------------------------

    @property
    def platforms(self) -> "Collection[Platform]":
        """Platform lookup collection."""
        return self._db.platforms

    @property
    def genres(self) -> "Collection[Genre]":
        """Genre lookup collection."""
        return self._db.genres

    @property
    def tags(self) -> "Collection[Tag]":
        """Tag lookup collection."""
        return self._db.tags

    @property
    def categories(self) -> "Collection[Category]":
        """Category lookup collection."""
        return self._db.categories

    @property
    def series(self) -> "Collection[Series]":
        """Series lookup collection."""
        return self._db.series

    @property
    def age_ratings(self) -> "Collection[AgeRating]":
        """Age rating lookup collection."""
        return self._db.age_ratings

    @property
    def regions(self) -> "Collection[Region]":
        """Region lookup collection."""
        return self._db.regions

    @property
    def features(self) -> "Collection[GameFeature]":
        """Game feature lookup collection."""
        return self._db.features

    @property
    def sources(self) -> "Collection[GameSource]":
        """Game source lookup collection."""
        return self._db.sources

    @property
    def completion_statuses(self) -> "Collection[CompletionStatus]":
        """Completion status lookup collection."""
        return self._db.completion_statuses

    @property
    def companies(self) -> "Collection[Company]":
        """Company lookup collection (developers and publishers)."""
        return self._db.companies

    @property
    def database_path(self) -> str:
        """Path to the underlying SQLite database file."""
        return self._db._path

    @contextmanager
    def buffered_update(self) -> Iterator[None]:
        """
        Context manager that defers all SQLite commits until the block exits.

        Delegates to :meth:`~database.game_database.GameDatabase.buffered_update`.
        """
        with self._db.buffered_update():
            yield

    # -- Change notifications --------------------------------------------------

    def _notify_change(self) -> None:
        for cb in self._change_callbacks:
            cb()

    def _register_change_handler(self, callback: Callable[[], None]) -> None:
        self._change_callbacks.append(callback)

    def clear_change_handlers(self) -> None:
        """Release all registered change handlers, breaking callback → namespace refs."""
        self._change_callbacks.clear()


# ---------------------------------------------------------------------------
# Sub-API: Addons / menu registration
# ---------------------------------------------------------------------------

class AddonsAPI:
    """
    Allows scripts to register custom menu items and UI elements.
    """

    def __init__(self) -> None:
        self._main_menu_items: List[Dict[str, Any]] = []
        self._game_menu_items: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def add_main_menu_item(
        self,
        name: str,
        callback: Callable[[], None],
        section: str = "Extensions",
    ) -> None:
        """Register a custom item in the application's main menu."""
        with self._lock:
            self._main_menu_items.append(
                {"name": name, "callback": callback, "section": section}
            )

    def add_game_menu_item(
        self,
        name: str,
        callback: Callable[["Game"], None],
        section: str = "Extensions",
    ) -> None:
        """Register a custom item in the game context menu."""
        with self._lock:
            self._game_menu_items.append(
                {"name": name, "callback": callback, "section": section}
            )

    def get_main_menu_items(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._main_menu_items)

    def get_game_menu_items(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._game_menu_items)

    def clear_script_items(self, script_name: str) -> None:
        """Remove all menu items registered by *script_name*."""
        with self._lock:
            self._main_menu_items = [
                i for i in self._main_menu_items if i.get("_script") != script_name
            ]
            self._game_menu_items = [
                i for i in self._game_menu_items if i.get("_script") != script_name
            ]

    def clear(self) -> None:
        """Remove all registered menu items, releasing all callback references.

        Called by the script manager on unload to ensure that callbacks defined
        in the script's namespace do not prevent garbage collection of the
        namespace (and all objects it holds) via their ``__globals__`` pointer.
        """
        with self._lock:
            self._main_menu_items.clear()
            self._game_menu_items.clear()


# ---------------------------------------------------------------------------
# Top-level SDK object
# ---------------------------------------------------------------------------

_GAME_VAR_RE = re.compile(r"\{game\.(\w+)\}")


class PlayniteSDK:
    """
    Entry-point object available to all scripts as ``__api__`` / ``api``.

    Constructed by :class:`~extensions.manager.ScriptManager` and passed into
    each script's execution context.

    Parameters
    ----------
    db:
        Open :class:`~database.game_database.GameDatabase` instance.
    paths:
        A :class:`PathsAPI` configured for the current script.
    logger:
        The per-script :class:`~extensions.logger.ScriptLogger`.
    headless:
        If *True*, dialogs use stdin/stdout rather than GUI widgets.
    lifecycle:
        Optional :class:`~extensions.lifecycle.LifecycleDispatcher` used by
        :meth:`start_game`, :meth:`install_game`, and :meth:`uninstall_game`.
    """

    def __init__(
        self,
        db: "GameDatabase",
        paths: PathsAPI,
        logger: "ScriptLogger",
        headless: bool = True,
        lifecycle: Optional["LifecycleDispatcher"] = None,
    ) -> None:
        self.database = GameDatabaseAPI(db)
        self.notifications = NotificationAPI()
        self.dialogs = DialogAPI(headless=headless)
        self.paths = paths
        self.addons = AddonsAPI()
        self.logger = logger
        self._headless = headless
        self._lifecycle = lifecycle

    def expand_game_variables(self, game: "Game", template: str) -> str:
        """
        Substitute ``{game.<field>}`` placeholders in *template* with the
        corresponding attribute value from *game*.

        Unknown placeholders are left unchanged.

        Example
        -------
        ::

            api.expand_game_variables(game, "Playing {game.name} from {game.install_directory}")
        """
        def _replace(m: re.Match) -> str:
            return str(getattr(game, m.group(1), m.group(0)))

        return _GAME_VAR_RE.sub(_replace, template)

    def start_game(self, game_id: str) -> None:
        """
        Fire the ``on_game_starting`` lifecycle hook for *game_id*.

        In headless mode no actual process is launched — scripts use this to
        signal that a game is about to start and trigger registered handlers.

        Raises
        ------
        ValueError
            If *game_id* is not in the database.
        """
        game = self.database.get_game(game_id)
        if game is None:
            raise ValueError(f"Game '{game_id}' not found in the database.")
        if self._lifecycle is not None:
            self._lifecycle.on_game_starting(game)

    def install_game(self, game_id: str) -> None:
        """
        Fire the ``on_game_installed`` lifecycle hook for *game_id*.

        Raises
        ------
        ValueError
            If *game_id* is not in the database.
        """
        game = self.database.get_game(game_id)
        if game is None:
            raise ValueError(f"Game '{game_id}' not found in the database.")
        if self._lifecycle is not None:
            self._lifecycle.on_game_installed(game)

    def uninstall_game(self, game_id: str) -> None:
        """
        Fire the ``on_game_uninstalled`` lifecycle hook for *game_id*.

        Raises
        ------
        ValueError
            If *game_id* is not in the database.
        """
        game = self.database.get_game(game_id)
        if game is None:
            raise ValueError(f"Game '{game_id}' not found in the database.")
        if self._lifecycle is not None:
            self._lifecycle.on_game_uninstalled(game)

    def __repr__(self) -> str:
        return f"PlayniteSDK(headless={self._headless})"
