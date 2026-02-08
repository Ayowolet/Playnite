"""Enumerations for the library system."""

from enum import Enum


class SortField(Enum):
    """Fields available for sorting games."""
    NAME = "name"
    RELEASE_DATE = "release_date"
    ADDED_DATE = "added_date"
    MODIFIED_DATE = "modified_date"
    PLAYTIME = "playtime"
    LAST_PLAYED = "last_played"
    RATING = "rating"
    USER_SCORE = "user_score"
    CRITIC_SCORE = "critic_score"
    COMMUNITY_SCORE = "community_score"
    INSTALL_SIZE = "install_size"
    COMPLETION_STATUS = "completion_status"
    PLATFORM = "platform"
    GENRE = "genre"
    DEVELOPER = "developer"
    PUBLISHER = "publisher"


class SortDirection(Enum):
    """Sort direction."""
    ASCENDING = "asc"
    DESCENDING = "desc"


class ViewMode(Enum):
    """View mode for displaying games."""
    GRID = "grid"
    LIST = "list"
    DETAILS = "details"


class FilterOperator(Enum):
    """Operators for filtering."""
    EQUALS = "eq"
    NOT_EQUALS = "ne"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    GREATER_THAN_OR_EQUAL = "gte"
    LESS_THAN_OR_EQUAL = "lte"
    IN = "in"
    NOT_IN = "not_in"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class CompletionStatusType(Enum):
    """Game completion status."""
    NOT_PLAYED = "not_played"
    PLAYING = "playing"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    DROPPED = "dropped"
    PLAN_TO_PLAY = "plan_to_play"
    BEATEN = "beaten"
    HUNDRED_PERCENT = "hundred_percent"


class GridSize(Enum):
    """Grid size for grid view."""
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    EXTRA_LARGE = "extra_large"
