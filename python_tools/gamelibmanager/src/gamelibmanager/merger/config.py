"""Configuration for library merge operations."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from .strategy import MergeStrategyType


@dataclass
class MergeConfig:
    """Configuration for a library merge operation."""

    strategy_type: MergeStrategyType = MergeStrategyType.MERGE_ALL
    backup_dir: str = ""
    include_media: bool = True
    add_new_games: bool = True
    update_existing: bool = True
    preserve_target_ids: bool = True
    selective_game_ids: set[uuid.UUID] | None = None
    selective_categories: set[str] | None = None
    fuzzy_match_threshold: float = 0.85
    incremental: bool = False
    last_merge_timestamp: datetime | None = None
    custom_field_strategies: dict[str, MergeStrategyType] = field(default_factory=dict)
    source_library_path: str = ""
    target_library_path: str = ""

    def to_json(self) -> str:
        """Export configuration for reuse."""
        d = {
            "strategy_type": self.strategy_type.value,
            "backup_dir": self.backup_dir,
            "include_media": self.include_media,
            "add_new_games": self.add_new_games,
            "update_existing": self.update_existing,
            "preserve_target_ids": self.preserve_target_ids,
            "fuzzy_match_threshold": self.fuzzy_match_threshold,
            "incremental": self.incremental,
            "source_library_path": self.source_library_path,
            "target_library_path": self.target_library_path,
        }
        if self.selective_game_ids:
            d["selective_game_ids"] = [str(g) for g in self.selective_game_ids]
        if self.selective_categories:
            d["selective_categories"] = list(self.selective_categories)
        if self.last_merge_timestamp:
            d["last_merge_timestamp"] = self.last_merge_timestamp.isoformat()
        if self.custom_field_strategies:
            d["custom_field_strategies"] = {
                k: v.value for k, v in self.custom_field_strategies.items()
            }
        return json.dumps(d, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> MergeConfig:
        """Import configuration."""
        d = json.loads(json_str)
        config = cls(
            strategy_type=MergeStrategyType(d.get("strategy_type", "merge_all")),
            backup_dir=d.get("backup_dir", ""),
            include_media=d.get("include_media", True),
            add_new_games=d.get("add_new_games", True),
            update_existing=d.get("update_existing", True),
            preserve_target_ids=d.get("preserve_target_ids", True),
            fuzzy_match_threshold=d.get("fuzzy_match_threshold", 0.85),
            incremental=d.get("incremental", False),
            source_library_path=d.get("source_library_path", ""),
            target_library_path=d.get("target_library_path", ""),
        )
        if "selective_game_ids" in d:
            config.selective_game_ids = {uuid.UUID(g) for g in d["selective_game_ids"]}
        if "selective_categories" in d:
            config.selective_categories = set(d["selective_categories"])
        if "last_merge_timestamp" in d and d["last_merge_timestamp"]:
            config.last_merge_timestamp = datetime.fromisoformat(d["last_merge_timestamp"])
        if "custom_field_strategies" in d:
            config.custom_field_strategies = {
                k: MergeStrategyType(v)
                for k, v in d["custom_field_strategies"].items()
            }
        return config
