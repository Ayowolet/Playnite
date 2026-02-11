from .matcher import GameMatcher, MatchResult, MatchWeights
from .detector import (
    DuplicateDetector,
    DuplicateGroup,
    DetectorConfig,
    DuplicateReport,
)
from .resolver import DuplicateResolver, ResolutionAction, ResolutionRecord

__all__ = [
    "GameMatcher",
    "MatchResult",
    "MatchWeights",
    "DuplicateDetector",
    "DuplicateGroup",
    "DetectorConfig",
    "DuplicateReport",
    "DuplicateResolver",
    "ResolutionAction",
    "ResolutionRecord",
]
