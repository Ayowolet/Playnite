"""Link model mirroring C# Playnite.SDK.Models.Link."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Link:
    """A named URL link attached to a game."""

    name: str = ""
    url: str = ""

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Link):
            return NotImplemented
        return self.name == other.name and self.url == other.url

    def __hash__(self) -> int:
        return hash((self.name, self.url))
