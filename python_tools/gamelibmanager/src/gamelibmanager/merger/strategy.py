"""Merge strategy pattern implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable

from ..models.game import Game


class MergeStrategyType(Enum):
    KEEP_NEWEST = "keep_newest"
    KEEP_OLDEST = "keep_oldest"
    KEEP_SOURCE = "keep_source"
    KEEP_TARGET = "keep_target"
    MERGE_ALL = "merge_all"
    INTERACTIVE = "interactive"


class MergeStrategy(ABC):
    """Base class for merge conflict resolution strategies."""

    @abstractmethod
    def resolve(
        self,
        field_name: str,
        source_value: Any,
        target_value: Any,
        source_game: Game,
        target_game: Game,
    ) -> Any:
        """Return the winning value for a conflicting field."""


class KeepNewestStrategy(MergeStrategy):
    """Keep value from the game with the more recent 'modified' timestamp."""

    def resolve(self, field_name, source_value, target_value, source_game, target_game):
        s_ts = source_game.modified.timestamp() if source_game.modified else 0
        t_ts = target_game.modified.timestamp() if target_game.modified else 0
        return source_value if s_ts >= t_ts else target_value


class KeepOldestStrategy(MergeStrategy):
    """Keep value from the game with the older 'modified' timestamp."""

    def resolve(self, field_name, source_value, target_value, source_game, target_game):
        s_ts = source_game.modified.timestamp() if source_game.modified else float("inf")
        t_ts = target_game.modified.timestamp() if target_game.modified else float("inf")
        return source_value if s_ts <= t_ts else target_value


class KeepSourceStrategy(MergeStrategy):
    """Always keep the source library's value."""

    def resolve(self, field_name, source_value, target_value, source_game, target_game):
        return source_value


class KeepTargetStrategy(MergeStrategy):
    """Always keep the target library's value."""

    def resolve(self, field_name, source_value, target_value, source_game, target_game):
        return target_value


class MergeAllStrategy(MergeStrategy):
    """Union lists, prefer non-empty scalars, newest for conflicting non-empty scalars."""

    def resolve(self, field_name, source_value, target_value, source_game, target_game):
        # List fields: union
        if isinstance(source_value, list) and isinstance(target_value, list):
            # Deduplicate while preserving order
            seen = set()
            merged = []
            for item in source_value + target_value:
                key = str(item)
                if key not in seen:
                    seen.add(key)
                    merged.append(item)
            return merged

        # Prefer non-empty
        if not source_value and target_value:
            return target_value
        if source_value and not target_value:
            return source_value

        # Both non-empty: prefer newest
        s_ts = source_game.modified.timestamp() if source_game.modified else 0
        t_ts = target_game.modified.timestamp() if target_game.modified else 0
        return source_value if s_ts >= t_ts else target_value


class InteractiveStrategy(MergeStrategy):
    """Prompts via callback for each conflict."""

    def __init__(self, prompt_callback: Callable | None = None):
        self._callback = prompt_callback or self._default_prompt

    def resolve(self, field_name, source_value, target_value, source_game, target_game):
        return self._callback(field_name, source_value, target_value, source_game, target_game)

    @staticmethod
    def _default_prompt(field_name, source_value, target_value, source_game, target_game):
        # In non-interactive mode, fall back to source
        return source_value


def create_strategy(
    strategy_type: MergeStrategyType,
    prompt_callback: Callable | None = None,
) -> MergeStrategy:
    """Factory function for creating merge strategies."""
    mapping = {
        MergeStrategyType.KEEP_NEWEST: KeepNewestStrategy,
        MergeStrategyType.KEEP_OLDEST: KeepOldestStrategy,
        MergeStrategyType.KEEP_SOURCE: KeepSourceStrategy,
        MergeStrategyType.KEEP_TARGET: KeepTargetStrategy,
        MergeStrategyType.MERGE_ALL: MergeAllStrategy,
    }
    if strategy_type == MergeStrategyType.INTERACTIVE:
        return InteractiveStrategy(prompt_callback)
    cls = mapping.get(strategy_type)
    if cls is None:
        raise ValueError(f"Unknown strategy: {strategy_type}")
    return cls()
