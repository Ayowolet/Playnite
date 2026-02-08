"""Generate test data for benchmarks."""

from typing import List
from datetime import date, timedelta
import random

from faker import Faker

from playnite_py.database import GameOperations


class GameDataGenerator:
    """Generate realistic test game data for benchmarks."""

    def __init__(self, seed: int = 42):
        """
        Initialize data generator.

        Args:
            seed: Random seed for reproducible data
        """
        self.faker = Faker()
        Faker.seed(seed)
        random.seed(seed)

        # Common genres, platforms, tags
        self.genres = [
            'Action', 'Adventure', 'RPG', 'Strategy', 'Simulation',
            'Sports', 'Racing', 'Puzzle', 'Fighting', 'Shooter',
            'Platformer', 'Horror', 'Survival', 'Stealth', 'Roguelike'
        ]

        self.platforms = [
            'PC', 'PlayStation 5', 'PlayStation 4', 'Xbox Series X',
            'Xbox One', 'Nintendo Switch', 'Steam', 'Epic Games Store',
            'GOG', 'iOS', 'Android'
        ]

        self.tags = [
            'singleplayer', 'multiplayer', 'co-op', 'online',
            'offline', 'open-world', 'linear', 'story-rich',
            'indie', 'AAA', 'early-access', 'completed',
            'challenging', 'casual', 'relaxing', 'competitive',
            'retro', 'pixel-art', '2D', '3D', 'VR'
        ]

    def generate_test_games(self, count: int, session) -> List:
        """
        Generate test games with realistic data.

        Args:
            count: Number of games to generate
            session: Database session

        Returns:
            List of created games
        """
        ops = GameOperations(session)
        games = []

        # Pre-create platforms, genres, tags to avoid duplicates
        for platform in self.platforms:
            from playnite_py.database import LibraryOperations
            lib_ops = LibraryOperations(session)
            lib_ops.create_platform(platform)

        for genre in self.genres:
            from playnite_py.database import LibraryOperations
            lib_ops = LibraryOperations(session)
            lib_ops.create_genre(genre)

        for tag in self.tags:
            from playnite_py.database import LibraryOperations
            lib_ops = LibraryOperations(session)
            lib_ops.create_tag(tag)

        # Generate games
        for i in range(count):
            # Generate game name
            if random.random() < 0.3:
                # Some games with series numbers
                name = f"{self.faker.catch_phrase()} {random.randint(1, 5)}"
            else:
                name = self.faker.catch_phrase()

            # Random playtime (0-500 hours, with some outliers)
            playtime = int(random.lognormvariate(4, 2))  # Log-normal distribution
            playtime = min(playtime, 2000)  # Cap at 2000 hours

            # Random release date (last 20 years)
            days_ago = random.randint(0, 365 * 20)
            release_date = date.today() - timedelta(days=days_ago)

            # Random rating
            user_score = random.randint(0, 100) if random.random() < 0.8 else None

            # Random favorite status (10% are favorites)
            is_favorite = random.random() < 0.1

            # Random hidden status (5% are hidden)
            is_hidden = random.random() < 0.05

            # Create game
            game = ops.create_game(
                name=name,
                playtime=playtime,
                release_date=release_date,
                user_score=user_score,
                is_favorite=is_favorite,
                is_hidden=is_hidden
            )

            # Add 1-3 platforms
            num_platforms = random.randint(1, 3)
            for platform in random.sample(self.platforms, num_platforms):
                ops.add_platform_to_game(game.id, platform)

            # Add 1-3 genres
            num_genres = random.randint(1, 3)
            for genre in random.sample(self.genres, num_genres):
                ops.add_genre_to_game(game.id, genre)

            # Add 0-5 tags
            num_tags = random.randint(0, 5)
            if num_tags > 0:
                for tag in random.sample(self.tags, num_tags):
                    ops.add_tag_to_game(game.id, tag)

            games.append(game)

            # Commit in batches for performance
            if (i + 1) % 100 == 0:
                session.commit()

        # Final commit
        session.commit()
        return games

    def generate_with_relationships(self, count: int, session) -> List:
        """
        Generate games with full relationship data.

        This is an alias for generate_test_games with relationships enabled.

        Args:
            count: Number of games to generate
            session: Database session

        Returns:
            List of created games
        """
        return self.generate_test_games(count, session)
