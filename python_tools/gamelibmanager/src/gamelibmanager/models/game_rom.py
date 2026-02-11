"""GameRom model mirroring C# Playnite.SDK.Models.GameRom."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class GameRom:
    """A ROM file associated with a game."""

    name: str = ""
    path: str = ""

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GameRom):
            return NotImplemented
        return (
            self.name == other.name
            and os.path.normcase(self.path) == os.path.normcase(other.path)
        )

    def __hash__(self) -> int:
        return hash((self.name, os.path.normcase(self.path)))
