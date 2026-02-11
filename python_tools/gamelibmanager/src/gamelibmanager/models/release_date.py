"""Variable-granularity release date mirroring C# ReleaseDate struct."""

from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass(slots=True)
class ReleaseDate:
    """Release date with optional month and day.

    Serialises as ``"YYYY"``, ``"YYYY-M"``, or ``"YYYY-M-D"`` to match
    the Playnite JSON format.
    """

    year: int
    month: int | None = None
    day: int | None = None

    @property
    def date(self) -> datetime.date:
        return datetime.date(self.year, self.month or 1, self.day or 1)

    def serialize(self) -> str:
        if self.day is not None and self.month is not None:
            return f"{self.year}-{self.month}-{self.day}"
        if self.month is not None:
            return f"{self.year}-{self.month}"
        return str(self.year)

    @classmethod
    def deserialize(cls, s: str) -> ReleaseDate:
        parts = s.split("-")
        if len(parts) == 3:
            return cls(int(parts[0]), int(parts[1]), int(parts[2]))
        if len(parts) == 2:
            return cls(int(parts[0]), int(parts[1]))
        return cls(int(parts[0]))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ReleaseDate):
            return NotImplemented
        return (self.year, self.month, self.day) == (other.year, other.month, other.day)

    def __hash__(self) -> int:
        return hash((self.year, self.month, self.day))
