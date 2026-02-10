"""Content-based filtering for game recommendations."""
from typing import List, Dict, Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from loguru import logger


class ContentBasedFilter:
    """Content-based recommendation filter using game attributes."""

    def __init__(self):
        self.vectorizer = TfidfVectorizer(max_features=1000)
        self.game_features = {}

    def build_game_features(self, game: Dict) -> str:
        """
        Combine game attributes into a feature string for TF-IDF.

        Args:
            game: Game dictionary with attributes

        Returns:
            Space-separated feature string
        """
        features = []

        # Add genres (weighted more heavily by repeating)
        if game.get("genres"):
            for genre in game["genres"]:
                features.extend([genre.lower()] * 3)  # 3x weight

        # Add developers (weighted)
        if game.get("developers"):
            for dev in game["developers"]:
                features.extend([dev.lower()] * 2)  # 2x weight

        # Add publishers
        if game.get("publishers"):
            for pub in game["publishers"]:
                features.append(pub.lower())

        # Add tags
        if game.get("tags"):
            for tag in game["tags"]:
                features.extend([tag.lower()] * 2)  # 2x weight

        # Add features/mechanics
        if game.get("features"):
            for feature in game["features"]:
                features.extend([feature.lower()] * 2)

        # Add platforms
        if game.get("platforms"):
            for platform in game["platforms"]:
                features.append(platform.lower())

        return " ".join(features)

    def identify_enjoyed_games(self, library: List[Dict], min_playtime: int = 3600) -> List[Dict]:
        """
        Identify games the user has enjoyed based on playtime and ratings.

        Args:
            library: List of games with playtime and rating data
            min_playtime: Minimum playtime in seconds to consider

        Returns:
            List of enjoyed games
        """
        enjoyed = []

        for game in library:
            playtime = game.get("playtime_seconds", 0)
            user_score = game.get("user_score", 0)
            favorite = game.get("favorite", False)
            completion_status = game.get("completion_status", "")

            # Strong signals of enjoyment
            if favorite:
                enjoyed.append(game)
            elif user_score >= 75:  # High rating
                enjoyed.append(game)
            elif playtime >= min_playtime:  # Significant playtime
                enjoyed.append(game)
            elif completion_status in ["Completed", "Beaten", "Playing"]:
                enjoyed.append(game)

        logger.debug(f"Identified {len(enjoyed)} enjoyed games from {len(library)} total")
        return enjoyed

    def calculate_similarity(self, library: List[Dict]) -> np.ndarray:
        """
        Calculate similarity matrix for all games in library.

        Args:
            library: List of game dictionaries

        Returns:
            Similarity matrix (n_games x n_games)
        """
        if not library:
            return np.array([[]])

        feature_strings = [self.build_game_features(game) for game in library]

        # Handle case where all feature strings are empty
        if all(not s.strip() for s in feature_strings):
            logger.warning("All games have empty feature strings")
            return np.zeros((len(library), len(library)))

        try:
            tfidf_matrix = self.vectorizer.fit_transform(feature_strings)
            similarity_matrix = cosine_similarity(tfidf_matrix)
            return similarity_matrix
        except ValueError as e:
            logger.error(f"Error calculating similarity: {e}")
            return np.zeros((len(library), len(library)))

    def recommend(
        self,
        user_profile: Dict,
        library: List[Dict],
        limit: int = 10,
        similarity_threshold: float = 0.3,
        min_playtime: int = 3600,
    ) -> List[Dict]:
        """
        Generate content-based recommendations.

        Args:
            user_profile: User profile data (currently unused, for future use)
            library: Complete game library
            limit: Maximum number of recommendations
            similarity_threshold: Minimum similarity score to recommend
            min_playtime: Minimum playtime to consider game "enjoyed"

        Returns:
            List of recommendation dictionaries
        """
        if not library or len(library) < 2:
            logger.warning("Library too small for recommendations")
            return []

        # Identify games user has enjoyed
        enjoyed_games = self.identify_enjoyed_games(library, min_playtime)

        if not enjoyed_games:
            logger.info("No enjoyed games found, returning popular unplayed games")
            # Fallback: recommend popular unplayed games
            return self._recommend_popular(library, limit)

        # Calculate similarity matrix
        similarity_matrix = self.calculate_similarity(library)

        if similarity_matrix.size == 0:
            logger.warning("Could not calculate similarity matrix")
            return []

        # Build recommendation list
        recommendations = []
        game_id_to_idx = {game["game_id"]: idx for idx, game in enumerate(library)}

        for game_idx, game in enumerate(library):
            # Skip if already played significantly
            if game.get("playtime_seconds", 0) > 600:  # > 10 minutes
                continue

            # Skip if hidden
            if game.get("hidden", False):
                continue

            # Calculate average similarity to enjoyed games
            enjoyed_indices = [
                game_id_to_idx[g["game_id"]]
                for g in enjoyed_games
                if g["game_id"] in game_id_to_idx
            ]

            if not enjoyed_indices:
                continue

            similarities = [similarity_matrix[game_idx][idx] for idx in enjoyed_indices]
            avg_similarity = float(np.mean(similarities))
            max_similarity = float(np.max(similarities))

            if avg_similarity >= similarity_threshold:
                # Find most similar enjoyed game for explanation
                most_similar_idx = enjoyed_indices[np.argmax(similarities)]
                most_similar_game = library[most_similar_idx]

                recommendations.append(
                    {
                        "game_id": game["game_id"],
                        "score": avg_similarity,
                        "reason": f"Similar to {most_similar_game['name']}",
                        "factors": {
                            "content_similarity": avg_similarity,
                            "max_similarity": max_similarity,
                            "similar_to": most_similar_game["name"],
                        },
                    }
                )

        # Sort by score and return top N
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        logger.info(f"Generated {len(recommendations)} content-based recommendations")
        return recommendations[:limit]

    def _recommend_popular(self, library: List[Dict], limit: int) -> List[Dict]:
        """
        Fallback: Recommend popular unplayed games.

        Args:
            library: Game library
            limit: Number of recommendations

        Returns:
            List of popular game recommendations
        """
        popular = []

        for game in library:
            # Skip if already played
            if game.get("playtime_seconds", 0) > 0:
                continue

            # Skip if hidden
            if game.get("hidden", False):
                continue

            # Use community score as popularity metric
            popularity_score = game.get("community_score", game.get("critic_score", 50)) / 100.0

            if popularity_score > 0:
                popular.append(
                    {
                        "game_id": game["game_id"],
                        "score": popularity_score,
                        "reason": "Popular game in your library",
                        "factors": {
                            "popularity": popularity_score,
                        },
                    }
                )

        popular.sort(key=lambda x: x["score"], reverse=True)
        return popular[:limit]
