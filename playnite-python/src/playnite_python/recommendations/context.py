"""Context-aware filtering for mood and temporal recommendations."""
from typing import List, Dict, Optional
from datetime import datetime, timezone
from loguru import logger


class ContextualFilter:
    """Apply contextual filters based on mood, time, and other factors."""

    # Mood-to-genre mappings
    MOOD_GENRES = {
        "relaxing": ["Simulation", "Puzzle", "Casual", "Adventure"],
        "challenging": ["Action", "Platformer", "Fighting", "Strategy"],
        "story": ["RPG", "Adventure", "Visual Novel", "Interactive Fiction"],
        "social": ["Multiplayer", "Co-op", "MMO", "Party"],
        "creative": ["Sandbox", "Simulation", "Building", "Puzzle"],
        "competitive": ["Fighting", "Sports", "Racing", "Strategy", "MOBA"],
        "quick": ["Arcade", "Puzzle", "Casual", "Platformer"],
        "immersive": ["RPG", "Open World", "Simulation", "Adventure"],
    }

    # Time-of-day preferences
    TIME_PREFERENCES = {
        "morning": ["casual", "puzzle", "simulation"],
        "afternoon": ["action", "strategy", "adventure"],
        "evening": ["rpg", "story", "immersive"],
        "night": ["relaxing", "casual", "story"],
    }

    def __init__(self):
        pass

    def get_time_of_day(self) -> str:
        """Determine current time of day."""
        hour = datetime.now(timezone.utc).hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 22:
            return "evening"
        else:
            return "night"

    def filter(
        self, recommendations: List[Dict], library: List[Dict], context: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Apply contextual filters to recommendations.

        Args:
            recommendations: List of recommendations to filter
            library: Complete game library for looking up game details
            context: Context dictionary with optional keys:
                - mood: User's current mood (relaxing, challenging, story, etc.)
                - time_of_day: Time of day (morning, afternoon, evening, night)
                - session_length: Expected session length (short, medium, long)

        Returns:
            Filtered and re-scored recommendations
        """
        if not context:
            context = {}

        # Create game lookup
        game_lookup = {g["game_id"]: g for g in library}

        # Apply mood filter
        mood = context.get("mood")
        if mood and mood.lower() in self.MOOD_GENRES:
            recommendations = self._filter_by_mood(recommendations, game_lookup, mood.lower())

        # Apply time-of-day adjustment
        time_of_day = context.get("time_of_day", self.get_time_of_day())
        if time_of_day in self.TIME_PREFERENCES:
            recommendations = self._adjust_for_time(recommendations, game_lookup, time_of_day)

        # Apply session length filter
        session_length = context.get("session_length")
        if session_length:
            recommendations = self._filter_by_session_length(
                recommendations, game_lookup, session_length
            )

        # Re-sort after adjustments
        recommendations.sort(key=lambda x: x["score"], reverse=True)

        logger.info(f"Applied contextual filters: {len(recommendations)} recommendations remain")
        return recommendations

    def _filter_by_mood(
        self, recommendations: List[Dict], game_lookup: Dict, mood: str
    ) -> List[Dict]:
        """Filter and boost recommendations matching mood."""
        mood_genres = [g.lower() for g in self.MOOD_GENRES.get(mood, [])]

        filtered = []
        for rec in recommendations:
            game = game_lookup.get(rec["game_id"])
            if not game:
                continue

            game_genres = [g.lower() for g in game.get("genres", [])]
            game_tags = [t.lower() for t in game.get("tags", [])]

            # Check if game matches mood
            genre_match = any(mg in " ".join(game_genres) for mg in mood_genres)
            tag_match = any(mood in " ".join(game_tags) for _ in [mood])

            if genre_match or tag_match:
                # Boost score for mood match
                rec["score"] *= 1.3
                rec["reason"] = f"{rec['reason']} (Perfect for {mood} mood)"
                rec["factors"]["mood_boost"] = 1.3
                filtered.append(rec)
            elif rec["score"] > 0.7:  # Keep highly scored recommendations even if not perfect match
                filtered.append(rec)

        return filtered

    def _adjust_for_time(
        self, recommendations: List[Dict], game_lookup: Dict, time_of_day: str
    ) -> List[Dict]:
        """Adjust scores based on time of day preferences."""
        preferred_moods = self.TIME_PREFERENCES.get(time_of_day, [])

        for rec in recommendations:
            game = game_lookup.get(rec["game_id"])
            if not game:
                continue

            game_genres = [g.lower() for g in game.get("genres", [])]
            game_tags = [t.lower() for t in game.get("tags", [])]

            # Check if game matches time-appropriate moods
            for preferred_mood in preferred_moods:
                mood_genres = [g.lower() for g in self.MOOD_GENRES.get(preferred_mood, [])]
                if any(mg in " ".join(game_genres) for mg in mood_genres):
                    rec["score"] *= 1.15
                    rec["factors"]["time_boost"] = 1.15
                    break

        return recommendations

    def _filter_by_session_length(
        self, recommendations: List[Dict], game_lookup: Dict, session_length: str
    ) -> List[Dict]:
        """Filter based on expected session length."""
        # This is a simplified version - in production, you'd want to track
        # average session lengths per game or genre

        quick_genres = ["arcade", "puzzle", "casual", "platformer"]
        long_genres = ["rpg", "strategy", "simulation", "mmo"]

        if session_length == "short":
            # Prefer quick games
            for rec in recommendations:
                game = game_lookup.get(rec["game_id"])
                if not game:
                    continue

                game_genres = [g.lower() for g in game.get("genres", [])]
                if any(qg in " ".join(game_genres) for qg in quick_genres):
                    rec["score"] *= 1.2
                    rec["factors"]["session_boost"] = 1.2

        elif session_length == "long":
            # Prefer immersive games
            for rec in recommendations:
                game = game_lookup.get(rec["game_id"])
                if not game:
                    continue

                game_genres = [g.lower() for g in game.get("genres", [])]
                if any(lg in " ".join(game_genres) for lg in long_genres):
                    rec["score"] *= 1.2
                    rec["factors"]["session_boost"] = 1.2

        return recommendations
