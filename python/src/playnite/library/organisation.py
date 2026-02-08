"""Main library organisation manager — the primary entry point for all library ops."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import create_engine, func, update, delete
from sqlalchemy.orm import Session, sessionmaker, joinedload

from ..database.models import (
    Base,
    Category,
    Game,
    Genre,
    Platform,
    SmartCollection,
    Tag,
    ViewPreset,
)
from .collections import CollectionEvaluator, validate_rules
from .filters import FilterEngine, FilterSpec
from .search import SearchEngine

logger = logging.getLogger(__name__)

# Fields that can be sorted at the SQL level
_SQL_SORT_FIELDS = {
    "name", "release_year", "playtime", "play_count", "added",
    "last_played", "user_score", "developer", "publisher",
    "completion_status", "is_favorite", "is_hidden", "is_installed",
    "sort_name",
}


class LibraryError(Exception):
    """Base error for library operations."""


class NotFoundError(LibraryError):
    """Raised when the requested entity does not exist."""


# ── Validation ────────────────────────────────────────────────────────────────

_VALID_COMPLETION_STATUSES = frozenset([
    "not_played", "playing", "completed", "dropped", "plan_to_play", "on_hold",
])

_GAME_SCALAR_FIELDS = frozenset({
    "name", "description", "release_year", "developer", "publisher",
    "playtime", "completion_status", "user_score", "is_favorite",
    "is_hidden", "is_installed", "notes", "cover_image", "sort_name",
    "play_count", "last_played",
})


def _validate_game_fields(fields: dict) -> None:
    """Raise ValueError for out-of-range or invalid game field values."""
    if "name" in fields:
        if not fields["name"] or len(fields["name"]) > 500:
            raise ValueError("name must be 1–500 characters")
    if "release_year" in fields and fields["release_year"] is not None:
        if not (1900 <= fields["release_year"] <= 2100):
            raise ValueError("release_year must be between 1900 and 2100")
    if "user_score" in fields and fields["user_score"] is not None:
        if not (0 <= fields["user_score"] <= 100):
            raise ValueError("user_score must be between 0 and 100")
    if "completion_status" in fields:
        if fields["completion_status"] not in _VALID_COMPLETION_STATUSES:
            raise ValueError(
                f"completion_status must be one of {sorted(_VALID_COMPLETION_STATUSES)}"
            )


def _eager():
    """Standard joinedload options for all four relationship collections."""
    return [
        joinedload(Game.tags),
        joinedload(Game.genres),
        joinedload(Game.platforms),
        joinedload(Game.categories),
    ]


# ── Mixins ────────────────────────────────────────────────────────────────────


class _TagCategoryMixin:
    """Tag and category management methods, extracted to keep LibraryManager focused."""

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def list_tags(self) -> List[dict]:
        with self._Session() as session:
            return [t.to_dict() for t in session.query(Tag).order_by(Tag.name).all()]

    def get_tag(self, tag_id: str) -> dict:
        with self._Session() as session:
            tag = session.get(Tag, tag_id)
            if tag is None:
                raise NotFoundError(f"Tag not found: {tag_id}")
            return tag.to_dict()

    def add_tag(self, name: str) -> dict:
        with self._Session() as session:
            tag = self._get_or_create(session, Tag, name=name)
            session.commit()
            session.refresh(tag)
            return tag.to_dict()

    def update_tag(self, tag_id: str, name: str) -> dict:
        with self._Session() as session:
            tag = session.get(Tag, tag_id)
            if tag is None:
                raise NotFoundError(f"Tag not found: {tag_id}")
            tag.name = name
            session.commit()
            session.refresh(tag)
            return tag.to_dict()

    def delete_tag(self, tag_id: str) -> None:
        with self._Session() as session:
            tag = session.get(Tag, tag_id)
            if tag is None:
                raise NotFoundError(f"Tag not found: {tag_id}")
            session.delete(tag)
            session.commit()

    def apply_tag(self, game_id: str, tag_name: str) -> dict:
        with self._Session() as session:
            game = (
                session.query(Game).options(*_eager()).filter(Game.id == game_id).first()
            )
            if game is None:
                raise NotFoundError(f"Game not found: {game_id}")
            tag = self._get_or_create(session, Tag, name=tag_name)
            if tag not in game.tags:
                game.tags.append(tag)
            game.modified = self._clock()
            session.commit()
            session.refresh(game)
            return game.to_dict()

    def remove_tag(self, game_id: str, tag_name: str) -> dict:
        with self._Session() as session:
            game = (
                session.query(Game).options(*_eager()).filter(Game.id == game_id).first()
            )
            if game is None:
                raise NotFoundError(f"Game not found: {game_id}")
            tag = session.query(Tag).filter(Tag.name == tag_name).first()
            if tag and tag in game.tags:
                game.tags.remove(tag)
            game.modified = self._clock()
            session.commit()
            session.refresh(game)
            return game.to_dict()

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    def list_categories(self) -> List[dict]:
        with self._Session() as session:
            return [c.to_dict() for c in session.query(Category).order_by(Category.name).all()]

    def get_category(self, category_id: str) -> dict:
        with self._Session() as session:
            cat = session.get(Category, category_id)
            if cat is None:
                raise NotFoundError(f"Category not found: {category_id}")
            return cat.to_dict()

    def add_category(self, name: str) -> dict:
        with self._Session() as session:
            cat = self._get_or_create(session, Category, name=name)
            session.commit()
            session.refresh(cat)
            return cat.to_dict()

    def update_category(self, category_id: str, name: str) -> dict:
        with self._Session() as session:
            cat = session.get(Category, category_id)
            if cat is None:
                raise NotFoundError(f"Category not found: {category_id}")
            cat.name = name
            session.commit()
            session.refresh(cat)
            return cat.to_dict()

    def delete_category(self, category_id: str) -> None:
        with self._Session() as session:
            cat = session.get(Category, category_id)
            if cat is None:
                raise NotFoundError(f"Category not found: {category_id}")
            session.delete(cat)
            session.commit()

    # ------------------------------------------------------------------
    # Bulk tag / category
    # ------------------------------------------------------------------

    def bulk_tag(self, game_ids: List[str], tag_name: str) -> List[dict]:
        """Apply *tag_name* to every game in *game_ids*."""
        with self._Session() as session:
            tag = self._get_or_create(session, Tag, name=tag_name)
            games = self._fetch_games(session, list(game_ids))
            for game in games:
                if tag not in game.tags:
                    game.tags.append(tag)
                game.modified = self._clock()
            session.commit()
            return [g.to_dict() for g in games]

    def bulk_categorize(self, game_ids: List[str], category_name: str) -> List[dict]:
        """Apply *category_name* to every game in *game_ids*."""
        with self._Session() as session:
            cat = self._get_or_create(session, Category, name=category_name)
            games = self._fetch_games(session, list(game_ids))
            for game in games:
                if cat not in game.categories:
                    game.categories.append(cat)
                game.modified = self._clock()
            session.commit()
            return [g.to_dict() for g in games]


class _PresetMixin:
    """View-preset management methods, extracted to keep LibraryManager focused."""

    def save_view_preset(
        self,
        name: str,
        sort_by: str = "name",
        sort_order: str = "asc",
        group_by: Optional[str] = None,
        view_type: str = "list",
        filters: Optional[dict] = None,
        columns: Optional[List[str]] = None,
    ) -> dict:
        """Save (or overwrite) a named view preset."""
        with self._Session() as session:
            preset = session.query(ViewPreset).filter_by(name=name).first()
            if preset is None:
                preset = ViewPreset(name=name)
                session.add(preset)
            preset.sort_by = sort_by
            preset.sort_order = sort_order
            preset.group_by = group_by
            preset.view_type = view_type
            preset.filters = filters or {}
            preset.columns = columns or []
            session.commit()
            session.refresh(preset)
            return preset.to_dict()

    def load_view_preset(self, name: str) -> dict:
        with self._Session() as session:
            preset = session.query(ViewPreset).filter_by(name=name).first()
            if preset is None:
                raise NotFoundError(f"View preset not found: {name}")
            return preset.to_dict()

    def list_games_with_preset(self, name: str) -> Any:
        """Load a named view preset and return games filtered/sorted/grouped by it."""
        preset = self.load_view_preset(name)
        filter_spec = FilterSpec.from_dict(preset.get("filters") or {})
        return self.list_games(
            sort_by=preset["sort_by"],
            sort_order=preset["sort_order"],
            group_by=preset.get("group_by"),
            filter_spec=filter_spec,
        )

    def delete_view_preset(self, name: str) -> None:
        with self._Session() as session:
            preset = session.query(ViewPreset).filter_by(name=name).first()
            if preset is None:
                raise NotFoundError(f"View preset not found: {name}")
            session.delete(preset)
            session.commit()

    def list_view_presets(self) -> List[dict]:
        with self._Session() as session:
            return [p.to_dict() for p in session.query(ViewPreset).order_by(ViewPreset.name).all()]


# ── Main manager ──────────────────────────────────────────────────────────────


class LibraryManager(_TagCategoryMixin, _PresetMixin):
    """
    Central manager for all game library operations.

    All methods return plain dicts (JSON-serialisable) so the CLI and any
    GUI layer can share the same backend without duplication.
    """

    COMPLETION_STATUSES = [
        "not_played",
        "playing",
        "completed",
        "dropped",
        "plan_to_play",
        "on_hold",
    ]

    def __init__(
        self,
        db_url: str = "sqlite:///:memory:",
        _clock: Optional[Callable] = None,
        _filter_engine: Optional[FilterEngine] = None,
        _search_engine: Optional[SearchEngine] = None,
        _col_evaluator: Optional[CollectionEvaluator] = None,
    ):
        self.engine = create_engine(db_url, echo=False, pool_pre_ping=True)
        Base.metadata.create_all(self.engine)
        self._Session = sessionmaker(bind=self.engine)
        self._filter_engine = _filter_engine or FilterEngine()
        self._search_engine = _search_engine or SearchEngine()
        self._col_evaluator = _col_evaluator or CollectionEvaluator()
        self._clock: Callable = _clock or datetime.now

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _session(self) -> Session:
        return self._Session()

    def _get_or_create(self, session: Session, model, **kwargs):
        instance = session.query(model).filter_by(**kwargs).first()
        if instance is None:
            instance = model(**kwargs)
            session.add(instance)
        return instance

    def _resolve_relationships(self, session: Session, game: Game, data: dict) -> None:
        """Attach platform/genre/tag/category relationships from lists of names."""
        mapping = {
            "platforms": Platform,
            "genres": Genre,
            "tags": Tag,
            "categories": Category,
        }
        with session.no_autoflush:
            for attr, model in mapping.items():
                if attr in data:
                    names = data.pop(attr) or []
                    # Batch pre-fetch existing entities in a single IN query
                    existing = {
                        e.name: e
                        for e in session.query(model).filter(model.name.in_(names)).all()
                    }
                    setattr(game, attr, [existing.get(n) or model(name=n) for n in names])

    def _fetch_games(self, session: Session, game_ids: List[str]) -> List[Game]:
        """Fetch games by IDs with all relationships eagerly loaded."""
        return (
            session.query(Game)
            .options(*_eager())
            .filter(Game.id.in_(game_ids))
            .all()
        )

    # ------------------------------------------------------------------
    # Game CRUD
    # ------------------------------------------------------------------

    def add_game(
        self,
        name: str,
        *,
        description: Optional[str] = None,
        release_year: Optional[int] = None,
        developer: Optional[str] = None,
        publisher: Optional[str] = None,
        playtime: int = 0,
        completion_status: str = "not_played",
        user_score: Optional[int] = None,
        is_favorite: bool = False,
        is_hidden: bool = False,
        is_installed: bool = False,
        notes: Optional[str] = None,
        cover_image: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        genres: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
    ) -> dict:
        """Add a new game and return its dict representation."""
        _validate_game_fields({
            "name": name,
            "release_year": release_year,
            "user_score": user_score,
            "completion_status": completion_status,
        })
        with self._Session() as session:
            game = Game(
                name=name,
                description=description,
                release_year=release_year,
                developer=developer,
                publisher=publisher,
                playtime=playtime,
                completion_status=completion_status,
                user_score=user_score,
                is_favorite=is_favorite,
                is_hidden=is_hidden,
                is_installed=is_installed,
                notes=notes,
                cover_image=cover_image,
            )
            rel_data = {
                "platforms": platforms,
                "genres": genres,
                "tags": tags,
                "categories": categories,
            }
            self._resolve_relationships(session, game, rel_data)
            session.add(game)
            session.commit()
            session.refresh(game)
            return game.to_dict()

    def get_game(self, game_id: str) -> dict:
        """Return a single game by id."""
        with self._Session() as session:
            game = (
                session.query(Game)
                .options(*_eager())
                .filter(Game.id == game_id)
                .first()
            )
            if game is None:
                raise NotFoundError(f"Game not found: {game_id}")
            return game.to_dict()

    def update_game(self, game_id: str, **kwargs) -> dict:
        """Update one or more fields on a game."""
        rel_fields = {"platforms", "genres", "tags", "categories"}
        with self._Session() as session:
            game = (
                session.query(Game)
                .options(*_eager())
                .filter(Game.id == game_id)
                .first()
            )
            if game is None:
                raise NotFoundError(f"Game not found: {game_id}")
            rel_data = {k: kwargs.pop(k) for k in list(kwargs) if k in rel_fields}
            _validate_game_fields(kwargs)
            for key, value in kwargs.items():
                if key not in _GAME_SCALAR_FIELDS:
                    raise ValueError(f"Unknown or non-updatable field: {key!r}")
                setattr(game, key, value)
            if rel_data:
                self._resolve_relationships(session, game, rel_data)
            game.modified = self._clock()
            session.commit()
            session.refresh(game)
            return game.to_dict()

    def delete_game(self, game_id: str) -> None:
        """Delete a game permanently."""
        with self._Session() as session:
            game = session.get(Game, game_id)
            if game is None:
                raise NotFoundError(f"Game not found: {game_id}")
            session.delete(game)
            session.commit()

    def list_games(
        self,
        sort_by: str = "name",
        sort_order: str = "asc",
        group_by: Optional[str] = None,
        include_hidden: bool = False,
        filter_spec: Optional[FilterSpec] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> Any:
        """
        List games with optional sorting, filtering, grouping, and pagination.

        Sorting on SQL-sortable fields uses ORDER BY; derived/relationship
        fields (tags, genres, platforms, categories) fall back to Python sort,
        which loads all matching games into memory before paginating.
        Returns a list of dicts normally, or a dict of {group: [dicts]} when
        *group_by* is set.
        """
        _ALL_SORT_FIELDS = _SQL_SORT_FIELDS | {"tags", "genres", "platforms", "categories"}
        if sort_by not in _ALL_SORT_FIELDS:
            raise ValueError(
                f"Invalid sort_by: {sort_by!r}. Valid fields: {sorted(_ALL_SORT_FIELDS)}"
            )

        with self._Session() as session:
            if filter_spec is not None:
                query = self._filter_engine.build_query(session, filter_spec, include_hidden=include_hidden)
            else:
                query = session.query(Game)
                if not include_hidden:
                    query = query.filter(Game.is_hidden == False)  # noqa: E712

            # Always eager-load relationships to avoid N+1 on to_dict()
            query = query.options(*_eager())

            # SQL-level sort when possible
            if sort_by in _SQL_SORT_FIELDS:
                col = getattr(Game, sort_by)
                query = query.order_by(col.desc() if sort_order == "desc" else col.asc())
                query = query.offset(offset)
                if limit is not None:
                    query = query.limit(limit)
                games = query.all()
            else:
                games = query.all()
                # Python-level fallback for relationship-derived fields
                def sort_key(g: Game):
                    val = getattr(g, sort_by, None)
                    if val is None:
                        return ("", 0)
                    if isinstance(val, str):
                        return (val.lower(), 0)
                    return ("", val)
                games.sort(key=sort_key, reverse=(sort_order == "desc"))
                games = games[offset: offset + limit] if limit is not None else games[offset:]

            dicts = [g.to_dict() for g in games]

            if group_by:
                return self._group_results(dicts, group_by)
            return dicts

    def _group_results(self, games: List[dict], group_by: str) -> Dict[str, List[dict]]:
        groups: Dict[str, List[dict]] = {}
        for game in games:
            key = game.get(group_by)
            if isinstance(key, list):
                for k in key:
                    groups.setdefault(str(k) if k else "Unknown", []).append(game)
            else:
                groups.setdefault(str(key) if key else "Unknown", []).append(game)
        return groups

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        fuzzy: bool = True,
        threshold: int = 60,
        include_hidden: bool = False,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[dict]:
        """Full-text / fuzzy search across name, developer, publisher, tags."""
        with self._Session() as session:
            q = session.query(Game).options(*_eager())
            if not include_hidden:
                q = q.filter(Game.is_hidden == False)  # noqa: E712
            games = q.all()
            results = self._search_engine.search(games, query, fuzzy=fuzzy, threshold=threshold)
            if limit is not None:
                results = results[offset: offset + limit]
            return [
                {"game": r.game.to_dict(), "score": r.score, "matched_field": r.matched_field}
                for r in results
            ]

    # ------------------------------------------------------------------
    # Genres & Platforms (read / auto-create via game operations)
    # ------------------------------------------------------------------

    def list_genres(self) -> List[dict]:
        with self._Session() as session:
            return [g.to_dict() for g in session.query(Genre).order_by(Genre.name).all()]

    def list_platforms(self) -> List[dict]:
        with self._Session() as session:
            return [p.to_dict() for p in session.query(Platform).order_by(Platform.name).all()]

    # ------------------------------------------------------------------
    # Smart Collections
    # ------------------------------------------------------------------

    def create_smart_collection(
        self,
        name: str,
        rules: List[dict],
        logic: str = "AND",
        description: Optional[str] = None,
    ) -> dict:
        validate_rules(rules)
        with self._Session() as session:
            col = SmartCollection(name=name, rules=rules, logic=logic, description=description)
            session.add(col)
            session.commit()
            session.refresh(col)
            return col.to_dict()

    def get_smart_collection(self, collection_id: str) -> dict:
        with self._Session() as session:
            col = session.get(SmartCollection, collection_id)
            if col is None:
                raise NotFoundError(f"Collection not found: {collection_id}")
            return col.to_dict()

    _SMART_COLLECTION_FIELDS = frozenset({"name", "rules", "logic", "description"})

    def update_smart_collection(self, collection_id: str, **kwargs) -> dict:
        if "rules" in kwargs:
            validate_rules(kwargs["rules"])
        for key in kwargs:
            if key not in self._SMART_COLLECTION_FIELDS:
                raise ValueError(f"Unknown or non-updatable field: {key!r}")
        with self._Session() as session:
            col = session.get(SmartCollection, collection_id)
            if col is None:
                raise NotFoundError(f"Collection not found: {collection_id}")
            for key, value in kwargs.items():
                setattr(col, key, value)
            session.commit()
            session.refresh(col)
            return col.to_dict()

    def delete_smart_collection(self, collection_id: str) -> None:
        with self._Session() as session:
            col = session.get(SmartCollection, collection_id)
            if col is None:
                raise NotFoundError(f"Collection not found: {collection_id}")
            session.delete(col)
            session.commit()

    def list_smart_collections(self) -> List[dict]:
        with self._Session() as session:
            return [c.to_dict() for c in session.query(SmartCollection).order_by(SmartCollection.name).all()]

    def get_smart_collection_games(self, collection_id: str) -> List[dict]:
        """Evaluate collection rules dynamically and return matching games."""
        with self._Session() as session:
            col = session.get(SmartCollection, collection_id)
            if col is None:
                raise NotFoundError(f"Collection not found: {collection_id}")
            all_games = (
                session.query(Game)
                .options(*_eager())
                .filter(Game.is_hidden == False)  # noqa: E712
                .all()
            )
            matching = self._col_evaluator.get_matching_games(all_games, col)
            return [g.to_dict() for g in matching]

    # ------------------------------------------------------------------
    # Favourites / Pinning
    # ------------------------------------------------------------------

    def pin_game(self, game_id: str) -> dict:
        return self.update_game(game_id, is_favorite=True)

    def unpin_game(self, game_id: str) -> dict:
        return self.update_game(game_id, is_favorite=False)

    def get_favourites(self) -> List[dict]:
        with self._Session() as session:
            games = (
                session.query(Game)
                .options(*_eager())
                .filter(Game.is_favorite == True, Game.is_hidden == False)  # noqa: E712
                .all()
            )
            return [g.to_dict() for g in games]

    # ------------------------------------------------------------------
    # Hiding
    # ------------------------------------------------------------------

    def hide_game(self, game_id: str) -> dict:
        return self.update_game(game_id, is_hidden=True)

    def unhide_game(self, game_id: str) -> dict:
        return self.update_game(game_id, is_hidden=False)

    # ------------------------------------------------------------------
    # Bulk Operations
    # ------------------------------------------------------------------

    def bulk_update(self, game_ids: List[str], **kwargs) -> List[dict]:
        """Update scalar fields on multiple games at once using a single SQL UPDATE."""
        if not game_ids or not kwargs:
            return []
        for key in kwargs:
            if key not in _GAME_SCALAR_FIELDS:
                raise ValueError(f"Unknown or non-updatable field: {key!r}")
        _validate_game_fields(kwargs)
        with self._Session() as session:
            kwargs["modified"] = self._clock()
            session.execute(
                update(Game).where(Game.id.in_(list(game_ids))).values(**kwargs)
            )
            session.commit()
            games = self._fetch_games(session, list(game_ids))
            return [g.to_dict() for g in games]

    def bulk_delete(self, game_ids: List[str]) -> int:
        """Delete multiple games. Returns the count actually deleted."""
        if not game_ids:
            return 0
        with self._Session() as session:
            result = session.execute(
                delete(Game).where(Game.id.in_(list(game_ids)))
            )
            session.commit()
            return result.rowcount

    def bulk_hide(self, game_ids: List[str]) -> List[dict]:
        return self.bulk_update(game_ids, is_hidden=True)

    def bulk_unhide(self, game_ids: List[str]) -> List[dict]:
        return self.bulk_update(game_ids, is_hidden=False)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        with self._Session() as session:
            from sqlalchemy import case, select
            row = session.execute(select(
                func.count(Game.id).label("total"),
                func.sum(case((Game.is_installed.is_(True), 1), else_=0)).label("installed"),
                func.sum(case((Game.is_favorite.is_(True), 1), else_=0)).label("favorites"),
                func.sum(case((Game.is_hidden.is_(True), 1), else_=0)).label("hidden"),
                func.coalesce(func.sum(Game.playtime), 0).label("playtime"),
            )).first()
            total_playtime = row.playtime or 0
            return {
                "total_games": row.total,
                "installed_games": row.installed,
                "favourite_games": row.favorites,
                "hidden_games": row.hidden,
                "total_playtime_seconds": total_playtime,
                "total_playtime_hours": round(total_playtime / 3600, 1),
            }
