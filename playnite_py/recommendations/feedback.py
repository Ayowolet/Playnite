"""
Feedback engine — records user reactions to recommendations and
adjusts recommendation weights based on cumulative signal.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ..config import RecommendationConfig
from ..models.game import Game
from ..models.user_profile import RecommendationFeedback, UserProfile


# Action → signed signal value used for weight updates
_ACTION_SIGNALS: Dict[str, float] = {
    "played":            +1.0,
    "liked":             +0.8,
    "added_to_wishlist": +0.6,
    "ignored":           -0.1,
    "dismissed":         -0.5,
    "disliked":          -0.8,
}


class FeedbackEngine:
    """
    Records user feedback on recommendations and updates the user profile's
    scoring weights so future recommendations improve over time.
    """

    def __init__(self, config: Optional[RecommendationConfig] = None) -> None:
        self.config = config or RecommendationConfig()

    # ------------------------------------------------------------------ #
    # Recording                                                            #
    # ------------------------------------------------------------------ #

    def record_feedback(
        self,
        user_id: str,
        recommendation_id: str,
        game: Game,
        action: str,
        content_score: float = 0.0,
        collaborative_score: float = 0.0,
        final_score: float = 0.0,
        notes: Optional[str] = None,
    ) -> RecommendationFeedback:
        """Create and return a new feedback record (caller is responsible for saving)."""
        if action not in _ACTION_SIGNALS:
            raise ValueError(f"Unknown action '{action}'. Valid: {list(_ACTION_SIGNALS)}")

        return RecommendationFeedback(
            id=str(uuid.uuid4()),
            user_id=user_id,
            recommendation_id=recommendation_id,
            game_id=game.id,
            action=action,
            timestamp=datetime.utcnow(),
            notes=notes,
            content_score=content_score,
            collaborative_score=collaborative_score,
            final_score=final_score,
        )

    # ------------------------------------------------------------------ #
    # Weight adjustment                                                    #
    # ------------------------------------------------------------------ #

    def update_profile_from_feedback(
        self,
        profile: UserProfile,
        feedback_list: List[RecommendationFeedback],
        game_map: Dict[str, Game],
    ) -> UserProfile:
        """
        Analyse recent feedback and update the profile's scoring weights.

        Called periodically (e.g., every time recommendations are generated).
        """
        if len(feedback_list) < self.config.min_feedback_count:
            return profile  # Not enough signal yet

        lr = self.config.feedback_learning_rate

        for fb in feedback_list:
            signal = _ACTION_SIGNALS.get(fb.action, 0.0)
            game = game_map.get(fb.game_id)
            if game is None:
                continue

            # Update genre weights
            for genre in game.genres:
                current = profile.genre_weights.get(genre, 0.5)
                profile.genre_weights[genre] = float(max(0.0, min(1.0, current + lr * signal)))

            # Update mechanic weights
            for mechanic in game.mechanics:
                current = profile.mechanic_weights.get(mechanic, 0.5)
                profile.mechanic_weights[mechanic] = float(max(0.0, min(1.0, current + lr * signal)))

            # Update theme weights
            for theme in game.themes:
                current = profile.theme_weights.get(theme, 0.5)
                profile.theme_weights[theme] = float(max(0.0, min(1.0, current + lr * signal)))

            # Update tag weights
            for tag in game.tags:
                current = profile.tag_weights.get(tag, 0.5)
                profile.tag_weights[tag] = float(max(0.0, min(1.0, current + lr * signal)))

        profile.updated_at = datetime.utcnow()
        return profile

    def adjust_engine_weights(
        self,
        feedback_list: List[RecommendationFeedback],
        current_content_weight: float,
        current_collab_weight: float,
    ) -> Tuple[float, float]:
        """
        Adjust content vs collaborative filter weights based on which signal
        was more predictive of positive outcomes.

        Returns (new_content_weight, new_collab_weight).
        """
        if not feedback_list:
            return current_content_weight, current_collab_weight

        content_correct = 0
        collab_correct = 0
        total = 0

        for fb in feedback_list:
            if fb.content_score is None or fb.collaborative_score is None:
                continue
            is_positive = _ACTION_SIGNALS.get(fb.action, 0.0) > 0
            content_predicted_positive = (fb.content_score or 0.0) > 0.5
            collab_predicted_positive = (fb.collaborative_score or 0.0) > 0.5
            if content_predicted_positive == is_positive:
                content_correct += 1
            if collab_predicted_positive == is_positive:
                collab_correct += 1
            total += 1

        if total < 5:
            return current_content_weight, current_collab_weight

        content_acc = content_correct / total
        collab_acc = collab_correct / total
        total_acc = content_acc + collab_acc

        if total_acc < 0.01:
            return current_content_weight, current_collab_weight

        # Proportion-based rebalancing, smoothed with current weights
        lr = 0.05
        new_content = current_content_weight * (1 - lr) + (content_acc / total_acc) * (current_content_weight + current_collab_weight) * lr
        new_collab = current_collab_weight * (1 - lr) + (collab_acc / total_acc) * (current_content_weight + current_collab_weight) * lr

        # Renormalise
        total_w = new_content + new_collab
        if total_w > 0:
            ratio = (current_content_weight + current_collab_weight) / total_w
            new_content *= ratio
            new_collab *= ratio

        return round(new_content, 3), round(new_collab, 3)

    # ------------------------------------------------------------------ #
    # Accuracy metrics                                                     #
    # ------------------------------------------------------------------ #

    def get_accuracy_metrics(
        self, feedback_list: List[RecommendationFeedback]
    ) -> Dict[str, float]:
        """Compute precision, acceptance rate, and other accuracy stats."""
        if not feedback_list:
            return {}

        total = len(feedback_list)
        positive = sum(1 for fb in feedback_list if _ACTION_SIGNALS.get(fb.action, 0) > 0)
        negative = sum(1 for fb in feedback_list if _ACTION_SIGNALS.get(fb.action, 0) < 0)
        played = sum(1 for fb in feedback_list if fb.action == "played")

        return {
            "total_feedback": total,
            "acceptance_rate": round(positive / total, 3),
            "rejection_rate": round(negative / total, 3),
            "play_conversion_rate": round(played / total, 3),
            "positive_count": positive,
            "negative_count": negative,
            "played_count": played,
        }

    def get_feedback_stats(self, feedback_list: List[RecommendationFeedback]) -> Dict:
        """Detailed breakdown by action type."""
        by_action: Dict[str, int] = {}
        for fb in feedback_list:
            by_action[fb.action] = by_action.get(fb.action, 0) + 1

        accuracy = self.get_accuracy_metrics(feedback_list)
        return {"by_action": by_action, "accuracy": accuracy}
