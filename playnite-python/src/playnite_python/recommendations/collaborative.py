"""Collaborative filtering for game recommendations."""
from typing import List, Dict
from loguru import logger


class CollaborativeFilter:
    """
    Collaborative filtering using implicit feedback.

    For single-user scenarios, this uses playtime and ratings as implicit feedback.
    In multi-user scenarios, this would find similar users and recommend their favorites.
    """

    def __init__(self):
        self.user_game_matrix = None

    def recommend(
        self, user_id: str, library: List[Dict], play_histories: List[Dict], limit: int = 10
    ) -> List[Dict]:
        """
        Generate collaborative recommendations.

        Args:
            user_id: User identifier
            library: Complete game library
            play_histories: Play history records
            limit: Maximum number of recommendations

        Returns:
            List of recommendation dictionaries
        """
        # For single user, we use a popularity-based approach
        # In a multi-user system, this would use matrix factorization or KNN

        played_game_ids = set(h["game_id"] for h in play_histories if h["user_id"] == user_id)

        recommendations = []
        for game in library:
            if game["game_id"] in played_game_ids:
                continue

            if game.get("hidden", False):
                continue

            # Calculate popularity score from community and critic scores
            community_score = game.get("community_score", 0)
            critic_score = game.get("critic_score", 0)

            # Weighted average (favor community score)
            if community_score > 0 and critic_score > 0:
                popularity = (community_score * 0.7 + critic_score * 0.3) / 100.0
            elif community_score > 0:
                popularity = community_score / 100.0
            elif critic_score > 0:
                popularity = critic_score / 100.0
            else:
                popularity = 0

            if popularity > 0.6:  # Only recommend well-rated games
                recommendations.append(
                    {
                        "game_id": game["game_id"],
                        "score": popularity,
                        "reason": "Highly rated by the community",
                        "factors": {
                            "popularity": popularity,
                            "community_score": community_score,
                            "critic_score": critic_score,
                        },
                    }
                )

        recommendations.sort(key=lambda x: x["score"], reverse=True)
        logger.info(f"Generated {len(recommendations)} collaborative recommendations")
        return recommendations[:limit]
