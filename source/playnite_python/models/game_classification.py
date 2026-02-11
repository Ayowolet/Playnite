"""
Classification enumerations and helpers for :class:`~models.game.Game`.

Separated from ``game.py`` so that the classification vocabulary can be
imported and used independently without pulling in the full game model.

Public API
----------
Enumerations: :class:`ScoreRating`, :class:`ScoreGroup`,
:class:`PastTimeSegment`, :class:`PlaytimeCategory`,
:class:`InstallSizeGroup`, :class:`InstallationStatus`, :class:`GameField`.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional


__all__ = [
    "ScoreRating",
    "ScoreGroup",
    "PastTimeSegment",
    "PlaytimeCategory",
    "InstallSizeGroup",
    "InstallationStatus",
    "GameField",
]


# ---------------------------------------------------------------------------
# Classification enumerations
# ---------------------------------------------------------------------------

class ScoreRating(Enum):
    """Bucketed score quality label."""
    NONE = "None"
    NEGATIVE = "Negative"
    MIXED = "Mixed"
    POSITIVE = "Positive"


class ScoreGroup(Enum):
    """Score decade group (0-9 → O0x, 10-19 → O1x, …, 90-100 → O9x)."""
    NONE = "None"
    O0x = "0x"
    O1x = "1x"
    O2x = "2x"
    O3x = "3x"
    O4x = "4x"
    O5x = "5x"
    O6x = "6x"
    O7x = "7x"
    O8x = "8x"
    O9x = "9x"


class PastTimeSegment(Enum):
    """Time-ago bucket for date fields."""
    NEVER = "Never"
    TODAY = "Today"
    YESTERDAY = "Yesterday"
    PAST_WEEK = "PastWeek"
    PAST_MONTH = "PastMonth"
    PAST_YEAR = "PastYear"
    MORE_THAN_YEAR = "MoreThanYear"


class PlaytimeCategory(Enum):
    """Buckets for total play time."""
    NOT_PLAYED = "NotPlayed"
    LESS_THAN_HOUR = "LessThanHour"
    O1_10 = "1_10"
    O10_100 = "10_100"
    O100_500 = "100_500"
    O500_1000 = "500_1000"
    O1000PLUS = "1000plus"


class InstallSizeGroup(Enum):
    """Buckets for installed game size."""
    NONE = "None"
    S0 = "S0"    # < 100 MB
    S1 = "S1"    # 100 MB – 1 GB
    S2 = "S2"    # 1 GB – 5 GB
    S3 = "S3"    # 5 GB – 10 GB
    S4 = "S4"    # 10 GB – 20 GB
    S5 = "S5"    # 20 GB – 50 GB
    S6 = "S6"    # 50 GB – 100 GB
    S7 = "S7"    # > 100 GB


class InstallationStatus(Enum):
    """Whether a game is currently installed."""
    INSTALLED = "Installed"
    UNINSTALLED = "Uninstalled"


class GameField(Enum):
    """Identifiers for every storable field on :class:`~models.game.Game`."""
    Name = "Name"
    SortingName = "SortingName"
    Description = "Description"
    Notes = "Notes"
    Version = "Version"
    GameId = "GameId"
    IsInstalled = "IsInstalled"
    InstallDirectory = "InstallDirectory"
    InstallSize = "InstallSize"
    OverrideInstallState = "OverrideInstallState"
    IsHidden = "IsHidden"
    IsFavorite = "IsFavorite"
    Platforms = "Platforms"
    Genres = "Genres"
    Developers = "Developers"
    Publishers = "Publishers"
    Tags = "Tags"
    Categories = "Categories"
    Features = "Features"
    Series = "Series"
    AgeRatings = "AgeRatings"
    Regions = "Regions"
    Source = "Source"
    CompletionStatus = "CompletionStatus"
    PlayTime = "PlayTime"
    PlayCount = "PlayCount"
    LastActivity = "LastActivity"
    PreScript = "PreScript"
    PostScript = "PostScript"
    GameStartedScript = "GameStartedScript"
    UserScore = "UserScore"
    CommunityScore = "CommunityScore"
    CriticScore = "CriticScore"
    BackgroundImage = "BackgroundImage"
    Icon = "Icon"
    CoverImage = "CoverImage"
    Manual = "Manual"
    GameActions = "GameActions"
    Links = "Links"
    ReleaseDate = "ReleaseDate"
    Added = "Added"
    Modified = "Modified"
    PluginId = "PluginId"
    EnableSystemHdr = "EnableSystemHdr"
    Roms = "Roms"
    IncludeLibraryPluginAction = "IncludeLibraryPluginAction"
    IsInstalling = "IsInstalling"
    IsUninstalling = "IsUninstalling"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _score_rating(score: Optional[int]) -> ScoreRating:
    if score is None:
        return ScoreRating.NONE
    if score < 40:
        return ScoreRating.NEGATIVE
    if score < 75:
        return ScoreRating.MIXED
    return ScoreRating.POSITIVE


def _score_group(score: Optional[int]) -> ScoreGroup:
    if score is None:
        return ScoreGroup.NONE
    decade = min(score // 10, 9)
    return list(ScoreGroup)[decade + 1]  # index 0 is NONE, then O0x…O9x


def _classify_past_time(dt: Optional[datetime]) -> PastTimeSegment:
    if dt is None:
        return PastTimeSegment.NEVER
    today = date.today()
    d = dt.date()
    delta = (today - d).days
    if delta == 0:
        return PastTimeSegment.TODAY
    if delta == 1:
        return PastTimeSegment.YESTERDAY
    if delta <= 7:
        return PastTimeSegment.PAST_WEEK
    if delta <= 30:
        return PastTimeSegment.PAST_MONTH
    if delta <= 365:
        return PastTimeSegment.PAST_YEAR
    return PastTimeSegment.MORE_THAN_YEAR
