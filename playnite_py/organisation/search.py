"""Game search with fuzzy matching and advanced search capabilities."""

from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_
from difflib import SequenceMatcher

from ..models import Game, Developer, Publisher, Tag


class GameSearch:
    """Search games with fuzzy matching support."""

    def __init__(self, session: Session):
        self.session = session

    def search(self, query: str, fuzzy: bool = True,
               search_fields: Optional[List[str]] = None,
               limit: int = 50,
               min_score: float = 0.6) -> List[Tuple[Game, float]]:
        """
        Search for games with optional fuzzy matching.

        Args:
            query: Search query string
            fuzzy: Enable fuzzy matching
            search_fields: Fields to search in (name, developer, publisher, tags)
            limit: Maximum number of results
            min_score: Minimum fuzzy match score (0-1) for fuzzy search

        Returns:
            List of (Game, score) tuples sorted by relevance
        """
        if not query:
            return []

        if search_fields is None:
            search_fields = ['name', 'developer', 'publisher', 'tags']

        results = []

        # Direct SQL search for fast initial filtering
        filters = []

        if 'name' in search_fields:
            filters.append(Game.name.ilike(f'%{query}%'))

        if 'developer' in search_fields:
            filters.append(Game.developers.any(Developer.name.ilike(f'%{query}%')))

        if 'publisher' in search_fields:
            filters.append(Game.publishers.any(Publisher.name.ilike(f'%{query}%')))

        if 'tags' in search_fields:
            filters.append(Game.tags.any(Tag.name.ilike(f'%{query}%')))

        if filters:
            games = self.session.query(Game).filter(or_(*filters)).limit(limit * 2).all()
        else:
            return []

        # Calculate fuzzy match scores
        for game in games:
            score = self._calculate_match_score(game, query, search_fields)
            if fuzzy:
                if score >= min_score:
                    results.append((game, score))
            else:
                # For non-fuzzy, just check if query is contained (case-insensitive)
                if self._exact_match(game, query, search_fields):
                    results.append((game, score))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)

        return results[:limit]

    def _calculate_match_score(self, game: Game, query: str,
                                search_fields: List[str]) -> float:
        """Calculate fuzzy match score for a game."""
        query_lower = query.lower()
        scores = []

        if 'name' in search_fields and game.name:
            name_score = SequenceMatcher(None, query_lower, game.name.lower()).ratio()
            scores.append(name_score * 2.0)  # Weight name matches higher

        if 'developer' in search_fields:
            for dev in game.developers:
                dev_score = SequenceMatcher(None, query_lower, dev.name.lower()).ratio()
                scores.append(dev_score)

        if 'publisher' in search_fields:
            for pub in game.publishers:
                pub_score = SequenceMatcher(None, query_lower, pub.name.lower()).ratio()
                scores.append(pub_score)

        if 'tags' in search_fields:
            for tag in game.tags:
                tag_score = SequenceMatcher(None, query_lower, tag.name.lower()).ratio()
                scores.append(tag_score)

        return max(scores) if scores else 0.0

    def _exact_match(self, game: Game, query: str, search_fields: List[str]) -> bool:
        """Check if game matches query exactly (case-insensitive substring)."""
        query_lower = query.lower()

        if 'name' in search_fields and game.name:
            if query_lower in game.name.lower():
                return True

        if 'developer' in search_fields:
            for dev in game.developers:
                if query_lower in dev.name.lower():
                    return True

        if 'publisher' in search_fields:
            for pub in game.publishers:
                if query_lower in pub.name.lower():
                    return True

        if 'tags' in search_fields:
            for tag in game.tags:
                if query_lower in tag.name.lower():
                    return True

        return False

    def search_by_title(self, title: str, fuzzy: bool = True, limit: int = 20) -> List[Tuple[Game, float]]:
        """Search games by title only."""
        return self.search(title, fuzzy=fuzzy, search_fields=['name'], limit=limit)

    def search_by_developer(self, developer: str, fuzzy: bool = True, limit: int = 50) -> List[Tuple[Game, float]]:
        """Search games by developer."""
        return self.search(developer, fuzzy=fuzzy, search_fields=['developer'], limit=limit)

    def search_by_tag(self, tag: str, fuzzy: bool = True, limit: int = 50) -> List[Tuple[Game, float]]:
        """Search games by tag."""
        return self.search(tag, fuzzy=fuzzy, search_fields=['tags'], limit=limit)
