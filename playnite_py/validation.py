"""Input validation utilities."""

import re
from typing import Any, Optional


class ValidationError(ValueError):
    """Raised when input validation fails."""
    pass


def validate_game_name(name: Any) -> str:
    """
    Validate game name input.

    Args:
        name: Game name to validate

    Returns:
        Validated and cleaned name

    Raises:
        ValidationError: If name is invalid
    """
    if name is None:
        raise ValidationError("Game name cannot be None")

    if not isinstance(name, str):
        raise ValidationError(f"Game name must be a string, got {type(name).__name__}")

    name = name.strip()

    if not name:
        raise ValidationError("Game name cannot be empty")

    if len(name) > 500:
        raise ValidationError(f"Game name too long: {len(name)} characters (max 500)")

    return name


def validate_string_field(value: Any, field_name: str, max_length: int = 500,
                          allow_empty: bool = True, allow_none: bool = False) -> Optional[str]:
    """
    Validate a string field.

    Args:
        value: Value to validate
        field_name: Name of the field (for error messages)
        max_length: Maximum allowed length
        allow_empty: Whether empty strings are allowed
        allow_none: Whether None is allowed

    Returns:
        Validated string or None

    Raises:
        ValidationError: If validation fails
    """
    if value is None:
        if allow_none:
            return None
        raise ValidationError(f"{field_name} cannot be None")

    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string, got {type(value).__name__}")

    value = value.strip()

    if not value and not allow_empty:
        raise ValidationError(f"{field_name} cannot be empty")

    if len(value) > max_length:
        raise ValidationError(
            f"{field_name} too long: {len(value)} characters (max {max_length})"
        )

    return value if value else None


def validate_playtime(playtime: Any) -> int:
    """
    Validate playtime value.

    Args:
        playtime: Playtime in minutes

    Returns:
        Validated playtime

    Raises:
        ValidationError: If playtime is invalid
    """
    if playtime is None:
        return 0

    if not isinstance(playtime, (int, float)):
        raise ValidationError(f"Playtime must be a number, got {type(playtime).__name__}")

    playtime = int(playtime)

    if playtime < 0:
        raise ValidationError(f"Playtime cannot be negative: {playtime}")

    if playtime > 1_000_000:  # Sanity check: ~694 days
        raise ValidationError(f"Playtime unreasonably large: {playtime} minutes")

    return playtime


def validate_rating(rating: Any, field_name: str = "Rating") -> Optional[float]:
    """
    Validate a rating value (0-100 scale).

    Args:
        rating: Rating value
        field_name: Name of the field

    Returns:
        Validated rating or None

    Raises:
        ValidationError: If rating is invalid
    """
    if rating is None:
        return None

    if not isinstance(rating, (int, float)):
        raise ValidationError(f"{field_name} must be a number, got {type(rating).__name__}")

    rating = float(rating)

    if rating < 0 or rating > 100:
        raise ValidationError(f"{field_name} must be between 0 and 100, got {rating}")

    return rating


def validate_list_field(value: Any, field_name: str) -> list:
    """
    Validate that a value is a list.

    Args:
        value: Value to validate
        field_name: Name of the field

    Returns:
        Validated list

    Raises:
        ValidationError: If value is not a list
    """
    if value is None:
        return []

    if not isinstance(value, (list, tuple)):
        raise ValidationError(f"{field_name} must be a list, got {type(value).__name__}")

    return list(value)


def sanitize_path_component(component: str) -> str:
    """
    Sanitize a path component to prevent directory traversal.

    Args:
        component: Path component to sanitize

    Returns:
        Sanitized path component

    Raises:
        ValidationError: If component contains dangerous patterns
    """
    if not component:
        raise ValidationError("Path component cannot be empty")

    # Remove any path separators and dangerous sequences
    dangerous_patterns = ['..', '/', '\\', '\x00']
    for pattern in dangerous_patterns:
        if pattern in component:
            raise ValidationError(f"Path component contains disallowed pattern: {pattern}")

    # Only allow alphanumeric, dash, underscore, dot
    if not re.match(r'^[a-zA-Z0-9._-]+$', component):
        raise ValidationError(f"Path component contains invalid characters: {component}")

    return component
