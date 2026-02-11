"""Library merger orchestrator."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ..db.concurrency import DatabaseLockedError, is_lock_error
from ..duplicates.normalizer import TitleNormalizer
from ..models.game import Game
from ..models.lookup_tables import (
    AgeRating, Category, Company, CompletionStatus, GameFeature,
    GameSource, Genre, Platform, Region, Series, Tag,
)
from .backup import MergeBackup
from .config import MergeConfig
from .conflict import ConflictDetector, ConflictRecord, FieldConflict
from .incremental import IncrementalMerger
from .media import MediaHandler
from .preview import MergePreview
from .report import MergeReport
from .rollback import RollbackManager
from .strategy import MergeStrategy, create_strategy

_EMPTY_UUID = uuid.UUID(int=0)


@dataclass
class _GamePair:
    source: Game
    target: Game


class LibraryMerger:
    """Main orchestrator for library merge operations."""

    def __init__(self, source_db: object, target_db: object, config: MergeConfig):
        from ..db.database import GameDatabase
        self.source_db: GameDatabase = source_db  # type: ignore[assignment]
        self.target_db: GameDatabase = target_db  # type: ignore[assignment]
        self.config = config
        self.conflict_detector = ConflictDetector()
        self.strategy: MergeStrategy = create_strategy(config.strategy_type)
        self._errors: list[str] = []
        self._warnings: list[str] = []

    def preview(self) -> MergePreview:
        """Generate a preview without executing."""
        source_games = self._get_source_games()
        target_games = self.target_db.get_all_games()

        matched, source_only, _target_only = self._match_games(source_games, target_games)

        preview = MergePreview()

        if self.config.add_new_games:
            preview.games_to_add = source_only

        if self.config.update_existing:
            for pair in matched:
                conflicts = self.conflict_detector.detect_conflicts(pair.source, pair.target)
                if conflicts:
                    preview.games_to_update.append((pair.source, pair.target, conflicts))
                    preview.total_conflicts += len(conflicts)
                else:
                    preview.games_to_skip.append(pair.source)
        else:
            preview.games_to_skip = [p.source for p in matched]

        # Count media files
        if self.config.include_media and self.config.source_library_path and self.config.target_library_path:
            media = MediaHandler(self.config.source_library_path, self.config.target_library_path)
            for g in preview.games_to_add:
                preview.media_files_to_copy += media.count_media_to_copy(g)
            for src, _tgt, _conflicts in preview.games_to_update:
                preview.media_files_to_copy += media.count_media_to_copy(src)

        return preview

    def execute(
        self, progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> MergeReport:
        """Execute the merge operation."""
        start_time = time.time()
        report = MergeReport(
            timestamp=datetime.now(),
            source_library=self.config.source_library_path,
            target_library=self.config.target_library_path,
            strategy=self.config.strategy_type.value,
        )

        # 1. Create backup
        backup_path = ""
        rollback: RollbackManager | None = None
        if self.config.backup_dir:
            rollback = RollbackManager(
                self.target_db, self.config.backup_dir,
                self.config.target_library_path or ".",
            )
            try:
                backup_path = rollback.begin_merge(self.config.include_media)
                report.backup_path = backup_path
            except Exception as e:
                self._errors.append(f"Backup failed: {e}")
                report.errors = self._errors
                return report

        try:
            # 2. Get games
            source_games = self._get_source_games()
            target_games = self.target_db.get_all_games()

            if progress_callback:
                progress_callback("Matching games", 0, len(source_games))

            # 3. Match
            matched, source_only, _target_only = self._match_games(source_games, target_games)

            # 4. Process matched pairs
            conflict_records: list[ConflictRecord] = []
            for i, pair in enumerate(matched):
                if progress_callback:
                    progress_callback("Merging matched games", i, len(matched))
                try:
                    conflicts = self.conflict_detector.detect_conflicts(pair.source, pair.target)
                    if conflicts and self.config.update_existing:
                        merged_game = self._merge_game_pair(pair.source, pair.target, conflicts)
                        self.target_db.update_game(merged_game)
                        report.games_updated += 1
                        report.conflicts_resolved += len(conflicts)
                        conflict_records.append(ConflictRecord(
                            source_game_id=pair.source.id,
                            target_game_id=pair.target.id,
                            game_name=pair.target.name,
                            conflicts=conflicts,
                            resolution_strategy=self.config.strategy_type.value,
                        ))
                    else:
                        report.games_skipped += 1
                except sqlite3.OperationalError as exc:
                    if is_lock_error(exc):
                        raise DatabaseLockedError(
                            f"merge game '{pair.source.name}'", 1, exc,
                        )
                    self._warnings.append(f"Error merging {pair.source.name}: {exc}")
                    report.games_skipped += 1
                except Exception as e:
                    self._warnings.append(f"Error merging {pair.source.name}: {e}")
                    report.games_skipped += 1

            # 5. Add new games
            if self.config.add_new_games:
                for i, game in enumerate(source_only):
                    if progress_callback:
                        progress_callback("Adding new games", i, len(source_only))
                    try:
                        new_game = self._add_new_game(game)
                        self.target_db.add_game(new_game)
                        report.games_added += 1
                    except sqlite3.OperationalError as exc:
                        if is_lock_error(exc):
                            raise DatabaseLockedError(
                                f"add game '{game.name}'", 1, exc,
                            )
                        self._warnings.append(f"Error adding {game.name}: {exc}")
                    except Exception as e:
                        self._warnings.append(f"Error adding {game.name}: {e}")

            # 6. Copy media
            if self.config.include_media and self.config.source_library_path and self.config.target_library_path:
                media = MediaHandler(self.config.source_library_path, self.config.target_library_path)
                all_pairs = [(p.source, p.target) for p in matched]
                for src, tgt in all_pairs:
                    report.media_files_copied += media.copy_media(src, tgt)
                for g in source_only:
                    report.media_files_copied += media.copy_media(g, g)

            # 7. Record merge history
            self._record_merge_history(report)

            # 8. Commit
            if rollback:
                rollback.commit()

            report.conflicts_details = conflict_records

        except DatabaseLockedError as e:
            self._errors.append(str(e))
            if rollback:
                rollback.rollback_all()
        except Exception as e:
            self._errors.append(f"Critical error: {e}")
            if rollback:
                rollback.rollback_all()

        report.errors = self._errors
        report.warnings = self._warnings
        report.duration_seconds = time.time() - start_time
        return report

    def validate_library(self, db: object) -> list[str]:
        """Validate library integrity. Returns list of issues found."""
        from ..db.database import GameDatabase
        _db: GameDatabase = db  # type: ignore[assignment]
        issues: list[str] = []

        games = _db.get_all_games()
        seen_ids: set[uuid.UUID] = set()
        for g in games:
            if g.id in seen_ids:
                issues.append(f"Duplicate game ID: {g.id} ({g.name})")
            seen_ids.add(g.id)
            if not g.name:
                issues.append(f"Game {g.id} has no name")

        return issues

    # ------------------------------------------------------------------ #
    # Internal matching
    # ------------------------------------------------------------------ #

    def _get_source_games(self) -> list[Game]:
        all_games = self.source_db.get_all_games()

        # Apply selective filters
        if self.config.selective_game_ids:
            all_games = [g for g in all_games if g.id in self.config.selective_game_ids]

        if self.config.selective_categories:
            # Filter by category names
            filtered = []
            for g in all_games:
                if g.category_ids:
                    for cid in g.category_ids:
                        cat = self.source_db.get_lookup(Category, cid)
                        if cat and cat.name in self.config.selective_categories:
                            filtered.append(g)
                            break
            all_games = filtered

        # Incremental: only changed since last merge
        if self.config.incremental:
            inc = IncrementalMerger(self.target_db)
            last_time = inc.get_last_merge_time(self.config.source_library_path)
            if last_time:
                all_games = [
                    g for g in all_games
                    if g.modified and g.modified > last_time
                ]

        return all_games

    def _match_games(
        self,
        source_games: list[Game],
        target_games: list[Game],
    ) -> tuple[list[_GamePair], list[Game], list[Game]]:
        """Match games between source and target.

        Priority:
        1. Exact: same GameId + PluginId
        2. Exact normalised title
        3. Fuzzy: batch ``cdist`` comparison above threshold
        """
        matched: list[_GamePair] = []
        source_only: list[Game] = []
        target_matched_ids: set[uuid.UUID] = set()

        # Build target index by (plugin_id, game_id)
        target_by_provider: dict[tuple[uuid.UUID, str], Game] = {}
        for tg in target_games:
            if tg.plugin_id != _EMPTY_UUID and tg.game_id:
                target_by_provider[(tg.plugin_id, tg.game_id)] = tg

        # Build target index by normalised name
        target_by_norm: dict[str, list[Game]] = {}
        for tg in target_games:
            norm = TitleNormalizer.normalize(tg.name)
            target_by_norm.setdefault(norm, []).append(tg)

        # --- Pass 1: exact provider match + exact normalised name ---
        fuzzy_pending: list[tuple[Game, str]] = []  # (game, norm)

        for sg in source_games:
            # 1. Exact provider match
            key = (sg.plugin_id, sg.game_id)
            if key in target_by_provider and sg.plugin_id != _EMPTY_UUID:
                tg = target_by_provider[key]
                if tg.id not in target_matched_ids:
                    matched.append(_GamePair(source=sg, target=tg))
                    target_matched_ids.add(tg.id)
                    continue

            # 2. Exact normalised name match
            norm_s = TitleNormalizer.normalize(sg.name)
            found = False
            if norm_s in target_by_norm:
                for tg in target_by_norm[norm_s]:
                    if tg.id not in target_matched_ids:
                        matched.append(_GamePair(source=sg, target=tg))
                        target_matched_ids.add(tg.id)
                        found = True
                        break

            if not found:
                fuzzy_pending.append((sg, norm_s))

        # --- Pass 2: batch fuzzy matching via cdist ---
        if fuzzy_pending:
            from rapidfuzz import fuzz, process

            target_norm_list = list(target_by_norm.keys())
            source_norms = [norm for _, norm in fuzzy_pending]
            cutoff = self.config.fuzzy_match_threshold * 100

            # Compute score matrix (source x target) in parallel C++
            score_matrix = process.cdist(
                source_norms,
                target_norm_list,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=cutoff,
                workers=-1,
            )

            # Build (score, src_idx, tgt_idx) pairs sorted by score descending
            import numpy as np
            src_indices, tgt_indices = np.nonzero(score_matrix >= cutoff)
            scores = score_matrix[src_indices, tgt_indices]
            order = np.argsort(-scores)

            matched_src: set[int] = set()
            for k in order:
                si = int(src_indices[k])
                ti = int(tgt_indices[k])
                if si in matched_src:
                    continue
                tgt_norm = target_norm_list[ti]
                # Find an unclaimed game in this normalised-name group
                best: Game | None = None
                for tg in target_by_norm[tgt_norm]:
                    if tg.id not in target_matched_ids:
                        best = tg
                        break
                if best is not None:
                    sg = fuzzy_pending[si][0]
                    matched.append(_GamePair(source=sg, target=best))
                    target_matched_ids.add(best.id)
                    matched_src.add(si)

            # Remaining unmatched source games
            for i, (sg, _) in enumerate(fuzzy_pending):
                if i not in matched_src:
                    source_only.append(sg)
        else:
            source_only = []

        target_only = [tg for tg in target_games if tg.id not in target_matched_ids]
        return matched, source_only, target_only

    def _merge_game_pair(
        self, source: Game, target: Game, conflicts: list[FieldConflict],
    ) -> Game:
        """Merge two matched games using the configured strategy."""
        for conflict in conflicts:
            resolved = self.strategy.resolve(
                conflict.field_name,
                conflict.source_value,
                conflict.target_value,
                source,
                target,
            )
            conflict.resolved_value = resolved
            setattr(target, conflict.field_name, resolved)

        # Update modified timestamp
        target.modified = datetime.now()
        return target

    def _add_new_game(self, source_game: Game) -> Game:
        """Prepare a source game for insertion into the target library."""
        new_game = Game(
            id=source_game.id if self.config.preserve_target_ids else uuid.uuid4(),
            name=source_game.name,
            game_id=source_game.game_id,
            plugin_id=source_game.plugin_id,
            sorting_name=source_game.sorting_name,
            description=source_game.description,
            notes=source_game.notes,
            hidden=source_game.hidden,
            favorite=source_game.favorite,
            is_installed=False,  # Not installed in target
            platform_ids=self._remap_lookup_ids(source_game.platform_ids, Platform),
            developer_ids=self._remap_lookup_ids(source_game.developer_ids, Company),
            publisher_ids=self._remap_lookup_ids(source_game.publisher_ids, Company),
            genre_ids=self._remap_lookup_ids(source_game.genre_ids, Genre),
            category_ids=self._remap_lookup_ids(source_game.category_ids, Category),
            tag_ids=self._remap_lookup_ids(source_game.tag_ids, Tag),
            feature_ids=self._remap_lookup_ids(source_game.feature_ids, GameFeature),
            series_ids=self._remap_lookup_ids(source_game.series_ids, Series),
            age_rating_ids=self._remap_lookup_ids(source_game.age_rating_ids, AgeRating),
            region_ids=self._remap_lookup_ids(source_game.region_ids, Region),
            source_id=self._remap_single_id(source_game.source_id, GameSource),
            completion_status_id=self._remap_single_id(
                source_game.completion_status_id, CompletionStatus
            ),
            release_date=source_game.release_date,
            last_activity=source_game.last_activity,
            added=datetime.now(),
            modified=datetime.now(),
            playtime=source_game.playtime,
            play_count=source_game.play_count,
            user_score=source_game.user_score,
            critic_score=source_game.critic_score,
            community_score=source_game.community_score,
            icon=source_game.icon,
            cover_image=source_game.cover_image,
            background_image=source_game.background_image,
            version=source_game.version,
            links=source_game.links,
            game_actions=source_game.game_actions,
            roms=source_game.roms,
        )
        return new_game

    def _remap_lookup_ids(
        self, ids: list[uuid.UUID] | None, cls: type,
    ) -> list[uuid.UUID] | None:
        """Remap lookup IDs from source to target by matching names."""
        if not ids:
            return ids
        remapped = []
        for uid in ids:
            new_id = self._remap_single_id(uid, cls)
            if new_id != _EMPTY_UUID:
                remapped.append(new_id)
        return remapped if remapped else None

    def _remap_single_id(self, uid: uuid.UUID, cls: type) -> uuid.UUID:
        """Find or create matching lookup entity in target."""
        if uid == _EMPTY_UUID:
            return _EMPTY_UUID
        # Look up in source
        src_obj = self.source_db.get_lookup(cls, uid)
        if not src_obj:
            return uid  # Keep original ID if not found

        # Find by name in target
        tgt_obj = self.target_db.find_lookup_by_name(cls, src_obj.name)
        if tgt_obj:
            return tgt_obj.id

        # Create in target
        self.target_db.add_lookup(src_obj)
        return src_obj.id

    def _record_merge_history(self, report: MergeReport) -> None:
        assert self.target_db.conn is not None
        self.target_db.conn.execute(
            "INSERT INTO merge_history "
            "(timestamp, source_library, target_library, strategy, "
            "games_added, games_updated, games_skipped, conflicts_resolved, "
            "backup_path, details) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(),
                os.path.normcase(self.config.source_library_path)
                if self.config.source_library_path else "",
                os.path.normcase(self.config.target_library_path)
                if self.config.target_library_path else "",
                self.config.strategy_type.value,
                report.games_added,
                report.games_updated,
                report.games_skipped,
                report.conflicts_resolved,
                report.backup_path,
                json.dumps({"errors": report.errors, "warnings": report.warnings}),
            ),
        )
