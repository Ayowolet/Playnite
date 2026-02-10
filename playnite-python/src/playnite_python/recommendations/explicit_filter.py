"""Explicit filtering for user-controlled attribute-based filtering."""
from typing import List, Dict, Optional
from loguru import logger


class ExplicitFilter:
    """
    Apply explicit user-controlled filters to recommendations.

    Unlike contextual filtering (which boosts recommendations based on mood/time),
    explicit filtering hard-excludes games that don't match user criteria.
    """

    VALID_DIFFICULTY_LEVELS = ["easy", "medium", "hard", "extreme"]

    def filter(
        self,
        recommendations: List[Dict],
        library: List[Dict],
        filters: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Apply explicit filters to recommendations.

        Args:
            recommendations: List of recommendations to filter
            library: Complete game library for looking up game details
            filters: Filter dictionary with optional keys:
                - min_completion_hours: Minimum hours to complete
                - max_completion_hours: Maximum hours to complete
                - difficulty_levels: List of allowed difficulty levels
                - multiplayer_only: True/False for multiplayer filtering
                - vr_compatible: True/False for VR filtering
                - vr_required: True for VR-exclusive games
                - platforms: List of allowed platforms

        Returns:
            Filtered recommendations (hard exclusions applied)
        """
        if not filters:
            return recommendations

        # Create game lookup
        game_lookup = {g["game_id"]: g for g in library}

        initial_count = len(recommendations)
        filtered = []

        for rec in recommendations:
            game = game_lookup.get(rec["game_id"])
            if not game:
                logger.warning(f"Game {rec['game_id']} not found in library")
                continue

            # Apply all filters - if any fail, exclude the game
            if not self._passes_completion_time_filter(game, filters):
                continue

            if not self._passes_difficulty_filter(game, filters):
                continue

            if not self._passes_multiplayer_filter(game, filters):
                continue

            if not self._passes_vr_filter(game, filters):
                continue

            if not self._passes_platform_filter(game, filters):
                continue

            # Game passed all filters
            filtered.append(rec)

        logger.info(
            f"Explicit filters applied: {initial_count} → {len(filtered)} recommendations "
            f"({initial_count - len(filtered)} filtered out)"
        )

        return filtered

    def _passes_completion_time_filter(
        self, game: Dict, filters: Dict
    ) -> bool:
        """Check if game passes completion time filter."""
        min_hours = filters.get("min_completion_hours")
        max_hours = filters.get("max_completion_hours")

        if min_hours is None and max_hours is None:
            return True

        completion_time = game.get("time_to_complete")

        # If no completion time data, exclude from time-based filtering
        if completion_time is None:
            logger.debug(
                f"Game {game.get('name')} excluded: no completion time data"
            )
            return False

        # Check minimum
        if min_hours is not None and completion_time < min_hours:
            logger.debug(
                f"Game {game.get('name')} excluded: {completion_time}h < {min_hours}h minimum"
            )
            return False

        # Check maximum
        if max_hours is not None and completion_time > max_hours:
            logger.debug(
                f"Game {game.get('name')} excluded: {completion_time}h > {max_hours}h maximum"
            )
            return False

        return True

    def _passes_difficulty_filter(self, game: Dict, filters: Dict) -> bool:
        """Check if game passes difficulty filter."""
        allowed_levels = filters.get("difficulty_levels")

        if not allowed_levels:
            return True

        # Validate difficulty levels
        invalid_levels = [
            lvl for lvl in allowed_levels if lvl not in self.VALID_DIFFICULTY_LEVELS
        ]
        if invalid_levels:
            logger.warning(f"Invalid difficulty levels: {invalid_levels}")
            return True  # Don't filter if invalid levels provided

        difficulty = game.get("difficulty")

        # If no difficulty data, exclude from difficulty filtering
        if difficulty is None:
            logger.debug(
                f"Game {game.get('name')} excluded: no difficulty rating"
            )
            return False

        if difficulty not in allowed_levels:
            logger.debug(
                f"Game {game.get('name')} excluded: difficulty '{difficulty}' not in {allowed_levels}"
            )
            return False

        return True

    def _passes_multiplayer_filter(self, game: Dict, filters: Dict) -> bool:
        """Check if game passes multiplayer filter."""
        multiplayer_only = filters.get("multiplayer_only")

        if multiplayer_only is None:
            return True

        features = game.get("features", [])
        has_multiplayer = any(
            "multiplayer" in str(f).lower() or "co-op" in str(f).lower()
            for f in features
        )

        if multiplayer_only and not has_multiplayer:
            logger.debug(
                f"Game {game.get('name')} excluded: single-player only"
            )
            return False

        if not multiplayer_only and has_multiplayer:
            logger.debug(
                f"Game {game.get('name')} excluded: has multiplayer"
            )
            return False

        return True

    def _passes_vr_filter(self, game: Dict, filters: Dict) -> bool:
        """Check if game passes VR filter."""
        vr_compatible = filters.get("vr_compatible")
        vr_required = filters.get("vr_required")

        # If VR-exclusive filter is set, check vr_required field
        if vr_required is True:
            if not game.get("vr_required", False):
                logger.debug(
                    f"Game {game.get('name')} excluded: not VR-exclusive"
                )
                return False
            return True

        # If VR compatibility filter is set
        if vr_compatible is not None:
            game_vr_compatible = game.get("vr_compatible", False)

            if vr_compatible and not game_vr_compatible:
                logger.debug(
                    f"Game {game.get('name')} excluded: not VR-compatible"
                )
                return False

            if not vr_compatible and game_vr_compatible:
                logger.debug(
                    f"Game {game.get('name')} excluded: is VR-compatible"
                )
                return False

        return True

    def _passes_platform_filter(self, game: Dict, filters: Dict) -> bool:
        """Check if game passes platform filter."""
        allowed_platforms = filters.get("platforms")

        if not allowed_platforms:
            return True

        game_platforms = game.get("platforms", [])

        # Normalize platform names for comparison (case-insensitive)
        game_platforms_lower = [p.lower() for p in game_platforms]
        allowed_platforms_lower = [p.lower() for p in allowed_platforms]

        # Check if any game platform matches allowed platforms
        has_match = any(
            gp in allowed_platforms_lower for gp in game_platforms_lower
        )

        if not has_match:
            logger.debug(
                f"Game {game.get('name')} excluded: platforms {game_platforms} "
                f"not in allowed {allowed_platforms}"
            )
            return False

        return True

    def get_filter_summary(self, filters: Optional[Dict]) -> str:
        """
        Generate human-readable summary of active filters.

        Args:
            filters: Filter dictionary

        Returns:
            String summary of active filters
        """
        if not filters:
            return "No filters active"

        active = []

        if filters.get("min_completion_hours") is not None:
            active.append(f"≥{filters['min_completion_hours']}h to complete")

        if filters.get("max_completion_hours") is not None:
            active.append(f"≤{filters['max_completion_hours']}h to complete")

        if filters.get("difficulty_levels"):
            levels = ", ".join(filters["difficulty_levels"])
            active.append(f"Difficulty: {levels}")

        if filters.get("multiplayer_only") is True:
            active.append("Multiplayer only")
        elif filters.get("multiplayer_only") is False:
            active.append("Single-player only")

        if filters.get("vr_required") is True:
            active.append("VR-exclusive only")
        elif filters.get("vr_compatible") is True:
            active.append("VR-compatible")
        elif filters.get("vr_compatible") is False:
            active.append("Non-VR only")

        if filters.get("platforms"):
            platforms = ", ".join(filters["platforms"])
            active.append(f"Platforms: {platforms}")

        if not active:
            return "No filters active"

        return " | ".join(active)
