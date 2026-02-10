"""
Game library manager — CRUD operations, import/export, and stats.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import AppConfig
from ..database.db import GameDatabase
from ..models.game import Game
from ..models.user_profile import UserProfile


class LibraryManager:
    """
    High-level interface for managing a user's game library.

    Wraps ``GameDatabase`` with convenience methods for searching,
    bulk-importing from JSON, exporting, and computing statistics.
    """

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self.config = config or AppConfig()
        self.config.ensure_dirs()
        self.db = GameDatabase(self.config.database_path)

    # ------------------------------------------------------------------ #
    # Game CRUD                                                            #
    # ------------------------------------------------------------------ #

    def add_game(self, game: Game) -> Game:
        """Add or update a game in the library."""
        game.modified = datetime.utcnow()
        if not game.added:
            game.added = datetime.utcnow()
        self.db.upsert_game(game)
        return game

    def get_game(self, game_id: str) -> Optional[Game]:
        return self.db.get_game(game_id)

    def update_game(self, game: Game) -> Game:
        game.modified = datetime.utcnow()
        self.db.upsert_game(game)
        return game

    def remove_game(self, game_id: str) -> bool:
        return self.db.delete_game(game_id)

    def get_all_games(self, include_hidden: bool = False) -> List[Game]:
        return self.db.list_games(hidden=include_hidden)

    def get_unplayed_games(self) -> List[Game]:
        return self.db.list_games(unplayed_only=True)

    def get_played_games(self) -> List[Game]:
        return self.db.list_games(played_only=True)

    def get_wishlist(self) -> List[Game]:
        return self.db.list_games(in_wishlist=True)

    # ------------------------------------------------------------------ #
    # Search & filter                                                      #
    # ------------------------------------------------------------------ #

    def search(self, query: str) -> List[Game]:
        """Simple case-insensitive substring search on name."""
        q = query.lower()
        return [g for g in self.get_all_games() if q in g.name.lower()]

    def filter_games(
        self,
        *,
        genre: Optional[str] = None,
        platform: Optional[str] = None,
        developer: Optional[str] = None,
        source: Optional[str] = None,
        tag: Optional[str] = None,
        min_playtime_hours: Optional[float] = None,
        max_playtime_hours: Optional[float] = None,
        installed_only: bool = False,
        favorites_only: bool = False,
        release_year: Optional[int] = None,
    ) -> List[Game]:
        games = self.get_all_games()

        if genre:
            gl = genre.lower()
            games = [g for g in games if any(gl == gn.lower() for gn in g.genres)]
        if platform:
            pl = platform.lower()
            games = [g for g in games if any(pl == p.lower() for p in g.platforms)]
        if developer:
            dl = developer.lower()
            games = [g for g in games if any(dl == d.lower() for d in g.developers)]
        if source:
            games = [g for g in games if (g.source or "").lower() == source.lower()]
        if tag:
            tl = tag.lower()
            games = [g for g in games if any(tl == t.lower() for t in g.tags)]
        if min_playtime_hours is not None:
            games = [g for g in games if g.playtime_hours >= min_playtime_hours]
        if max_playtime_hours is not None:
            games = [g for g in games if g.playtime_hours <= max_playtime_hours]
        if installed_only:
            games = [g for g in games if g.is_installed]
        if favorites_only:
            games = [g for g in games if g.favorite]
        if release_year is not None:
            games = [g for g in games if g.release_year == release_year]

        return games

    # ------------------------------------------------------------------ #
    # Play tracking                                                        #
    # ------------------------------------------------------------------ #

    def record_play_start(self, game_id: str, user_id: str) -> Optional[str]:
        """Start a play session and return session ID."""
        from ..models.user_profile import PlaySession

        game = self.db.get_game(game_id)
        if not game:
            return None

        session = PlaySession(
            id=str(uuid.uuid4()),
            game_id=game_id,
            user_id=user_id,
        )
        self.db.save_play_session(session)
        return session.id

    def record_play_end(self, session_id: str, game_id: str, user_id: str) -> Optional[int]:
        """
        Finish a play session, update game statistics, return duration seconds.
        """
        sessions = self.db.get_play_sessions(game_id=game_id, user_id=user_id)
        session = next((s for s in sessions if s.id == session_id), None)
        if not session:
            return None

        session.finish()
        self.db.save_play_session(session)

        game = self.db.get_game(game_id)
        if game:
            game.play_count += 1
            game.playtime_seconds += session.duration_seconds
            game.last_played = session.end_time
            game.modified = datetime.utcnow()
            self.db.upsert_game(game)

        return session.duration_seconds

    # ------------------------------------------------------------------ #
    # Import / Export                                                      #
    # ------------------------------------------------------------------ #

    def import_from_json(self, path: Path, merge: bool = True) -> int:
        """
        Import games from a JSON file.
        Expects either a single game dict or a list of game dicts.
        Returns the number of games imported.
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            # Handle library fixture format: {"games": [...], "user": {...}}
            if "games" in data:
                games_data = data["games"]
            else:
                games_data = [data]
        else:
            games_data = data

        count = 0
        for gd in games_data:
            if not merge and self.db.get_game(gd.get("id", "")):
                continue
            game = Game.from_dict(gd)
            if not game.id:
                game.id = str(uuid.uuid4())
            self.db.upsert_game(game)
            count += 1
        return count

    def export_to_json(self, path: Path) -> int:
        """Export all games to a JSON file. Returns number of games exported."""
        games = self.get_all_games(include_hidden=True)
        data = [g.to_dict() for g in games]
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return len(data)

    # ------------------------------------------------------------------ #
    # User profiles                                                        #
    # ------------------------------------------------------------------ #

    def get_or_create_profile(self, user_id: Optional[str] = None) -> UserProfile:
        """Return an existing profile or create a default one."""
        if user_id:
            profile = self.db.get_user_profile(user_id)
            if profile:
                return profile
        else:
            profile = self.db.get_default_profile()
            if profile:
                return profile

        # Create default
        profile = UserProfile(
            id=user_id or str(uuid.uuid4()),
            username="Player",
        )
        self.db.upsert_user_profile(profile)
        return profile

    def save_profile(self, profile: UserProfile) -> UserProfile:
        profile.updated_at = datetime.utcnow()
        self.db.upsert_user_profile(profile)
        return profile

    # ------------------------------------------------------------------ #
    # Statistics                                                           #
    # ------------------------------------------------------------------ #

    def get_stats(self) -> Dict[str, Any]:
        """Return library summary statistics."""
        stats = self.db.get_library_stats()
        games = self.get_all_games()

        # Genre breakdown
        genre_counts: Dict[str, int] = {}
        platform_counts: Dict[str, int] = {}
        source_counts: Dict[str, int] = {}

        for g in games:
            for genre in g.genres:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1
            for platform in g.platforms:
                platform_counts[platform] = platform_counts.get(platform, 0) + 1
            if g.source:
                source_counts[g.source] = source_counts.get(g.source, 0) + 1

        stats["top_genres"] = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        stats["top_platforms"] = sorted(platform_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        stats["sources"] = source_counts

        # Most played
        played = sorted(games, key=lambda g: g.playtime_seconds, reverse=True)
        stats["most_played"] = [
            {"name": g.name, "playtime_hours": round(g.playtime_hours, 1)} for g in played[:5]
        ]

        return stats

    def build_user_preference_weights(self, profile: UserProfile) -> UserProfile:
        """
        Analyse play history and update preference weights on the profile.
        Called automatically when the recommendation engine runs.
        """
        played_games = self.get_played_games()
        if not played_games:
            return profile

        genre_scores: Dict[str, float] = {}
        mechanic_scores: Dict[str, float] = {}
        theme_scores: Dict[str, float] = {}
        developer_scores: Dict[str, float] = {}
        tag_scores: Dict[str, float] = {}

        total_playtime = sum(g.playtime_seconds for g in played_games) or 1

        for game in played_games:
            # Weight by normalised playtime + explicit rating bonus
            pt_weight = game.playtime_seconds / total_playtime
            rating = profile.ratings.get(game.id)
            if rating is not None:
                # Scale 0-10 rating to 0-1 multiplier (5 = neutral)
                rating_factor = rating / 10.0
            else:
                rating_factor = 0.5  # neutral default

            weight = (pt_weight * 0.7) + (rating_factor * 0.3)

            for g in game.genres:
                genre_scores[g] = genre_scores.get(g, 0.0) + weight
            for m in game.mechanics:
                mechanic_scores[m] = mechanic_scores.get(m, 0.0) + weight
            for t in game.themes:
                theme_scores[t] = theme_scores.get(t, 0.0) + weight
            for d in game.developers:
                developer_scores[d] = developer_scores.get(d, 0.0) + weight
            for tg in game.tags:
                tag_scores[tg] = tag_scores.get(tg, 0.0) + weight

        def _normalise(d: Dict[str, float]) -> Dict[str, float]:
            mx = max(d.values(), default=1.0)
            return {k: v / mx for k, v in d.items()} if mx > 0 else d

        profile.genre_weights = _normalise(genre_scores)
        profile.mechanic_weights = _normalise(mechanic_scores)
        profile.theme_weights = _normalise(theme_scores)
        profile.developer_weights = _normalise(developer_scores)
        profile.tag_weights = _normalise(tag_scores)

        return profile
