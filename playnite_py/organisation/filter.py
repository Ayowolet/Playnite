"""Game filtering system with support for multiple filter criteria."""

from typing import List, Optional, Any, Dict
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from datetime import datetime, timedelta

from ..models import Game, Platform, Genre, Developer, Publisher, Category, Tag, CompletionStatus
from ..models.enums import FilterOperator


class FilterBuilder:
    """Builder for constructing complex filter queries."""

    def __init__(self, session: Session):
        self.session = session
        self.filters = []

    def by_name(self, name: str, operator: FilterOperator = FilterOperator.CONTAINS) -> 'FilterBuilder':
        """Filter by game name."""
        if operator == FilterOperator.CONTAINS:
            self.filters.append(Game.name.ilike(f'%{name}%'))
        elif operator == FilterOperator.EQUALS:
            self.filters.append(Game.name == name)
        elif operator == FilterOperator.NOT_CONTAINS:
            self.filters.append(~Game.name.ilike(f'%{name}%'))
        return self

    def by_platform(self, platforms: List[str]) -> 'FilterBuilder':
        """Filter by platforms."""
        if platforms:
            self.filters.append(
                Game.platforms.any(Platform.name.in_(platforms))
            )
        return self

    def by_genre(self, genres: List[str]) -> 'FilterBuilder':
        """Filter by genres."""
        if genres:
            self.filters.append(
                Game.genres.any(Genre.name.in_(genres))
            )
        return self

    def by_developer(self, developers: List[str]) -> 'FilterBuilder':
        """Filter by developers."""
        if developers:
            self.filters.append(
                Game.developers.any(Developer.name.in_(developers))
            )
        return self

    def by_publisher(self, publishers: List[str]) -> 'FilterBuilder':
        """Filter by publishers."""
        if publishers:
            self.filters.append(
                Game.publishers.any(Publisher.name.in_(publishers))
            )
        return self

    def by_category(self, categories: List[str]) -> 'FilterBuilder':
        """Filter by categories."""
        if categories:
            self.filters.append(
                Game.categories.any(Category.name.in_(categories))
            )
        return self

    def by_tag(self, tags: List[str]) -> 'FilterBuilder':
        """Filter by tags."""
        if tags:
            self.filters.append(
                Game.tags.any(Tag.name.in_(tags))
            )
        return self

    def by_completion_status(self, statuses: List[str]) -> 'FilterBuilder':
        """Filter by completion status."""
        if statuses:
            self.filters.append(
                Game.completion_status.has(CompletionStatus.name.in_(statuses))
            )
        return self

    def by_release_year(self, min_year: Optional[int] = None,
                        max_year: Optional[int] = None) -> 'FilterBuilder':
        """Filter by release year range."""
        if min_year:
            self.filters.append(func.strftime('%Y', Game.release_date) >= str(min_year))
        if max_year:
            self.filters.append(func.strftime('%Y', Game.release_date) <= str(max_year))
        return self

    def by_playtime(self, min_minutes: Optional[int] = None,
                    max_minutes: Optional[int] = None) -> 'FilterBuilder':
        """Filter by playtime in minutes."""
        if min_minutes is not None:
            self.filters.append(Game.playtime >= min_minutes)
        if max_minutes is not None:
            self.filters.append(Game.playtime <= max_minutes)
        return self

    def by_rating(self, min_rating: Optional[float] = None,
                  max_rating: Optional[float] = None,
                  rating_type: str = 'user') -> 'FilterBuilder':
        """Filter by rating (user, critic, or community)."""
        rating_field = {
            'user': Game.user_score,
            'critic': Game.critic_score,
            'community': Game.community_score
        }.get(rating_type, Game.user_score)

        if min_rating is not None:
            self.filters.append(rating_field >= min_rating)
        if max_rating is not None:
            self.filters.append(rating_field <= max_rating)
        return self

    def by_last_played(self, days_ago: Optional[int] = None) -> 'FilterBuilder':
        """Filter by last played date."""
        if days_ago is not None:
            cutoff_date = datetime.utcnow().date() - timedelta(days=days_ago)
            self.filters.append(Game.last_played >= cutoff_date)
        return self

    def by_favorite(self, is_favorite: bool = True) -> 'FilterBuilder':
        """Filter by favorite status."""
        self.filters.append(Game.is_favorite == is_favorite)
        return self

    def by_hidden(self, is_hidden: bool = False) -> 'FilterBuilder':
        """Filter by hidden status."""
        self.filters.append(Game.is_hidden == is_hidden)
        return self

    def by_installed(self, is_installed: bool = True) -> 'FilterBuilder':
        """Filter by installation status."""
        self.filters.append(Game.is_installed == is_installed)
        return self

    def build(self) -> List:
        """Build and return the filter list."""
        return self.filters


class GameFilter:
    """High-level interface for filtering games with multiple criteria."""

    def __init__(self, session: Session):
        self.session = session

    def filter_games(self, filter_config: Dict[str, Any],
                     sort_by: Optional[str] = None,
                     sort_desc: bool = False,
                     limit: Optional[int] = None,
                     offset: int = 0) -> List[Game]:
        """
        Filter games based on configuration dictionary.

        Args:
            filter_config: Dictionary with filter criteria
            sort_by: Field to sort by (name, release_date, playtime, etc.)
            sort_desc: Sort in descending order
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of filtered games
        """
        query = self.session.query(Game)

        # Apply filters
        builder = FilterBuilder(self.session)

        # Name filter
        if 'name' in filter_config:
            builder.by_name(filter_config['name'])

        # Platform filter
        if 'platforms' in filter_config:
            builder.by_platform(filter_config['platforms'])

        # Genre filter
        if 'genres' in filter_config:
            builder.by_genre(filter_config['genres'])

        # Developer filter
        if 'developers' in filter_config:
            builder.by_developer(filter_config['developers'])

        # Publisher filter
        if 'publishers' in filter_config:
            builder.by_publisher(filter_config['publishers'])

        # Category filter
        if 'categories' in filter_config:
            builder.by_category(filter_config['categories'])

        # Tag filter
        if 'tags' in filter_config:
            builder.by_tag(filter_config['tags'])

        # Completion status filter
        if 'completion_statuses' in filter_config:
            builder.by_completion_status(filter_config['completion_statuses'])

        # Release year filter
        if 'release_year_min' in filter_config or 'release_year_max' in filter_config:
            builder.by_release_year(
                filter_config.get('release_year_min'),
                filter_config.get('release_year_max')
            )

        # Playtime filter
        if 'playtime_min' in filter_config or 'playtime_max' in filter_config:
            builder.by_playtime(
                filter_config.get('playtime_min'),
                filter_config.get('playtime_max')
            )

        # Rating filter
        if 'rating_min' in filter_config or 'rating_max' in filter_config:
            builder.by_rating(
                filter_config.get('rating_min'),
                filter_config.get('rating_max'),
                filter_config.get('rating_type', 'user')
            )

        # Favorite filter
        if 'is_favorite' in filter_config:
            builder.by_favorite(filter_config['is_favorite'])

        # Hidden filter (default to showing non-hidden)
        if 'is_hidden' in filter_config:
            builder.by_hidden(filter_config['is_hidden'])
        else:
            builder.by_hidden(False)

        # Installed filter
        if 'is_installed' in filter_config:
            builder.by_installed(filter_config['is_installed'])

        # Apply all filters
        filters = builder.build()
        if filters:
            query = query.filter(and_(*filters))

        # Apply sorting
        if sort_by:
            sort_field = getattr(Game, sort_by, None)
            if sort_field is not None:
                if sort_desc:
                    query = query.order_by(sort_field.desc())
                else:
                    query = query.order_by(sort_field.asc())

        # Apply pagination
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        return query.all()

    def count_filtered_games(self, filter_config: Dict[str, Any]) -> int:
        """
        Count games matching the filter criteria efficiently.

        Uses SQL COUNT instead of loading all results into memory.
        """
        query = self.session.query(Game)

        # Apply filters (same logic as filter_games, but without sorting/pagination)
        builder = FilterBuilder(self.session)

        # Name filter
        if 'name' in filter_config:
            builder.by_name(filter_config['name'])

        # Platform filter
        if 'platforms' in filter_config:
            builder.by_platform(filter_config['platforms'])

        # Genre filter
        if 'genres' in filter_config:
            builder.by_genre(filter_config['genres'])

        # Developer filter
        if 'developers' in filter_config:
            builder.by_developer(filter_config['developers'])

        # Publisher filter
        if 'publishers' in filter_config:
            builder.by_publisher(filter_config['publishers'])

        # Category filter
        if 'categories' in filter_config:
            builder.by_category(filter_config['categories'])

        # Tag filter
        if 'tags' in filter_config:
            builder.by_tag(filter_config['tags'])

        # Favorite filter
        if 'is_favorite' in filter_config:
            builder.by_favorite(filter_config['is_favorite'])

        # Hidden filter
        if 'is_hidden' in filter_config:
            builder.by_hidden(filter_config['is_hidden'])

        # Installed filter
        if 'is_installed' in filter_config:
            builder.by_installed(filter_config['is_installed'])

        # Playtime filters
        playtime_min = filter_config.get('playtime_min')
        playtime_max = filter_config.get('playtime_max')
        if playtime_min is not None or playtime_max is not None:
            builder.by_playtime(min_minutes=playtime_min, max_minutes=playtime_max)

        # Release year filters
        release_year_min = filter_config.get('release_year_min')
        release_year_max = filter_config.get('release_year_max')
        if release_year_min is not None or release_year_max is not None:
            builder.by_release_year(min_year=release_year_min, max_year=release_year_max)

        # Rating filters
        rating_min = filter_config.get('rating_min')
        rating_max = filter_config.get('rating_max')
        if rating_min is not None or rating_max is not None:
            builder.by_rating(min_rating=rating_min, max_rating=rating_max)

        # Completion status filter
        if 'completion_statuses' in filter_config:
            builder.by_completion_status(filter_config['completion_statuses'])

        # Apply all filters to query
        filters = builder.build()
        if filters:
            query = query.filter(and_(*filters))

        # Use SQL COUNT instead of loading results
        return query.count()
