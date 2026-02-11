from .normalizer import TitleNormalizer
from .scorer import DuplicateScorer, MatchScore, ScoringWeights
from .detector import DuplicateDetector
from .group import DuplicateGroup
from .config import DetectionConfig, DetectionFilter
from .report import DuplicateReport
from .history import ResolutionHistory, ResolutionRecord

__all__ = [
    "TitleNormalizer", "DuplicateScorer", "MatchScore", "ScoringWeights",
    "DuplicateDetector", "DuplicateGroup", "DetectionConfig", "DetectionFilter",
    "DuplicateReport", "ResolutionHistory", "ResolutionRecord",
]
