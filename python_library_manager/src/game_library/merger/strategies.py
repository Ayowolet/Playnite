"""
Merge strategies and field-level merge semantics.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional


class MergeStrategy(str, Enum):
    """
    Controls how field-level conflicts are resolved when both the master and
    the source library contain a game with the same identity.

    KEEP_MASTER
        The master library always wins.  Source-only games are added, but any
        field that already has a value in the master is left untouched.

    KEEP_SOURCE
        The source library always wins.  Every field from the source game
        overwrites the master's value.

    MERGE_PREFER_MASTER
        Fill empty fields on the master from the source.  When both sides have
        a value, the master's value is kept.

    MERGE_PREFER_SOURCE
        Fill empty fields on the master from the source.  When both sides have
        a value, the source's value overwrites the master.

    MOST_COMPLETE
        For each field, use the value from whichever game has it set.  When
        both have a value, choose the richer one (longer string, larger
        numeric score, non-empty list, etc.).

    MOST_PLAYED
        Like ``MERGE_PREFER_MASTER`` but for play-stats (Playtime, PlayCount,
        LastActivity) the source wins if it records more activity.
    """

    KEEP_MASTER = "keep_master"
    KEEP_SOURCE = "keep_source"
    MERGE_PREFER_MASTER = "merge_prefer_master"
    MERGE_PREFER_SOURCE = "merge_prefer_source"
    MOST_COMPLETE = "most_complete"
    MOST_PLAYED = "most_played"


class MergeField(str, Enum):
    """Named fields that participate in merge / conflict logic."""

    NAME = "Name"
    SORTING_NAME = "SortingName"
    DESCRIPTION = "Description"
    NOTES = "Notes"
    VERSION = "Version"
    RELEASE_DATE = "ReleaseDate"
    PLATFORM_IDS = "PlatformIds"
    DEVELOPER_IDS = "DeveloperIds"
    PUBLISHER_IDS = "PublisherIds"
    GENRE_IDS = "GenreIds"
    CATEGORY_IDS = "CategoryIds"
    TAG_IDS = "TagIds"
    SERIES_IDS = "SeriesIds"
    AGE_RATING_IDS = "AgeRatingIds"
    REGION_IDS = "RegionIds"
    COVER_IMAGE = "CoverImage"
    BACKGROUND_IMAGE = "BackgroundImage"
    ICON = "Icon"
    USER_SCORE = "UserScore"
    CRITIC_SCORE = "CriticScore"
    COMMUNITY_SCORE = "CommunityScore"
    PLAYTIME = "Playtime"
    PLAY_COUNT = "PlayCount"
    LAST_ACTIVITY = "LastActivity"
    LINKS = "Links"
    IS_INSTALLED = "IsInstalled"
    HIDDEN = "Hidden"
    FAVORITE = "Favorite"


def _richer_scalar(a: Any, b: Any) -> Any:
    """Return the 'richer' of two scalar values (longer string, higher score)."""
    if a is None:
        return b
    if b is None:
        return a
    if isinstance(a, str) and isinstance(b, str):
        return a if len(a) >= len(b) else b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return max(a, b)
    return a  # default: prefer existing


def _union_list(a: list, b: list) -> list:
    """Return a + b deduplicated (preserving order)."""
    seen: set = set()
    result: list = []
    for item in list(a) + list(b):
        key = item if not isinstance(item, dict) else str(sorted(item.items()))
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def apply_strategy(
    field: str,
    master_val: Any,
    source_val: Any,
    strategy: MergeStrategy,
) -> Any:
    """
    Return the value to use for *field* under *strategy*.

    This is the core merge decision function used by :class:`ConflictResolver`.
    """
    is_list = isinstance(master_val, list) or isinstance(source_val, list)
    master_empty = _is_empty(master_val)
    source_empty = _is_empty(source_val)

    # Both empty → no change
    if master_empty and source_empty:
        return master_val

    # One side empty → fill from the other (all strategies agree)
    if master_empty and not source_empty:
        return source_val
    if source_empty and not master_empty:
        return master_val

    # Both have values – apply strategy
    if strategy == MergeStrategy.KEEP_MASTER:
        return master_val
    if strategy == MergeStrategy.KEEP_SOURCE:
        return source_val
    if strategy == MergeStrategy.MERGE_PREFER_MASTER:
        return master_val
    if strategy == MergeStrategy.MERGE_PREFER_SOURCE:
        return source_val
    if strategy == MergeStrategy.MOST_COMPLETE:
        if is_list:
            return _union_list(master_val or [], source_val or [])
        return _richer_scalar(master_val, source_val)
    if strategy == MergeStrategy.MOST_PLAYED:
        # Play-stats fields: choose higher value
        if field in ("Playtime", "PlayCount"):
            return max(master_val or 0, source_val or 0)
        if field == "LastActivity":
            if master_val and source_val:
                return max(master_val, source_val)
            return master_val or source_val
        # Everything else: prefer master
        return master_val

    return master_val  # fallback


def _is_empty(val: Any) -> bool:
    """Return True if *val* is considered "not set" for merge purposes."""
    if val is None:
        return True
    if isinstance(val, str):
        return val == ""
    if isinstance(val, (list, dict)):
        return len(val) == 0
    if isinstance(val, int):
        return val == 0
    return False
