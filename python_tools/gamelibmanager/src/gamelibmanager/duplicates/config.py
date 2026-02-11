"""Configuration for duplicate detection."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class ScoringWeights:
    """Configurable weights for each scoring signal."""

    title: float = 0.45
    year: float = 0.15
    developer: float = 0.15
    publisher: float = 0.10
    platform: float = 0.10
    gameid: float = 0.05


@dataclass
class DetectionFilter:
    """Inclusion/exclusion filters for duplicate detection."""

    include_sources: set[uuid.UUID] | None = None
    exclude_sources: set[uuid.UUID] | None = None
    include_platforms: set[uuid.UUID] | None = None
    exclude_platforms: set[uuid.UUID] | None = None
    include_hidden: bool = True
    include_uninstalled: bool = True
    name_pattern: str | None = None


@dataclass
class DetectionConfig:
    """Full configuration for a duplicate detection run."""

    threshold: float = 0.75
    weights: ScoringWeights = field(default_factory=ScoringWeights)
    source_priority: list[str] = field(
        default_factory=lambda: ["Steam", "GOG", "Epic"]
    )
    filters: DetectionFilter = field(default_factory=DetectionFilter)
    similarity_mode: bool = False
    blocking_prefix_length: int = 3
    max_group_size: int = 50

    def validate(self) -> None:
        if not 0.60 <= self.threshold <= 1.00:
            raise ValueError("Threshold must be between 0.60 and 1.00")
        if self.blocking_prefix_length < 1:
            raise ValueError("blocking_prefix_length must be >= 1")
