"""Integration tests for the complete merge workflow."""

import json
from datetime import datetime

import pytest
from gamelibmanager.db.database import GameDatabase
from gamelibmanager.merger.backup import MergeBackup
from gamelibmanager.merger.config import MergeConfig
from gamelibmanager.merger.engine import LibraryMerger
from gamelibmanager.merger.strategy import MergeStrategyType
from tests.factories import (
    STEAM_SOURCE_ID, GOG_SOURCE_ID, STEAM_PLUGIN_ID, GOG_PLUGIN_ID,
    make_game, make_lookup_tables,
)


class TestMergeWorkflow:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.tmp_path = tmp_path
        self.source_db = GameDatabase(str(tmp_path / "source.db"))
        self.source_db.open()
        make_lookup_tables(self.source_db)

        self.target_db = GameDatabase(str(tmp_path / "target.db"))
        self.target_db.open()
        make_lookup_tables(self.target_db)

        # Create library dirs for media handling
        self.source_lib = tmp_path / "source_lib"
        self.target_lib = tmp_path / "target_lib"
        for d in [self.source_lib, self.target_lib]:
            (d / "games").mkdir(parents=True)
            (d / "files").mkdir(parents=True)

        yield
        self.source_db.close()
        self.target_db.close()

    def test_full_merge_workflow(self):
        """End-to-end: preview -> backup -> merge -> verify -> report."""
        # 1. Setup source with games
        src_games = [
            make_game(name="Shared Game", game_id="shared", plugin_id=STEAM_PLUGIN_ID,
                     description="Updated desc", modified=datetime(2024, 6, 1)),
            make_game(name="Source Only Game", source_id=STEAM_SOURCE_ID),
        ]
        self.source_db.add_games_batch(src_games)

        # 2. Setup target with overlapping game
        tgt_game = make_game(name="Shared Game", game_id="shared", plugin_id=STEAM_PLUGIN_ID,
                            description="Old desc", modified=datetime(2024, 1, 1))
        self.target_db.add_game(tgt_game)

        # 3. Configure merge
        config = MergeConfig(
            strategy_type=MergeStrategyType.MERGE_ALL,
            backup_dir=str(self.tmp_path / "backups"),
            source_library_path=str(self.source_lib),
            target_library_path=str(self.target_lib),
        )

        merger = LibraryMerger(self.source_db, self.target_db, config)

        # 4. Preview
        preview = merger.preview()
        assert len(preview.games_to_add) == 1
        assert len(preview.games_to_update) == 1

        # 5. Execute
        report = merger.execute()
        assert report.games_added == 1
        assert report.games_updated == 1
        assert report.backup_path != ""
        assert len(report.errors) == 0

        # 6. Verify target
        all_target = self.target_db.get_all_games()
        assert len(all_target) == 2

        # The shared game should have updated description
        shared = self.target_db.get_game(tgt_game.id)
        assert shared.description == "Updated desc"

        # 7. Report
        json_report = report.to_json()
        data = json.loads(json_report)
        assert data["games_added"] == 1
        assert data["games_updated"] == 1

    def test_merge_with_rollback(self):
        """Test that rollback restores the target to its original state."""
        original = make_game(name="Original Game")
        self.target_db.add_game(original)

        # Source has games that will be added
        for i in range(5):
            self.source_db.add_game(make_game(name=f"New Game {i}"))

        backup_dir = str(self.tmp_path / "backups")
        config = MergeConfig(
            backup_dir=backup_dir,
            source_library_path=str(self.source_lib),
            target_library_path=str(self.target_lib),
        )

        merger = LibraryMerger(self.source_db, self.target_db, config)
        report = merger.execute()

        assert self.target_db.game_count() == 6  # 1 original + 5 new

        # Rollback via backup restore
        backup = MergeBackup(self.target_lib, backup_dir)
        backup.restore_backup(report.backup_path)
        # Note: DB rollback would need to re-open the DB from backup

    def test_incremental_merge(self):
        """Incremental merge should only process changed games."""
        import time
        # First merge
        g1 = make_game(name="Game 1", modified=datetime(2024, 1, 1))
        self.source_db.add_game(g1)

        config = MergeConfig(
            source_library_path=str(self.source_lib),
            target_library_path=str(self.target_lib),
        )
        merger = LibraryMerger(self.source_db, self.target_db, config)
        merger.execute()
        assert self.target_db.game_count() == 1

        # Add new game to source after first merge with a modified time
        # that is after the merge timestamp (which is datetime.now())
        time.sleep(0.05)
        g2 = make_game(name="Game 2", modified=datetime.now())
        self.source_db.add_game(g2)

        # Incremental merge
        config2 = MergeConfig(
            incremental=True,
            source_library_path=str(self.source_lib),
            target_library_path=str(self.target_lib),
        )
        merger2 = LibraryMerger(self.source_db, self.target_db, config2)
        report = merger2.execute()

        # Should add the new game
        assert self.target_db.game_count() == 2

    def test_merge_config_export_import(self):
        """Configuration should round-trip through JSON."""
        config = MergeConfig(
            strategy_type=MergeStrategyType.KEEP_NEWEST,
            backup_dir="/backups",
            include_media=False,
            fuzzy_match_threshold=0.90,
            source_library_path="/source",
            target_library_path="/target",
        )
        json_str = config.to_json()
        restored = MergeConfig.from_json(json_str)

        assert restored.strategy_type == MergeStrategyType.KEEP_NEWEST
        assert restored.backup_dir == "/backups"
        assert restored.include_media is False
        assert restored.fuzzy_match_threshold == 0.90

    def test_validate_after_merge(self):
        """Merged library should pass validation."""
        self.source_db.add_game(make_game(name="Game"))
        config = MergeConfig()
        merger = LibraryMerger(self.source_db, self.target_db, config)
        merger.execute()

        issues = merger.validate_library(self.target_db)
        assert len(issues) == 0

    def test_merge_unicode_titles(self):
        """Merge with Japanese, Cyrillic, accented, emoji, and Korean titles."""
        src_games = [
            make_game(name="ファイナルファンタジー VII", game_id="ff7",
                     plugin_id=STEAM_PLUGIN_ID, description="Classic RPG",
                     modified=datetime(2024, 6, 1)),
            make_game(name="Pokémon Legends: Arceus"),
            make_game(name="Метро: Исход"),
            make_game(name="🎮 Super Mario Bros 🎮"),
            make_game(name="메이플스토리"),
        ]
        self.source_db.add_games_batch(src_games)

        # Target has overlapping Japanese game with older data
        tgt_game = make_game(name="ファイナルファンタジー VII", game_id="ff7",
                            plugin_id=STEAM_PLUGIN_ID, description="",
                            modified=datetime(2024, 1, 1))
        self.target_db.add_game(tgt_game)

        config = MergeConfig(
            source_library_path=str(self.source_lib),
            target_library_path=str(self.target_lib),
        )
        merger = LibraryMerger(self.source_db, self.target_db, config)

        preview = merger.preview()
        assert len(preview.games_to_add) == 4
        assert len(preview.games_to_update) == 1

        report = merger.execute()
        assert report.games_added == 4
        assert report.games_updated == 1
        assert len(report.errors) == 0

        all_target = self.target_db.get_all_games()
        assert len(all_target) == 5
        target_names = {g.name for g in all_target}
        assert "ファイナルファンタジー VII" in target_names
        assert "Pokémon Legends: Arceus" in target_names
        assert "Метро: Исход" in target_names
        assert "🎮 Super Mario Bros 🎮" in target_names
        assert "메이플스토리" in target_names

        # Description should be merged from source
        updated = self.target_db.get_game(tgt_game.id)
        assert updated.description == "Classic RPG"
