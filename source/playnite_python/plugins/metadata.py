"""
Metadata plugin base class.

A metadata plugin downloads game metadata from an external source (e.g. IGDB,
MobyGames).  Subclass :class:`MetadataPlugin` and implement
:meth:`get_metadata_provider` to return an :class:`OnDemandMetadataProvider`
instance for each download request.

Example
-------
::

    class IGDBMetadataPlugin(MetadataPlugin):
        @property
        def plugin_id(self) -> str:
            return "com.example.igdb"

        @property
        def name(self) -> str:
            return "IGDB Metadata"

        @property
        def supported_fields(self) -> List[MetadataField]:
            return [MetadataField.Name, MetadataField.Description,
                    MetadataField.CoverImage, MetadataField.CriticScore]

        def get_metadata_provider(self, options):
            return IGDBProvider(options.game_data)
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base import Plugin

if TYPE_CHECKING:
    from ..models.game import Game


# ---------------------------------------------------------------------------
# MetadataField enum — mirrors C# Playnite SDK MetadataField
# ---------------------------------------------------------------------------

class MetadataField(Enum):
    """Identifiers for metadata fields a plugin can provide."""
    Name = "Name"
    Genres = "Genres"
    ReleaseDate = "ReleaseDate"
    Developers = "Developers"
    Publishers = "Publishers"
    Tags = "Tags"
    Description = "Description"
    Links = "Links"
    CriticScore = "CriticScore"
    CommunityScore = "CommunityScore"
    Icon = "Icon"
    CoverImage = "CoverImage"
    BackgroundImage = "BackgroundImage"
    Features = "Features"
    Series = "Series"
    AgeRating = "AgeRating"
    Region = "Region"
    Platform = "Platform"
    InstallSize = "InstallSize"


# ---------------------------------------------------------------------------
# Request / args types
# ---------------------------------------------------------------------------

@dataclass
class MetadataRequestOptions:
    """Options for a metadata download request."""
    is_background_download: bool = False
    game_data: Optional["Game"] = None


@dataclass
class GetMetadataFieldArgs:
    """Arguments passed to individual field getters on :class:`OnDemandMetadataProvider`."""
    game_data: Optional["Game"] = None
    options: Optional[MetadataRequestOptions] = None


# ---------------------------------------------------------------------------
# On-demand provider base — override the getters you support
# ---------------------------------------------------------------------------

class OnDemandMetadataProvider:
    """
    Per-request metadata provider.

    Returned by :meth:`MetadataPlugin.get_metadata_provider`.  Override
    only the field getter methods that your source supports; all others
    return *None* by default.
    """

    def get_name(self, args: GetMetadataFieldArgs) -> Optional[str]:
        return None

    def get_genres(self, args: GetMetadataFieldArgs) -> Optional[List[Any]]:
        return None

    def get_release_date(self, args: GetMetadataFieldArgs) -> Optional[str]:
        return None

    def get_developers(self, args: GetMetadataFieldArgs) -> Optional[List[Any]]:
        return None

    def get_publishers(self, args: GetMetadataFieldArgs) -> Optional[List[Any]]:
        return None

    def get_tags(self, args: GetMetadataFieldArgs) -> Optional[List[Any]]:
        return None

    def get_description(self, args: GetMetadataFieldArgs) -> Optional[str]:
        return None

    def get_links(self, args: GetMetadataFieldArgs) -> Optional[List[Any]]:
        return None

    def get_critic_score(self, args: GetMetadataFieldArgs) -> Optional[int]:
        return None

    def get_community_score(self, args: GetMetadataFieldArgs) -> Optional[int]:
        return None

    def get_icon(self, args: GetMetadataFieldArgs) -> Optional[str]:
        return None

    def get_cover_image(self, args: GetMetadataFieldArgs) -> Optional[str]:
        return None

    def get_background_image(self, args: GetMetadataFieldArgs) -> Optional[str]:
        return None

    def get_features(self, args: GetMetadataFieldArgs) -> Optional[List[Any]]:
        return None

    def get_series(self, args: GetMetadataFieldArgs) -> Optional[List[Any]]:
        return None

    def get_age_ratings(self, args: GetMetadataFieldArgs) -> Optional[List[Any]]:
        return None

    def get_regions(self, args: GetMetadataFieldArgs) -> Optional[List[Any]]:
        return None

    def get_platforms(self, args: GetMetadataFieldArgs) -> Optional[List[Any]]:
        return None

    def get_install_size(self, args: GetMetadataFieldArgs) -> Optional[int]:
        return None


# Mapping from MetadataField → provider getter method name
_FIELD_TO_GETTER: Dict[MetadataField, str] = {
    MetadataField.Name: "get_name",
    MetadataField.Genres: "get_genres",
    MetadataField.ReleaseDate: "get_release_date",
    MetadataField.Developers: "get_developers",
    MetadataField.Publishers: "get_publishers",
    MetadataField.Tags: "get_tags",
    MetadataField.Description: "get_description",
    MetadataField.Links: "get_links",
    MetadataField.CriticScore: "get_critic_score",
    MetadataField.CommunityScore: "get_community_score",
    MetadataField.Icon: "get_icon",
    MetadataField.CoverImage: "get_cover_image",
    MetadataField.BackgroundImage: "get_background_image",
    MetadataField.Features: "get_features",
    MetadataField.Series: "get_series",
    MetadataField.AgeRating: "get_age_ratings",
    MetadataField.Region: "get_regions",
    MetadataField.Platform: "get_platforms",
    MetadataField.InstallSize: "get_install_size",
}


# ---------------------------------------------------------------------------
# MetadataPlugin base
# ---------------------------------------------------------------------------

class MetadataPlugin(Plugin):
    """
    Abstract base for metadata plugins.

    Implement :attr:`supported_fields` and :meth:`get_metadata_provider`.
    Call :meth:`download_metadata` to retrieve all supported fields for a
    given game.
    """

    @property
    @abstractmethod
    def supported_fields(self) -> List[MetadataField]:
        """List of :class:`MetadataField` values this plugin can provide."""
        ...

    @abstractmethod
    def get_metadata_provider(
        self, options: MetadataRequestOptions
    ) -> OnDemandMetadataProvider:
        """
        Return an :class:`OnDemandMetadataProvider` for *options*.

        The provider is called once per requested field.
        """
        ...

    def download_metadata(
        self,
        game: "Game",
        fields: Optional[List[MetadataField]] = None,
    ) -> Dict[str, Any]:
        """
        Download metadata for *game* and return it as a plain dict.

        Parameters
        ----------
        game:
            The game to download metadata for.
        fields:
            Subset of :class:`MetadataField` to fetch.  Defaults to
            :attr:`supported_fields`.

        Returns
        -------
        dict
            ``{MetadataField.value: value}`` for each requested field.
            Fields that the provider returns *None* for are included with
            value *None*.
        """
        options = MetadataRequestOptions(game_data=game)
        provider = self.get_metadata_provider(options)
        fields_to_get = fields if fields is not None else self.supported_fields
        result: Dict[str, Any] = {}
        for f in fields_to_get:
            getter_name = _FIELD_TO_GETTER.get(f)
            if getter_name:
                args = GetMetadataFieldArgs(game_data=game, options=options)
                getter = getattr(provider, getter_name, None)
                result[f.value] = getter(args) if getter else None
        return result
