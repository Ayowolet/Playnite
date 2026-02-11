"""GameAction model mirroring C# Playnite.SDK.Models.GameAction."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import IntEnum


class GameActionType(IntEnum):
    FILE = 0
    URL = 1
    EMULATOR = 2
    SCRIPT = 3


class TrackingMode(IntEnum):
    DEFAULT = 0
    PROCESS = 1
    DIRECTORY = 2
    ORIGINAL_PROCESS = 3
    PROCESS_NAME = 4


@dataclass(slots=True)
class GameAction:
    """An executable action for a game (launch, URL, emulator, script)."""

    type: GameActionType = GameActionType.FILE
    name: str = ""
    path: str = ""
    working_dir: str = ""
    arguments: str = ""
    additional_arguments: str = ""
    override_default_args: bool = False
    is_play_action: bool = False
    emulator_id: uuid.UUID = field(default_factory=lambda: uuid.UUID(int=0))
    emulator_profile_id: str = ""
    tracking_mode: TrackingMode = TrackingMode.DEFAULT
    tracking_path: str = ""
    script: str = ""
    initial_tracking_delay: int = 0
    tracking_frequency: int = 2000
