"""
JSON-based persistence layer.

Supports two layout modes:
- **Playnite layout** (``playnite=True``): reads a real Playnite library
  directory with per-entity sub-folders (``games/``, ``platforms/``, …).
- **Flat layout** (``playnite=False``): writes/reads a single
  ``library.json`` file with all data embedded.

Either way the round-trip ``save → load`` is lossless for our models.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from ..models.game import Game
from ..models.library import Library, LibrarySource, NamedEntity

logger = logging.getLogger(__name__)

# Increment this whenever a breaking change is made to the flat JSON layout.
# Add a migration step in :func:`_migrate` before bumping.
SCHEMA_VERSION = 1


def _migrate(data: dict[str, Any], from_version: int) -> dict[str, Any]:
    """Apply forward migrations from *from_version* to :data:`SCHEMA_VERSION`.

    To add a new migration: increment ``SCHEMA_VERSION``, add an ``elif``
    block here for the previous version, and update this docstring.
    """
    if from_version == SCHEMA_VERSION:
        return data
    if from_version > SCHEMA_VERSION:
        logger.warning(
            "Library file was written with schema version %d; this version "
            "of game-library-manager only supports up to v%d. "
            "Some data may be ignored.",
            from_version,
            SCHEMA_VERSION,
        )
        return data
    # from_version == 0 (unversioned): no structural changes required.
    # v0 → v1 only adds the schema_version field, which is written on save.
    logger.debug(
        "Loading pre-versioned library file; treating as schema v0 → v%d.",
        SCHEMA_VERSION,
    )
    return data


def _load_entities(directory: Path) -> dict[str, NamedEntity]:
    """Load all ``*.json`` files in *directory* as :class:`NamedEntity` objects."""
    entities: dict[str, NamedEntity] = {}
    if not directory.is_dir():
        return entities
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entity = NamedEntity.from_dict(data)
            entities[entity.Id] = entity
        except Exception as exc:
            logger.warning("Skipping corrupt entity file '%s': %s", path, exc)
    return entities


class JsonStore:
    """
    Reads and writes :class:`~game_library.models.Library` objects to disk.
    """

    def __init__(self, path: str | Path, playnite: bool = False):
        self.path = Path(path)
        self.playnite = playnite

    # ── Loading ──────────────────────────────────────────────────────────────

    def load(self, source_name: str = "default", source_priority: int = 99) -> Library:
        """
        Load a library from disk.

        For Playnite layout, *path* must point to the root database directory.
        For flat layout, *path* must point to the ``library.json`` file.
        """
        if self.playnite:
            return self._load_playnite(source_name, source_priority)
        return self._load_flat(source_name, source_priority)

    def _load_playnite(self, source_name: str, source_priority: int) -> Library:
        root = self.path
        lib = Library(source=LibrarySource(name=source_name, path=str(root), priority=source_priority))

        lib.platforms = _load_entities(root / "platforms")
        lib.companies = _load_entities(root / "companies")
        lib.genres = _load_entities(root / "genres")
        lib.categories = _load_entities(root / "categories")
        lib.tags = _load_entities(root / "tags")
        lib.series = _load_entities(root / "series")
        lib.sources = _load_entities(root / "sources")
        lib.age_ratings = _load_entities(root / "ageratings")
        lib.regions = _load_entities(root / "regions")
        lib.completion_statuses = _load_entities(root / "completionstatuses")

        games_dir = root / "games"
        if games_dir.is_dir():
            for path in games_dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    game = Game.from_dict(data)
                    lib.add_game(game)
                except Exception as exc:
                    logger.warning("Skipping corrupt game file '%s': %s", path, exc)

        lib.resolve_all()
        return lib

    def _load_flat(self, source_name: str, source_priority: int) -> Library:
        if not self.path.exists():
            return Library(source=LibrarySource(name=source_name, path=str(self.path), priority=source_priority))

        try:
            raw = self.path.read_text(encoding="utf-8")
        except PermissionError as exc:
            raise PermissionError(
                f"Cannot read library file '{self.path}'. "
                "The file may be open in another application (e.g. Playnite). "
                "Close it and retry."
            ) from exc
        data: dict[str, Any] = json.loads(raw)
        data = _migrate(data, data.get("schema_version", 0))
        src_data = data.get("source", {})
        lib = Library(
            source=LibrarySource(
                name=src_data.get("name", source_name),
                path=src_data.get("path", str(self.path)),
                priority=src_data.get("priority", source_priority),
            )
        )

        def _load_table(raw: list[dict]) -> dict[str, NamedEntity]:
            return {e.Id: e for e in (NamedEntity.from_dict(r) for r in raw)}

        lib.platforms = _load_table(data.get("platforms", []))
        lib.companies = _load_table(data.get("companies", []))
        lib.genres = _load_table(data.get("genres", []))
        lib.categories = _load_table(data.get("categories", []))
        lib.tags = _load_table(data.get("tags", []))
        lib.series = _load_table(data.get("series", []))
        lib.sources = _load_table(data.get("sources", []))
        lib.age_ratings = _load_table(data.get("age_ratings", []))
        lib.regions = _load_table(data.get("regions", []))
        lib.completion_statuses = _load_table(data.get("completion_statuses", []))

        for raw_game in data.get("games", []):
            game = Game.from_dict(raw_game)
            lib.add_game(game)

        lib.resolve_all()
        return lib

    # ── Saving ───────────────────────────────────────────────────────────────

    def save(self, library: Library) -> None:
        """Save *library* to disk using the configured layout."""
        if self.playnite:
            self._save_playnite(library)
        else:
            self._save_flat(library)

    def _save_playnite(self, library: Library) -> None:
        root = self.path
        root.mkdir(parents=True, exist_ok=True)

        def _write_entities(sub: str, table: dict[str, NamedEntity]) -> None:
            d = root / sub
            d.mkdir(exist_ok=True)
            for entity in table.values():
                (d / f"{entity.Id}.json").write_text(
                    json.dumps(entity.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
                )

        _write_entities("platforms", library.platforms)
        _write_entities("companies", library.companies)
        _write_entities("genres", library.genres)
        _write_entities("categories", library.categories)
        _write_entities("tags", library.tags)
        _write_entities("series", library.series)
        _write_entities("sources", library.sources)
        _write_entities("ageratings", library.age_ratings)
        _write_entities("regions", library.regions)
        _write_entities("completionstatuses", library.completion_statuses)

        games_dir = root / "games"
        games_dir.mkdir(exist_ok=True)
        for game in library.games.values():
            (games_dir / f"{game.Id}.json").write_text(
                json.dumps(game.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )

    def _save_flat(self, library: Library) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        def _serial(table: dict[str, NamedEntity]) -> list[dict]:
            return [e.to_dict() for e in table.values()]

        data: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "source": {
                "name": library.source.name,
                "path": library.source.path,
                "priority": library.source.priority,
            },
            "games": [g.to_dict() for g in library.games.values()],
            "platforms": _serial(library.platforms),
            "companies": _serial(library.companies),
            "genres": _serial(library.genres),
            "categories": _serial(library.categories),
            "tags": _serial(library.tags),
            "series": _serial(library.series),
            "sources": _serial(library.sources),
            "age_ratings": _serial(library.age_ratings),
            "regions": _serial(library.regions),
            "completion_statuses": _serial(library.completion_statuses),
        }
        json_text = json.dumps(data, ensure_ascii=False, indent=2)
        # Atomic write: serialise to a sibling .tmp file, then rename over the
        # target.  os.replace() is atomic on POSIX and on Windows (when the
        # target is not open); it guarantees the original is never partially
        # overwritten.  On Windows, if the target file is held open by another
        # application (e.g. Playnite), os.replace() raises PermissionError and
        # the original is left untouched.
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json_text, encoding="utf-8")
            os.replace(tmp, self.path)
        except PermissionError as exc:
            tmp.unlink(missing_ok=True)
            raise PermissionError(
                f"Cannot write to library file '{self.path}'. "
                "The file may be open in another application (e.g. Playnite). "
                "Close it and retry."
            ) from exc
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
