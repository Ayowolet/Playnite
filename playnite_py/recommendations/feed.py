"""
Personalised game discovery feed.

Generates multiple themed "shelves" of recommendations so that a single
feed request surfaces games from several different perspectives at once.

Shelves
-------
1. **Top Picks**          — highest-scored recommendations for this user.
2. **Because You Played** — games similar to the most recently played game.
3. **From Your Backlog**  — owned, unplayed games sorted oldest-added first.
4. **Discover Something New** — highly-rated games outside the user's usual
                                taste (low content similarity, high community
                                score).
5. **Seasonal Picks**     — games whose genre / theme profile matches the
                            current season / time of day.

Usage
-----
    from playnite_py.recommendations.feed import DiscoveryFeed

    feed = DiscoveryFeed(engine, library)
    shelves = feed.generate(profile, n_per_shelf=5)
    for shelf in shelves:
        print(shelf.name)
        for rec in shelf.recommendations:
            print(" ", rec.game.name)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from ..library.manager import LibraryManager
from ..models.user_profile import UserProfile
from .engine import Recommendation, RecommendationEngine
from .temporal_filter import TemporalFilter


@dataclass
class FeedShelf:
    """A named, themed collection of recommendations."""
    name: str
    description: str
    tag: str                              # machine-readable identifier
    recommendations: List[Recommendation] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "tag": self.tag,
            "count": len(self.recommendations),
            "recommendations": [r.to_dict() for r in self.recommendations],
        }


class DiscoveryFeed:
    """
    Curated multi-shelf discovery feed.

    Parameters
    ----------
    engine:
        A fitted (or unfitted) :class:`RecommendationEngine`.  Will be
        fitted automatically on first call to :meth:`generate` if needed.
    library:
        The user's :class:`LibraryManager`.
    """

    def __init__(
        self,
        engine: RecommendationEngine,
        library: LibraryManager,
    ) -> None:
        self.engine = engine
        self.library = library

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def generate(
        self,
        profile: UserProfile,
        n_per_shelf: int = 5,
        mood: Optional[str] = None,
    ) -> List[FeedShelf]:
        """
        Generate a complete discovery feed for the user.

        Parameters
        ----------
        profile:
            The user to generate recommendations for.
        n_per_shelf:
            Maximum recommendations per shelf.
        mood:
            Optional mood override applied to the Top Picks shelf.

        Returns
        -------
        List of :class:`FeedShelf` objects, each with up to ``n_per_shelf``
        recommendations.  Shelves are omitted when they produce no results.
        """
        if not self.engine._fitted:
            self.engine.fit()

        shelves: List[FeedShelf] = []
        seen: Set[str] = set()  # game IDs already included in earlier shelves

        # ── Shelf 1: Top Picks ──────────────────────────────────────────
        top = self.engine.generate(
            profile, n=n_per_shelf, mood=mood, save_to_db=False
        )
        if top:
            seen.update(r.game.id for r in top)
            shelves.append(FeedShelf(
                name="Top Picks",
                description="Your highest-scoring unplayed games right now.",
                tag="top_picks",
                recommendations=top,
            ))

        # ── Shelf 2: Because You Played X ───────────────────────────────
        played = sorted(
            self.library.get_played_games(),
            key=lambda g: g.last_played or datetime.min,
            reverse=True,
        )
        if played:
            last = played[0]
            last_tokens = set(
                last.genres + last.themes + last.mechanics
            )
            # Fetch a wider pool then rank by attribute overlap
            pool = self.engine.generate(
                profile,
                n=n_per_shelf * 3,
                exclude_ids=list(seen),
                save_to_db=False,
            )
            pool.sort(
                key=lambda r: len(
                    last_tokens
                    & set(r.game.genres + r.game.themes + r.game.mechanics)
                ),
                reverse=True,
            )
            contextual = pool[:n_per_shelf]
            if contextual:
                seen.update(r.game.id for r in contextual)
                shelves.append(FeedShelf(
                    name=f"Because You Played {last.name}",
                    description=f"Games with similar genre or theme to {last.name}.",
                    tag="contextual",
                    recommendations=contextual,
                ))

        # ── Shelf 3: From Your Backlog ───────────────────────────────────
        all_games = self.library.get_all_games()
        backlog = [
            g for g in all_games
            if g.is_owned and not g.is_played and g.id not in seen
        ]
        backlog.sort(key=lambda g: g.added or datetime.min)
        backlog_games = backlog[:n_per_shelf]
        if backlog_games:
            seen.update(g.id for g in backlog_games)
            backlog_recs: List[Recommendation] = []
            for i, g in enumerate(backlog_games, 1):
                r = Recommendation(game=g, batch_id="feed_backlog", final_score=0.0)
                r.rank = i
                backlog_recs.append(r)
            shelves.append(FeedShelf(
                name="From Your Backlog",
                description="Your oldest unplayed owned games.",
                tag="backlog",
                recommendations=backlog_recs,
            ))

        # ── Shelf 4: Discover Something New ─────────────────────────────
        # High community score + low content similarity → outside usual taste
        discovery_pool = self.engine.generate(
            profile,
            n=n_per_shelf * 4,
            include_unowned=True,
            exclude_ids=list(seen),
            save_to_db=False,
        )
        # Rank: community score minus a penalty for high content similarity
        discovery_pool.sort(
            key=lambda r: (r.game.community_score or 0) - r.content_score * 50,
            reverse=True,
        )
        discovery = discovery_pool[:n_per_shelf]
        if discovery:
            seen.update(r.game.id for r in discovery)
            shelves.append(FeedShelf(
                name="Discover Something New",
                description="Highly-rated games outside your usual taste.",
                tag="discovery",
                recommendations=discovery,
            ))

        # ── Shelf 5: Seasonal Picks ──────────────────────────────────────
        tf = TemporalFilter()
        ctx = tf.get_context_summary()
        seasonal_pool = self.engine.generate(
            profile,
            n=n_per_shelf * 3,
            exclude_ids=list(seen),
            save_to_db=False,
        )
        # Sort by temporal signal so the most season-appropriate games bubble up
        seasonal_pool.sort(key=lambda r: r.temporal_score, reverse=True)
        seasonal = seasonal_pool[:n_per_shelf]
        if seasonal:
            season = ctx.get("season", "now").title()
            shelves.append(FeedShelf(
                name=f"Perfect for {season}",
                description=(
                    f"Games that feel right for "
                    f"{ctx.get('season', 'this time of year')} evenings."
                ),
                tag="seasonal",
                recommendations=seasonal,
            ))

        return shelves
