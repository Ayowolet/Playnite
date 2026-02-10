"""Main recommendation engine combining multiple algorithms."""
from typing import List, Dict, Optional
from loguru import logger

from .content_based import ContentBasedFilter
from .collaborative import CollaborativeFilter
from .context import ContextualFilter
from .explicit_filter import ExplicitFilter
from .feedback_learner import FeedbackLearner


class RecommendationEngine:
    """
    Hybrid recommendation engine combining multiple approaches.

    Uses content-based filtering, collaborative filtering, and contextual
    adjustments to generate personalized game recommendations.
    """

    def __init__(self, feedback_learner: Optional[FeedbackLearner] = None):
        self.content_filter = ContentBasedFilter()
        self.collaborative_filter = CollaborativeFilter()
        self.context_filter = ContextualFilter()
        self.explicit_filter = ExplicitFilter()
        self.feedback_learner = feedback_learner or FeedbackLearner()

    def generate(
        self,
        user_id: str,
        library: List[Dict],
        play_histories: Optional[List[Dict]] = None,
        context: Optional[Dict] = None,
        filters: Optional[Dict] = None,
        limit: int = 10,
    ) -> List[Dict]:
        """
        Generate hybrid recommendations combining multiple algorithms.

        Args:
            user_id: User identifier
            library: Complete game library with metadata
            play_histories: Optional play history records
            context: Optional context (mood, time_of_day, session_length)
            filters: Optional explicit filters (time_to_complete, difficulty, etc.)
            limit: Maximum number of recommendations

        Returns:
            List of recommendation dictionaries with game_id, score, reason, factors
        """
        if not library:
            logger.warning("Empty library provided")
            return []

        play_histories = play_histories or []

        logger.info(
            f"Generating recommendations for user {user_id}: {len(library)} games, {len(play_histories)} play records"
        )

        # Get recommendations from each algorithm
        content_recs = self.content_filter.recommend({}, library, limit=limit * 2)
        collab_recs = self.collaborative_filter.recommend(
            user_id, library, play_histories, limit=limit * 2
        )

        logger.debug(f"Content-based: {len(content_recs)} recommendations")
        logger.debug(f"Collaborative: {len(collab_recs)} recommendations")

        # Merge recommendations
        merged = self._merge_recommendations(content_recs, collab_recs, library)

        logger.debug(f"Merged: {len(merged)} recommendations")

        # Apply contextual filters
        if context:
            merged = self.context_filter.filter(merged, library, context)
            logger.debug(f"After context filter: {len(merged)} recommendations")

        # Apply explicit filters
        if filters:
            filter_summary = self.explicit_filter.get_filter_summary(filters)
            logger.info(f"Applying explicit filters: {filter_summary}")
            merged = self.explicit_filter.filter(merged, library, filters)
            logger.debug(f"After explicit filters: {len(merged)} recommendations")

        # Sort and limit
        merged.sort(key=lambda x: x["score"], reverse=True)
        result = merged[:limit]

        # Enrich with game names
        game_lookup = {g["game_id"]: g for g in library}
        for rec in result:
            game = game_lookup.get(rec["game_id"])
            if game:
                rec["game_name"] = game["name"]

        logger.info(f"Generated {len(result)} final recommendations")
        return result

    def _merge_recommendations(
        self, content_recs: List[Dict], collab_recs: List[Dict], library: List[Dict]
    ) -> List[Dict]:
        """
        Merge recommendations from multiple algorithms with weighted scoring.

        Uses learned weights from feedback if available.

        Args:
            content_recs: Content-based recommendations
            collab_recs: Collaborative recommendations
            library: Game library for fallback

        Returns:
            Merged recommendation list
        """
        merged = {}

        # Get current weights from feedback learner
        weights = self.feedback_learner.get_current_weights()
        content_weight = weights.get("content", 0.6)
        collab_weight = weights.get("collaborative", 0.4)

        logger.debug(f"Using weights: content={content_weight:.3f}, collab={collab_weight:.3f}")

        # Content-based: learned weight
        for rec in content_recs:
            game_id = rec["game_id"]
            merged[game_id] = {
                **rec,
                "score": rec["score"] * content_weight,
                "sources": ["content"],
            }

        # Collaborative: learned weight
        for rec in collab_recs:
            game_id = rec["game_id"]
            if game_id in merged:
                merged[game_id]["score"] += rec["score"] * collab_weight
                merged[game_id]["reason"] = "Similar to games you enjoyed and highly rated"
                merged[game_id]["sources"].append("collaborative")
                # Merge factors
                if "factors" not in merged[game_id]:
                    merged[game_id]["factors"] = {}
                merged[game_id]["factors"].update(rec.get("factors", {}))
            else:
                merged[game_id] = {
                    **rec,
                    "score": rec["score"] * collab_weight,
                    "sources": ["collaborative"],
                }

        result = list(merged.values())

        # If we don't have enough recommendations, add popular unplayed games
        if len(result) < 10:
            result.extend(self._get_popular_fallback(library, set(merged.keys())))

        return result

    def _get_popular_fallback(
        self, library: List[Dict], exclude_ids: set, limit: int = 10
    ) -> List[Dict]:
        """
        Get popular games as fallback recommendations.

        Args:
            library: Game library
            exclude_ids: Game IDs to exclude (already recommended)
            limit: Maximum number of fallback recommendations

        Returns:
            List of fallback recommendations
        """
        fallbacks = []

        for game in library:
            if game["game_id"] in exclude_ids:
                continue

            if game.get("playtime_seconds", 0) > 0:
                continue

            if game.get("hidden", False):
                continue

            # Calculate popularity
            community_score = game.get("community_score", 0)
            critic_score = game.get("critic_score", 0)

            if community_score > 0 or critic_score > 0:
                popularity = max(community_score, critic_score) / 100.0
                fallbacks.append(
                    {
                        "game_id": game["game_id"],
                        "score": popularity * 0.3,  # Lower weight for fallbacks
                        "reason": "Popular in your library",
                        "factors": {"popularity": popularity, "fallback": True},
                        "sources": ["fallback"],
                    }
                )

        fallbacks.sort(key=lambda x: x["score"], reverse=True)
        return fallbacks[:limit]
