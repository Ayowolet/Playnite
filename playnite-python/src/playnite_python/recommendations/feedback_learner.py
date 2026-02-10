"""Feedback learning system for improving recommendations over time."""
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
from loguru import logger
from collections import defaultdict


class FeedbackLearner:
    """
    Learns from user feedback to improve recommendation accuracy.

    Tracks which recommendations were accepted, dismissed, or ignored,
    and adjusts algorithm weights accordingly.
    """

    def __init__(self):
        self.algorithm_weights = {
            "content": 0.6,
            "collaborative": 0.4,
        }
        self.min_weight = 0.1
        self.max_weight = 0.9
        self.learning_rate = 0.05

    def process_feedback(
        self,
        recommendation_id: int,
        game_id: str,
        feedback_type: str,
        recommendation_data: Dict
    ) -> Dict:
        """
        Process user feedback and update learning metrics.

        Args:
            recommendation_id: ID of the recommendation
            game_id: Game that was recommended
            feedback_type: 'liked', 'played', 'dismissed', 'hidden'
            recommendation_data: Original recommendation with sources and factors

        Returns:
            Updated metrics and weight adjustments
        """
        logger.info(f"Processing feedback: {feedback_type} for game {game_id}")

        # Determine if feedback is positive or negative
        is_positive = feedback_type in ['liked', 'played']

        # Extract which algorithms contributed
        sources = recommendation_data.get('sources', [])

        # Adjust weights based on feedback
        if is_positive:
            return self._reward_sources(sources)
        else:
            return self._penalize_sources(sources)

    def _reward_sources(self, sources: List[str]) -> Dict:
        """Increase weights for algorithms that made good recommendations."""
        adjustments = {}

        for source in sources:
            if source in self.algorithm_weights:
                old_weight = self.algorithm_weights[source]
                new_weight = min(
                    self.max_weight,
                    old_weight + self.learning_rate
                )
                self.algorithm_weights[source] = new_weight
                adjustments[source] = {
                    'old': old_weight,
                    'new': new_weight,
                    'change': new_weight - old_weight
                }
                logger.debug(f"Rewarded {source}: {old_weight:.3f} -> {new_weight:.3f}")

        # Normalize weights to sum to 1.0
        self._normalize_weights()

        return {
            'action': 'reward',
            'adjustments': adjustments,
            'current_weights': self.algorithm_weights.copy()
        }

    def _penalize_sources(self, sources: List[str]) -> Dict:
        """Decrease weights for algorithms that made poor recommendations."""
        adjustments = {}

        for source in sources:
            if source in self.algorithm_weights:
                old_weight = self.algorithm_weights[source]
                new_weight = max(
                    self.min_weight,
                    old_weight - self.learning_rate
                )
                self.algorithm_weights[source] = new_weight
                adjustments[source] = {
                    'old': old_weight,
                    'new': new_weight,
                    'change': new_weight - old_weight
                }
                logger.debug(f"Penalized {source}: {old_weight:.3f} -> {new_weight:.3f}")

        # Normalize weights to sum to 1.0
        self._normalize_weights()

        return {
            'action': 'penalize',
            'adjustments': adjustments,
            'current_weights': self.algorithm_weights.copy()
        }

    def _normalize_weights(self):
        """Normalize weights to sum to 1.0."""
        total = sum(self.algorithm_weights.values())
        if total > 0:
            for key in self.algorithm_weights:
                self.algorithm_weights[key] /= total

    def get_current_weights(self) -> Dict[str, float]:
        """Get current algorithm weights."""
        return self.algorithm_weights.copy()

    def calculate_accuracy_metrics(
        self,
        recommendations_with_feedback: List[Dict],
        time_window_days: int = 30
    ) -> Dict:
        """
        Calculate recommendation accuracy metrics.

        Args:
            recommendations_with_feedback: List of recommendations with user feedback
            time_window_days: Only consider feedback from last N days

        Returns:
            Accuracy metrics by algorithm and overall
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=time_window_days)

        # Filter recent recommendations
        recent = [
            r for r in recommendations_with_feedback
            if r.get('generated_at') and
            datetime.fromisoformat(r['generated_at'].replace('Z', '+00:00')) > cutoff_date
        ]

        if not recent:
            return {
                'total_recommendations': 0,
                'accuracy': 0.0,
                'by_algorithm': {},
                'time_window_days': time_window_days
            }

        # Count by algorithm
        algorithm_stats = defaultdict(lambda: {'total': 0, 'positive': 0})

        for rec in recent:
            feedback = rec.get('user_feedback')
            sources = rec.get('sources', [])

            if feedback:
                is_positive = feedback in ['liked', 'played']

                for source in sources:
                    algorithm_stats[source]['total'] += 1
                    if is_positive:
                        algorithm_stats[source]['positive'] += 1

        # Calculate accuracy by algorithm
        by_algorithm = {}
        for algo, stats in algorithm_stats.items():
            accuracy = stats['positive'] / stats['total'] if stats['total'] > 0 else 0.0
            by_algorithm[algo] = {
                'accuracy': accuracy,
                'total': stats['total'],
                'positive': stats['positive']
            }

        # Calculate overall accuracy
        total_recs = sum(s['total'] for s in algorithm_stats.values())
        total_positive = sum(s['positive'] for s in algorithm_stats.values())
        overall_accuracy = total_positive / total_recs if total_recs > 0 else 0.0

        logger.info(f"Accuracy metrics: {overall_accuracy:.2%} over {time_window_days} days")

        return {
            'total_recommendations': total_recs,
            'accuracy': overall_accuracy,
            'by_algorithm': by_algorithm,
            'time_window_days': time_window_days,
            'cutoff_date': cutoff_date.isoformat()
        }

    def auto_tune_weights(self, accuracy_metrics: Dict) -> Dict:
        """
        Automatically tune algorithm weights based on accuracy metrics.

        Args:
            accuracy_metrics: Output from calculate_accuracy_metrics

        Returns:
            Weight adjustment summary
        """
        by_algorithm = accuracy_metrics.get('by_algorithm', {})

        if not by_algorithm:
            logger.warning("No accuracy data available for auto-tuning")
            return {'status': 'no_data', 'weights': self.algorithm_weights.copy()}

        # Adjust weights proportionally to accuracy
        adjustments = {}

        for algo, metrics in by_algorithm.items():
            if algo in self.algorithm_weights:
                accuracy = metrics['accuracy']
                old_weight = self.algorithm_weights[algo]

                # If accuracy > 70%, increase weight; if < 30%, decrease weight
                if accuracy > 0.7:
                    adjustment = self.learning_rate * (accuracy - 0.7)
                    new_weight = min(self.max_weight, old_weight + adjustment)
                elif accuracy < 0.3:
                    adjustment = self.learning_rate * (0.3 - accuracy)
                    new_weight = max(self.min_weight, old_weight - adjustment)
                else:
                    # Accuracy in acceptable range, minor adjustment toward 50%
                    new_weight = old_weight

                self.algorithm_weights[algo] = new_weight
                adjustments[algo] = {
                    'old': old_weight,
                    'new': new_weight,
                    'accuracy': accuracy
                }

        # Normalize
        self._normalize_weights()

        logger.info(f"Auto-tuned weights: {self.algorithm_weights}")

        return {
            'status': 'tuned',
            'adjustments': adjustments,
            'new_weights': self.algorithm_weights.copy()
        }
