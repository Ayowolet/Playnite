"""
Library Merger: the high-level orchestrator for safe library merging.

Workflow
--------
1. User calls ``merger.preview(master, source)`` to see what would change.
2. User reviews the :class:`MergePreview` and adjusts :class:`MergeConfig`.
3. User calls ``merger.execute(master, source)`` which:
   a. Creates a backup of the master library.
   b. Matches each source game to an existing master game (or marks as new).
   c. Applies :class:`ConflictResolver` for each matched pair.
   d. Adds genuinely new games from the source.
   e. Copies referenced entities (platforms, companies, …) that don't exist.
   f. Validates the merged library.
   g. Returns a :class:`MergeResult`.
4. If anything goes wrong, ``merger.rollback(result)`` restores the backup.
"""
from __future__ import annotations

import copy
import datetime
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..models.game import Game
from ..models.library import Library, NamedEntity
from ..duplicate.matcher import GameMatcher, MatchWeights
from ..utils.text_utils import nfc_lower
from .strategies import MergeStrategy
from .conflict import ConflictResolver, Conflict
from .backup import BackupManager, BackupRecord


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class MergeConfig:
    """All tunable parameters for a merge operation."""

    strategy: MergeStrategy = MergeStrategy.MERGE_PREFER_MASTER

    # Minimum similarity score to consider two games the same (0.0-1.0)
    match_threshold: float = 0.85

    # Custom match weights
    match_weights: Optional[MatchWeights] = None

    # Selective merge: if non-empty, only these game IDs from source are merged
    include_game_ids: list[str] = field(default_factory=list)

    # Source games matching these filters are skipped
    exclude_platforms: list[str] = field(default_factory=list)
    exclude_sources: list[str] = field(default_factory=list)
    exclude_hidden: bool = False

    # Media file handling
    copy_cover_images: bool = True
    copy_background_images: bool = True
    copy_icons: bool = True

    # Incremental merge: only process source games modified after this datetime
    incremental_since: Optional[str] = None   # ISO-8601

    # Back-up directory (auto-created if not set)
    backup_dir: Optional[str] = None

    # Custom field strategy overrides
    field_strategy_overrides: dict[str, str] = field(default_factory=dict)

    # Per-field strategy overrides as MergeStrategy objects (populated on use)
    def get_field_overrides(self) -> dict[str, MergeStrategy]:
        """Convert the raw string overrides map to typed :class:`MergeStrategy` values."""
        return {
            fname: MergeStrategy(sval)
            for fname, sval in self.field_strategy_overrides.items()
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "match_threshold": self.match_threshold,
            "include_game_ids": self.include_game_ids,
            "exclude_platforms": self.exclude_platforms,
            "exclude_sources": self.exclude_sources,
            "exclude_hidden": self.exclude_hidden,
            "copy_cover_images": self.copy_cover_images,
            "copy_background_images": self.copy_background_images,
            "copy_icons": self.copy_icons,
            "incremental_since": self.incremental_since,
            "backup_dir": self.backup_dir,
            "field_strategy_overrides": self.field_strategy_overrides,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MergeConfig":
        cfg = cls()
        cfg.strategy = MergeStrategy(data.get("strategy", MergeStrategy.MERGE_PREFER_MASTER.value))
        cfg.match_threshold = data.get("match_threshold", 0.85)
        cfg.include_game_ids = data.get("include_game_ids", [])
        cfg.exclude_platforms = data.get("exclude_platforms", [])
        cfg.exclude_sources = data.get("exclude_sources", [])
        cfg.exclude_hidden = data.get("exclude_hidden", False)
        cfg.copy_cover_images = data.get("copy_cover_images", True)
        cfg.copy_background_images = data.get("copy_background_images", True)
        cfg.copy_icons = data.get("copy_icons", True)
        cfg.incremental_since = data.get("incremental_since")
        cfg.backup_dir = data.get("backup_dir")
        cfg.field_strategy_overrides = data.get("field_strategy_overrides", {})
        return cfg


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class GameMergePlan:
    """Merge plan for a single source game."""

    source_game: Game
    matched_master_game: Optional[Game]   # None → new game
    is_new: bool
    conflicts: list[Conflict] = field(default_factory=list)
    merged_game: Optional[Game] = None    # populated after execution

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_game.Id,
            "source_name": self.source_game.Name,
            "master_id": self.matched_master_game.Id if self.matched_master_game else None,
            "is_new": self.is_new,
            "conflict_count": len(self.conflicts),
            "conflicts": [c.to_dict() for c in self.conflicts],
        }


@dataclass
class MergePreview:
    """Dry-run result showing what a merge would change."""

    config: MergeConfig
    plans: list[GameMergePlan]

    @property
    def new_games(self) -> list[GameMergePlan]:
        return [p for p in self.plans if p.is_new]

    @property
    def updated_games(self) -> list[GameMergePlan]:
        return [p for p in self.plans if not p.is_new]

    @property
    def games_with_conflicts(self) -> list[GameMergePlan]:
        return [p for p in self.plans if p.conflicts]

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "total_source_games": len(self.plans),
            "new_games": len(self.new_games),
            "updated_games": len(self.updated_games),
            "games_with_conflicts": len(self.games_with_conflicts),
            "plans": [p.to_dict() for p in self.plans],
        }


@dataclass
class MergeResult:
    """Result of a completed merge operation."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    executed_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    config: Optional[MergeConfig] = None
    backup_record: Optional[BackupRecord] = None
    preview: Optional[MergePreview] = None

    games_added: int = 0
    games_updated: int = 0
    games_skipped: int = 0
    conflicts_resolved: int = 0
    errors: list[str] = field(default_factory=list)
    success: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "executed_at": self.executed_at,
            "config": self.config.to_dict() if self.config else None,
            "backup_id": self.backup_record.id if self.backup_record else None,
            "games_added": self.games_added,
            "games_updated": self.games_updated,
            "games_skipped": self.games_skipped,
            "conflicts_resolved": self.conflicts_resolved,
            "errors": self.errors,
            "success": self.success,
        }


# ── Merger ────────────────────────────────────────────────────────────────────

class LibraryMerger:
    """
    Safely merges a *source* :class:`~game_library.models.Library` into a
    *master* :class:`~game_library.models.Library`.

    Parameters
    ----------
    config:
        Merge configuration.  A default :class:`MergeConfig` is used when not
        supplied.
    backup_dir:
        Directory where backups are stored.  Defaults to ``./backups`` relative
        to the working directory.
    """

    def __init__(
        self,
        config: Optional[MergeConfig] = None,
        backup_dir: Optional[str | Path] = None,
    ) -> None:
        self.config = config or MergeConfig()
        _bdir = backup_dir or self.config.backup_dir or "./backups"
        self.backup_manager = BackupManager(_bdir)
        self._matcher = GameMatcher(weights=self.config.match_weights)

    # ── Public API ────────────────────────────────────────────────────────────

    def preview(self, master: Library, source: Library) -> MergePreview:
        """
        Dry-run: compute the merge plan without modifying any library.
        """
        master.resolve_all()
        source.resolve_all()
        source_games = self._filter_source_games(source.all_games())
        resolver = ConflictResolver(self.config.strategy)
        resolver.field_overrides = self.config.get_field_overrides()
        plans: list[GameMergePlan] = []
        for sg in source_games:
            match = self._find_match(sg, master)
            if match is None:
                plans.append(GameMergePlan(source_game=sg, matched_master_game=None, is_new=True))
            else:
                conflicts = resolver.detect_conflicts(match, sg)
                plans.append(GameMergePlan(
                    source_game=sg,
                    matched_master_game=match,
                    is_new=False,
                    conflicts=conflicts,
                ))
        return MergePreview(config=self.config, plans=plans)

    def execute(self, master: Library, source: Library) -> MergeResult:
        """
        Execute the merge.

        Creates a backup, applies the merge, validates, and returns a
        :class:`MergeResult`.  On critical error the backup is available for
        rollback via :meth:`rollback`.
        """
        master.resolve_all()
        source.resolve_all()

        # 1. Backup
        backup_data = self._serialise_library(master)
        backup_record = self.backup_manager.create(
            backup_data,
            description=f"Pre-merge backup of '{master.source.name}'",
        )

        result = MergeResult(config=self.config, backup_record=backup_record)

        try:
            preview = self.preview(master, source)
            result.preview = preview
            resolver = ConflictResolver(self.config.strategy)
            resolver.field_overrides = self.config.get_field_overrides()

            for plan in preview.plans:
                sg = plan.source_game
                try:
                    if plan.is_new:
                        new_game = self._import_game(sg, source, master)
                        master.add_game(new_game)
                        result.games_added += 1
                    else:
                        mg = plan.matched_master_game
                        merged_game, conflicts = resolver.resolve(mg, sg)
                        plan.merged_game = merged_game
                        master.games[merged_game.Id] = merged_game
                        result.games_updated += 1
                        result.conflicts_resolved += len(conflicts)
                except Exception as exc:
                    result.errors.append(f"Error processing '{sg.Name}': {exc}")

            # 2. Merge reference entities
            self._merge_entities(master, source)

            # 3. Validate
            issues = self._validate(master)
            if issues:
                result.errors.extend(issues)
                if any("critical" in i.lower() for i in issues):
                    result.success = False

        except Exception as exc:
            result.success = False
            result.errors.append(f"Fatal merge error: {exc}")

        return result

    def rollback(self, result: MergeResult, master: Library) -> Library:
        """
        Restore the master library to its pre-merge state from the backup.

        Returns the restored library (caller must replace their reference).
        """
        if result.backup_record is None:
            raise ValueError("No backup record in MergeResult – cannot rollback")

        backup_data = self.backup_manager.restore(result.backup_record.id)
        # Deserialise back into a Library
        from ..storage.json_store import JsonStore as JS
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(backup_data, f)
            tmp_path = f.name
        try:
            restored = JS(tmp_path).load(
                source_name=master.source.name,
                source_priority=master.source.priority,
            )
        finally:
            os.unlink(tmp_path)
        # Replace master contents in-place so callers' references stay valid
        master.games = restored.games
        master.platforms = restored.platforms
        master.companies = restored.companies
        master.genres = restored.genres
        master.categories = restored.categories
        master.tags = restored.tags
        master.series = restored.series
        master.sources = restored.sources
        master.age_ratings = restored.age_ratings
        master.regions = restored.regions
        master.completion_statuses = restored.completion_statuses
        return master

    def export_config(self, path: str | Path) -> None:
        """Export the current :class:`MergeConfig` to a JSON file for reuse."""
        Path(path).write_text(
            json.dumps(self.config.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load_config(cls, path: str | Path, backup_dir: Optional[str | Path] = None) -> "LibraryMerger":
        """Load a previously exported :class:`MergeConfig` and return a new merger."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        cfg = MergeConfig.from_dict(data)
        return cls(config=cfg, backup_dir=backup_dir or cfg.backup_dir)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _filter_source_games(self, games: list[Game]) -> list[Game]:
        """
        Apply the inclusion/exclusion filters from :attr:`config` and return
        the subset of source games that should be considered for merging.

        Handles ``include_game_ids``, ``exclude_hidden``, ``exclude_platforms``,
        ``exclude_sources``, and ``incremental_since`` filters.
        """
        cfg = self.config
        result: list[Game] = []
        for g in games:
            if cfg.include_game_ids and g.Id not in cfg.include_game_ids:
                continue
            if cfg.exclude_hidden and g.Hidden:
                continue
            if cfg.exclude_platforms:
                plats = {nfc_lower(p) for p in g._platform_names}
                if plats.intersection({nfc_lower(p) for p in cfg.exclude_platforms}):
                    continue
            if cfg.exclude_sources:
                if nfc_lower(g._source_name) in {nfc_lower(s) for s in cfg.exclude_sources}:
                    continue
            if cfg.incremental_since and g.Modified:
                if g.Modified <= cfg.incremental_since:
                    continue
            result.append(g)
        return result

    def _find_match(self, source_game: Game, master: Library) -> Optional[Game]:
        """Find the best-matching game in *master* for *source_game*."""
        best_game: Optional[Game] = None
        best_score = self.config.match_threshold

        for mg in master.all_games():
            if not self._matcher.quick_candidate(source_game, mg):
                continue
            result = self._matcher.match(source_game, mg)
            if result.score >= best_score:
                best_score = result.score
                best_game = mg

        return best_game

    def _import_game(self, source_game: Game, source: Library, master: Library) -> Game:
        """
        Prepare a source game for insertion into master by mapping / copying
        its relationship IDs to equivalent entities in master.
        """
        imported = copy.deepcopy(source_game)

        # Map platform IDs
        imported.PlatformIds = [
            self._map_entity(pid, source.platforms, master.platforms)
            for pid in source_game.PlatformIds
        ]
        # Map company IDs
        imported.DeveloperIds = [
            self._map_entity(did, source.companies, master.companies)
            for did in source_game.DeveloperIds
        ]
        imported.PublisherIds = [
            self._map_entity(pid, source.companies, master.companies)
            for pid in source_game.PublisherIds
        ]
        # Map genre IDs
        imported.GenreIds = [
            self._map_entity(gid, source.genres, master.genres)
            for gid in source_game.GenreIds
        ]
        # Map category / tag IDs
        imported.CategoryIds = [
            self._map_entity(cid, source.categories, master.categories)
            for cid in source_game.CategoryIds
        ]
        imported.TagIds = [
            self._map_entity(tid, source.tags, master.tags)
            for tid in source_game.TagIds
        ]
        # Map source ID
        if source_game.SourceId and source_game.SourceId in source.sources:
            src_entity = source.sources[source_game.SourceId]
            imported.SourceId = master.get_or_create_source(src_entity.Name)

        return imported

    def _map_entity(
        self,
        src_id: str,
        src_table: dict[str, NamedEntity],
        dst_table: dict[str, NamedEntity],
    ) -> str:
        """
        Map a source entity ID to the equivalent destination ID.

        If the entity (by name) already exists in *dst_table*, return its ID.
        Otherwise insert it and return the new ID.
        """
        if src_id not in src_table:
            return src_id  # unknown ID, keep as-is
        entity = src_table[src_id]
        # Find by name in destination
        for eid, dest_entity in dst_table.items():
            if nfc_lower(dest_entity.Name) == nfc_lower(entity.Name):
                return eid
        # Not found – copy it across
        new_entity = NamedEntity(Id=str(uuid.uuid4()), Name=entity.Name)
        dst_table[new_entity.Id] = new_entity
        return new_entity.Id

    def _merge_entities(self, master: Library, source: Library) -> None:
        """Copy any reference entities from source that are missing in master."""
        tables = [
            (master.platforms, source.platforms),
            (master.companies, source.companies),
            (master.genres, source.genres),
            (master.categories, source.categories),
            (master.tags, source.tags),
            (master.series, source.series),
            (master.sources, source.sources),
            (master.age_ratings, source.age_ratings),
            (master.regions, source.regions),
            (master.completion_statuses, source.completion_statuses),
        ]
        for dst, src in tables:
            master_names = {nfc_lower(e.Name) for e in dst.values()}
            for src_entity in src.values():
                if nfc_lower(src_entity.Name) not in master_names:
                    new_entity = NamedEntity(Id=str(uuid.uuid4()), Name=src_entity.Name)
                    dst[new_entity.Id] = new_entity
                    master_names.add(nfc_lower(new_entity.Name))

    def _validate(self, library: Library) -> list[str]:
        """Basic integrity checks on the merged library."""
        issues: list[str] = []
        platform_ids = set(library.platforms.keys())
        company_ids = set(library.companies.keys())
        genre_ids = set(library.genres.keys())

        for game in library.all_games():
            if not game.Id:
                issues.append(f"CRITICAL: Game '{game.Name}' has no Id")
            if not game.Name:
                issues.append(f"Game with Id={game.Id} has no Name")
            for pid in game.PlatformIds:
                if pid and pid not in platform_ids:
                    issues.append(f"Game '{game.Name}': unknown PlatformId {pid}")
            for did in game.DeveloperIds:
                if did and did not in company_ids:
                    issues.append(f"Game '{game.Name}': unknown DeveloperId {did}")
            for gid in game.GenreIds:
                if gid and gid not in genre_ids:
                    issues.append(f"Game '{game.Name}': unknown GenreId {gid}")

        return issues

    def _serialise_library(self, library: Library) -> dict[str, Any]:
        """Return a full JSON-serialisable dict of the library."""
        def _serial(table: dict) -> list:
            return [e.to_dict() for e in table.values()]
        return {
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
