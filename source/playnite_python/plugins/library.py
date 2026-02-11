"""
Library plugin base class.

A library plugin discovers and imports games from an external source (e.g. a
game store or platform).  Subclass :class:`LibraryPlugin` and implement
:meth:`get_games` to return a list of :class:`GameMetadata` objects.

The default :meth:`import_games` implementation converts those metadata
objects to fully-fledged :class:`~models.game.Game` records.

Example
-------
::

    class SteamLibraryPlugin(LibraryPlugin):
        @property
        def plugin_id(self) -> str:
            return "com.example.steam"

        @property
        def name(self) -> str:
            return "Steam Library"

        def get_games(self, args: LibraryGetGamesArgs) -> List[GameMetadata]:
            # Query Steam API ...
            return [GameMetadata(game_id="570", name="Dota 2")]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from abc import abstractmethod
from typing import Any, List, Optional, TYPE_CHECKING

from .base import Plugin, PluginProperties

if TYPE_CHECKING:
    from ..models.game import Game


# ---------------------------------------------------------------------------
# Arguments & metadata types
# ---------------------------------------------------------------------------

@dataclass
class LibraryGetGamesArgs:
    """Arguments passed to :meth:`LibraryPlugin.get_games`."""
    full_import: bool = False


@dataclass
class GameMetadata:
    """
    Raw game metadata returned by a library plugin before import.

    Fields here mirror the most common metadata available from external
    library sources.  All fields are optional — set only those that the
    library source provides.
    """
    game_id: str = ""
    name: str = ""
    platform_ids: List[str] = field(default_factory=list)
    description: str = ""
    developer_ids: List[str] = field(default_factory=list)
    publisher_ids: List[str] = field(default_factory=list)
    genre_ids: List[str] = field(default_factory=list)
    tag_ids: List[str] = field(default_factory=list)
    feature_ids: List[str] = field(default_factory=list)
    release_date: Optional[datetime] = None
    links: List[Any] = field(default_factory=list)
    icon: str = ""
    cover_image: str = ""
    background_image: str = ""
    community_score: Optional[int] = None
    critic_score: Optional[int] = None


@dataclass
class LibraryPluginProperties(PluginProperties):
    """Extended capabilities for library plugins."""
    can_shutdown_client: bool = False
    can_close_client: bool = False


# ---------------------------------------------------------------------------
# LibraryPlugin base
# ---------------------------------------------------------------------------

class LibraryPlugin(Plugin):
    """
    Abstract base for game library plugins.

    Implement :meth:`get_games` to return raw :class:`GameMetadata` from
    the library source.  Call :meth:`import_games` to convert and add those
    records to the database.
    """

    @abstractmethod
    def get_games(self, args: LibraryGetGamesArgs) -> List[GameMetadata]:
        """
        Fetch the list of games from the library source.

        Parameters
        ----------
        args:
            Import options such as ``full_import`` flag.

        Returns
        -------
        list[GameMetadata]
            Raw metadata for each discovered game.
        """
        ...

    @property
    def library_icon(self) -> str:
        """Path or resource key for the library's icon."""
        return ""

    @property
    def library_background(self) -> str:
        """Path or resource key for the library's background image."""
        return ""

    def import_games(
        self, args: Optional[LibraryGetGamesArgs] = None
    ) -> List["Game"]:
        """
        Convert :class:`GameMetadata` objects to :class:`~models.game.Game` records.

        This default implementation populates all fields that are present in
        the metadata.  Override to customise the conversion or to add games
        directly to the database.

        Parameters
        ----------
        args:
            Import options forwarded to :meth:`get_games`.  Defaults to
            :class:`LibraryGetGamesArgs` with ``full_import=False``.

        Returns
        -------
        list[Game]
            Converted game records (not yet persisted to the database).
        """
        from ..models.game import Game

        if args is None:
            args = LibraryGetGamesArgs()

        games: List[Game] = []
        for meta in self.get_games(args):
            g = Game(
                name=meta.name,
                game_id=meta.game_id,
                plugin_id=self.plugin_id,
                platform_ids=list(meta.platform_ids),
                description=meta.description,
                developer_ids=list(meta.developer_ids),
                publisher_ids=list(meta.publisher_ids),
                genre_ids=list(meta.genre_ids),
                tag_ids=list(meta.tag_ids),
                feature_ids=list(meta.feature_ids),
                release_date=meta.release_date,
                icon=meta.icon,
                cover_image=meta.cover_image,
                background_image=meta.background_image,
                community_score=meta.community_score,
                critic_score=meta.critic_score,
            )
            games.append(g)
        return games
