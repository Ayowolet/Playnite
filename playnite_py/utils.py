"""Shared utilities used across the playnite_py codebase."""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


class BoundedList(list[T]):
    """A list that automatically truncates to *max_size* after each append.

    Keeps the most recent items when the limit is exceeded, matching the
    sliding-window history pattern used by several subsystems.
    """

    def __init__(self, max_size: int = 1000):
        super().__init__()
        self.max_size = max_size

    def append(self, item: T) -> None:  # type: ignore[override]
        """Append *item* and trim to max_size if needed."""
        super().append(item)
        if len(self) > self.max_size:
            del self[: len(self) - self.max_size]
