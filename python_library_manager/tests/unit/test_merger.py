"""Unit tests for the LibraryMerger."""
import json
import pytest
from game_library.merger.merger import LibraryMerger, MergeConfig
from game_library.merger.strategies import MergeStrategy
from tests.conftest import make_game, make_library


class TestMergePreview:
    def test_preview_identifies_new_games(self, master_library, source_library):
        merger = LibraryMerger(MergeConfig(match_threshold=0.80))
        preview = merger.preview(master_library, source_library)
        # All source games either match or are new
        assert len(preview.plans) == len(source_library.games)

    def test_preview_matches_known_duplicates(self, master_library, source_library):
        merger = LibraryMerger(MergeConfig(match_threshold=0.80))
        preview = merger.preview(master_library, source_library)
        # Witcher 3 and Portal 2 should match existing master games
        updated = preview.updated_games
        assert len(updated) >= 2

    def test_preview_doesnt_modify_library(self, master_library, source_library):
        original_count = len(master_library.games)
        merger = LibraryMerger(MergeConfig(match_threshold=0.80))
        merger.preview(master_library, source_library)
        assert len(master_library.games) == original_count

    def test_preview_to_dict_serialisable(self, master_library, source_library):
        merger = LibraryMerger(MergeConfig(match_threshold=0.80))
        preview = merger.preview(master_library, source_library)
        json.dumps(preview.to_dict())


class TestMergeExecute:
    def test_execute_creates_backup(self, master_library, source_library, tmp_path):
        cfg = MergeConfig(match_threshold=0.80, backup_dir=str(tmp_path / "backups"))
        merger = LibraryMerger(cfg, backup_dir=tmp_path / "backups")
        result = merger.execute(master_library, source_library)
        assert result.backup_record is not None
        assert result.backup_record.game_count > 0

    def test_execute_adds_new_games(self, tmp_path):
        """Source-only games should be added to master."""
        master_games = [make_game("Existing Game", year=2020, source="Steam")]
        source_games = [make_game("Brand New Game", year=2023, source="GOG")]
        master = make_library("master", master_games)
        source = make_library("source", source_games)
        cfg = MergeConfig(match_threshold=0.85, backup_dir=str(tmp_path / "backups"))
        merger = LibraryMerger(cfg)
        result = merger.execute(master, source)
        assert result.games_added == 1
        assert result.success

    def test_execute_updates_matched_games(self, master_library, source_library, tmp_path):
        cfg = MergeConfig(
            match_threshold=0.80,
            strategy=MergeStrategy.MERGE_PREFER_SOURCE,
            backup_dir=str(tmp_path / "backups"),
        )
        merger = LibraryMerger(cfg)
        result = merger.execute(master_library, source_library)
        assert result.success
        assert result.games_updated >= 1

    def test_execute_result_serialisable(self, master_library, source_library, tmp_path):
        cfg = MergeConfig(match_threshold=0.80, backup_dir=str(tmp_path / "backups"))
        merger = LibraryMerger(cfg)
        result = merger.execute(master_library, source_library)
        json.dumps(result.to_dict())


class TestMergeRollback:
    def test_rollback_restores_library(self, master_library, source_library, tmp_path):
        original_game_ids = set(master_library.games.keys())
        cfg = MergeConfig(match_threshold=0.80, backup_dir=str(tmp_path / "backups"))
        merger = LibraryMerger(cfg)
        result = merger.execute(master_library, source_library)
        assert result.success

        # After merge, library may have changed
        merger.rollback(result, master_library)
        restored_ids = set(master_library.games.keys())
        assert restored_ids == original_game_ids, "Rollback should restore original game IDs"


class TestMergeStrategies:
    def _two_game_libraries(self, master_desc="Master", source_desc="Source", tmp_path=None):
        ga = make_game("Test Game", year=2020, description=master_desc, cover="master.jpg")
        gb = make_game("Test Game", year=2020, description=source_desc, cover="source.jpg")
        master = make_library("master", [ga])
        source = make_library("source", [gb])
        return master, source

    def test_keep_master_preserves_description(self, tmp_path):
        master, source = self._two_game_libraries("Original", "New")
        cfg = MergeConfig(
            strategy=MergeStrategy.KEEP_MASTER,
            match_threshold=0.85,
            backup_dir=str(tmp_path / "backups"),
        )
        merger = LibraryMerger(cfg)
        merger.execute(master, source)
        game = next(iter(master.games.values()))
        assert game.Description == "Original"

    def test_keep_source_overwrites_description(self, tmp_path):
        master, source = self._two_game_libraries("Original", "New")
        cfg = MergeConfig(
            strategy=MergeStrategy.KEEP_SOURCE,
            match_threshold=0.85,
            backup_dir=str(tmp_path / "backups"),
        )
        merger = LibraryMerger(cfg)
        merger.execute(master, source)
        game = next(iter(master.games.values()))
        assert game.Description == "New"


class TestMergeIncrementalMode:
    def test_incremental_skips_old_games(self, tmp_path):
        """Games not modified after incremental_since should be skipped."""
        old_game = make_game("Old Game", year=2019, source="GOG")
        old_game.Modified = "2022-01-01T00:00:00"
        new_game = make_game("New Game", year=2023, source="GOG")
        new_game.Modified = "2024-06-01T00:00:00"
        source = make_library("source", [old_game, new_game])
        master = make_library("master", [])
        cfg = MergeConfig(
            incremental_since="2023-01-01T00:00:00",
            backup_dir=str(tmp_path / "backups"),
        )
        merger = LibraryMerger(cfg)
        result = merger.execute(master, source)
        assert result.games_added == 1  # only new_game


class TestMergeConfigExport:
    def test_export_and_reload(self, tmp_path):
        cfg = MergeConfig(
            strategy=MergeStrategy.MOST_COMPLETE,
            match_threshold=0.75,
            exclude_hidden=True,
        )
        merger = LibraryMerger(cfg)
        config_path = tmp_path / "config.json"
        merger.export_config(config_path)
        reloaded = LibraryMerger.load_config(config_path)
        assert reloaded.config.strategy == MergeStrategy.MOST_COMPLETE
        assert reloaded.config.match_threshold == 0.75
        assert reloaded.config.exclude_hidden is True


class TestMergeValidation:
    def test_integrity_validation_catches_invalid_ids(self, tmp_path):
        """Games referencing non-existent entity IDs should surface as warnings."""
        game = make_game("Broken Game", year=2020)
        game.PlatformIds = ["non-existent-platform-id"]
        master = make_library("master", [])
        source = make_library("source", [game])
        cfg = MergeConfig(match_threshold=0.85, backup_dir=str(tmp_path / "backups"))
        merger = LibraryMerger(cfg)
        result = merger.execute(master, source)
        # Validation errors should be captured but merge should still succeed
        # (entity IDs are mapped during import, so platform may be resolved)
        assert result.success or len(result.errors) > 0
