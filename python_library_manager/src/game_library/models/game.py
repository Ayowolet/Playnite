"""
Game model that mirrors the Playnite JSON serialisation format.
All field names deliberately preserve Playnite's PascalCase convention so
that data round-trips through Playnite's JSON database files without loss.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class ReleaseDate:
    """Partial date (only Year is mandatory in Playnite)."""

    Year: Optional[int] = None
    Month: Optional[int] = None
    Day: Optional[int] = None

    def to_dict(self) -> dict[str, int]:
        return {k: v for k, v in {"Year": self.Year, "Month": self.Month, "Day": self.Day}.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReleaseDate":
        return cls(Year=data.get("Year"), Month=data.get("Month"), Day=data.get("Day"))

    def __str__(self) -> str:
        parts = [str(self.Year or "?")]
        if self.Month:
            parts.append(f"{self.Month:02d}")
            if self.Day:
                parts.append(f"{self.Day:02d}")
        return "-".join(parts)


@dataclass(slots=True)
class Link:
    """A named hyperlink associated with a game (e.g. official site, store page)."""

    Name: str = ""
    Url: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"Name": self.Name, "Url": self.Url}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Link":
        return cls(Name=data.get("Name", ""), Url=data.get("Url", ""))


@dataclass(slots=True)
class Game:
    """
    Full game model compatible with Playnite's JSON database format.

    Relationship fields (e.g. ``PlatformIds``) store GUIDs that reference
    separate entity collections.  Resolved human-readable names are held in
    private ``_resolved_*`` attributes that are never serialised to disk.
    """

    # ── Identity ────────────────────────────────────────────────────────────
    Id: str = field(default_factory=lambda: str(uuid.uuid4()))
    Name: str = ""
    SortingName: str = ""
    GameId: str = ""   # Provider-specific ID (e.g. Steam App ID)
    PluginId: str = ""  # GUID of the library plugin that owns this game

    # ── Relationships (stored as GUID lists) ────────────────────────────────
    SourceId: str = ""
    PlatformIds: list[str] = field(default_factory=list)
    DeveloperIds: list[str] = field(default_factory=list)
    PublisherIds: list[str] = field(default_factory=list)
    GenreIds: list[str] = field(default_factory=list)
    CategoryIds: list[str] = field(default_factory=list)
    TagIds: list[str] = field(default_factory=list)
    SeriesIds: list[str] = field(default_factory=list)
    AgeRatingIds: list[str] = field(default_factory=list)
    RegionIds: list[str] = field(default_factory=list)
    CompletionStatusId: str = ""

    # ── Dates (ISO-8601 strings for JSON compat) ────────────────────────────
    ReleaseDate: Optional[ReleaseDate] = None
    Added: Optional[str] = None
    Modified: Optional[str] = None
    LastActivity: Optional[str] = None

    # ── State flags ─────────────────────────────────────────────────────────
    IsInstalled: bool = False
    Hidden: bool = False
    Favorite: bool = False

    # ── Playtime & counts ───────────────────────────────────────────────────
    Playtime: int = 0   # seconds
    PlayCount: int = 0

    # ── Scores (0-100, None = not set) ──────────────────────────────────────
    UserScore: Optional[int] = None
    CriticScore: Optional[int] = None
    CommunityScore: Optional[int] = None

    # ── Content ─────────────────────────────────────────────────────────────
    Description: str = ""
    Notes: str = ""
    Version: str = ""
    Links: list[Link] = field(default_factory=list)

    # ── Media paths / URLs ──────────────────────────────────────────────────
    Icon: str = ""
    CoverImage: str = ""
    BackgroundImage: str = ""

    # ── Runtime-only resolved names (not serialised) ─────────────────────────
    _source_name: str = field(default="", compare=False, repr=False)
    _platform_names: list[str] = field(default_factory=list, compare=False, repr=False)
    _developer_names: list[str] = field(default_factory=list, compare=False, repr=False)
    _publisher_names: list[str] = field(default_factory=list, compare=False, repr=False)
    _genre_names: list[str] = field(default_factory=list, compare=False, repr=False)
    _category_names: list[str] = field(default_factory=list, compare=False, repr=False)
    _tag_names: list[str] = field(default_factory=list, compare=False, repr=False)

    # ── Convenience properties ───────────────────────────────────────────────

    @property
    def release_year(self) -> Optional[int]:
        """Return the release year, or ``None`` if no release date is set."""
        return self.ReleaseDate.Year if self.ReleaseDate else None

    @property
    def display_name(self) -> str:
        """Human-readable display name: ``SortingName`` if set, otherwise ``Name``."""
        return self.SortingName or self.Name

    # ── Completeness score ───────────────────────────────────────────────────

    def completeness_score(self) -> int:
        """Return 0-100 score measuring metadata completeness."""
        checks = [
            bool(self.Name),
            bool(self.CoverImage),
            bool(self.Description),
            bool(self.PlatformIds),
            bool(self.DeveloperIds),
            bool(self.PublisherIds),
            bool(self.GenreIds),
            bool(self.ReleaseDate and self.ReleaseDate.Year),
            self.CriticScore is not None,
            self.CommunityScore is not None,
            bool(self.BackgroundImage),
            bool(self.Icon),
            self.UserScore is not None,
            bool(self.Links),
            bool(self.Notes),
        ]
        return round(sum(checks) / len(checks) * 100)

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a Playnite-compatible dict (omits default/empty values)."""
        d: dict[str, Any] = {"Id": self.Id, "Name": self.Name}

        str_fields = [
            ("GameId", self.GameId),
            ("PluginId", self.PluginId),
            ("SourceId", self.SourceId),
            ("SortingName", self.SortingName),
            ("Description", self.Description),
            ("Notes", self.Notes),
            ("Version", self.Version),
            ("Icon", self.Icon),
            ("CoverImage", self.CoverImage),
            ("BackgroundImage", self.BackgroundImage),
            ("CompletionStatusId", self.CompletionStatusId),
        ]
        for key, val in str_fields:
            if val:
                d[key] = val

        list_fields = [
            ("PlatformIds", self.PlatformIds),
            ("DeveloperIds", self.DeveloperIds),
            ("PublisherIds", self.PublisherIds),
            ("GenreIds", self.GenreIds),
            ("CategoryIds", self.CategoryIds),
            ("TagIds", self.TagIds),
            ("SeriesIds", self.SeriesIds),
            ("AgeRatingIds", self.AgeRatingIds),
            ("RegionIds", self.RegionIds),
        ]
        for key, val in list_fields:
            if val:
                d[key] = val

        if self.ReleaseDate:
            d["ReleaseDate"] = self.ReleaseDate.to_dict()
        for key, val in [("Added", self.Added), ("Modified", self.Modified), ("LastActivity", self.LastActivity)]:
            if val:
                d[key] = val

        if self.IsInstalled:
            d["IsInstalled"] = True
        if self.Hidden:
            d["Hidden"] = True
        if self.Favorite:
            d["Favorite"] = True
        if self.Playtime:
            d["Playtime"] = self.Playtime
        if self.PlayCount:
            d["PlayCount"] = self.PlayCount
        for key, val in [("UserScore", self.UserScore), ("CriticScore", self.CriticScore), ("CommunityScore", self.CommunityScore)]:
            if val is not None:
                d[key] = val
        if self.Links:
            d["Links"] = [lnk.to_dict() for lnk in self.Links]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Game":
        """Deserialise from a Playnite-compatible dict."""
        release_date = None
        if rd := data.get("ReleaseDate"):
            release_date = ReleaseDate.from_dict(rd) if isinstance(rd, dict) else None
        links = [Link.from_dict(lnk) for lnk in data.get("Links", [])]
        return cls(
            Id=data.get("Id", str(uuid.uuid4())),
            Name=data.get("Name", ""),
            SortingName=data.get("SortingName", ""),
            GameId=data.get("GameId", ""),
            PluginId=data.get("PluginId", ""),
            SourceId=data.get("SourceId", ""),
            PlatformIds=data.get("PlatformIds") or [],
            DeveloperIds=data.get("DeveloperIds") or [],
            PublisherIds=data.get("PublisherIds") or [],
            GenreIds=data.get("GenreIds") or [],
            CategoryIds=data.get("CategoryIds") or [],
            TagIds=data.get("TagIds") or [],
            SeriesIds=data.get("SeriesIds") or [],
            AgeRatingIds=data.get("AgeRatingIds") or [],
            RegionIds=data.get("RegionIds") or [],
            CompletionStatusId=data.get("CompletionStatusId", ""),
            ReleaseDate=release_date,
            Added=data.get("Added"),
            Modified=data.get("Modified"),
            LastActivity=data.get("LastActivity"),
            IsInstalled=data.get("IsInstalled", False),
            Hidden=data.get("Hidden", False),
            Favorite=data.get("Favorite", False),
            Playtime=data.get("Playtime", 0),
            PlayCount=data.get("PlayCount", 0),
            UserScore=data.get("UserScore"),
            CriticScore=data.get("CriticScore"),
            CommunityScore=data.get("CommunityScore"),
            Description=data.get("Description", ""),
            Notes=data.get("Notes", ""),
            Version=data.get("Version", ""),
            Links=links,
            Icon=data.get("Icon", ""),
            CoverImage=data.get("CoverImage", ""),
            BackgroundImage=data.get("BackgroundImage", ""),
        )
