"""Base database object mirroring C# Playnite.SDK.Models.DatabaseObject."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(slots=True)
class DatabaseObject:
    """Base class for all database entities.

    Every entity in a Playnite database has a UUID ``id`` and a ``name``.
    """

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = ""

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DatabaseObject):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.id!s}, name={self.name!r})"
