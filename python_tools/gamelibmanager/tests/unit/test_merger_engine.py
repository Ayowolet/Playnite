"""Tests for LibraryMerger engine."""

import uuid
from datetime import datetime

import pytest
from gamelibmanager.db.database import GameDatabase
from gamelibmanager.merger.config import MergeConfig
from gamelibmanager.merger.engine import LibraryMerger
from gamelibmanager.merger.strategy import MergeStrategyType
from gamelibmanager.models.game import Game
from gamelibmanager.models.release_date import ReleaseDate
from tests.factories import (
    STEAM_SOURCE_ID, GOG_SOURCE_ID, STEAM_PLUGIN_ID, GOG_PLUGIN_ID,
    PC_PLATFORM_ID, make_game, make_lookup_tables,
)


class TestLibraryMerger:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.source_db = GameDatabase(str(tmp_path / "source.db"))
        self.source_db.open()
        make_lookup_tables(self.source_db)

        self.target_db = GameDatabase(str(tmp_path / "target.db"))
        self.target_db.open()
        make_lookup_tables(self.target_db)

        self.tmp_path = tmp_path
        yield
        self.source_db.close()
        self.target_db.close()

    def test_add_new_games(self):
        src_game = make_game(name="New Game", source_id=STEAM_SOURCE_ID)
        self.source_db.add_game(src_game)

        config = MergeConfig(strategy_type=MergeStrategyType.MERGE_ALL)
        merger = LibraryMerger(self.source_db, self.target_db, config)
        report = merger.execute()

        assert report.games_added == 1
        assert self.target_db.game_count() == 1

    def test_match_by_provider_id(self):
        src = make_game(name="DOOM", game_id="123", plugin_id=STEAM_PLUGIN_ID,
                       description="Source desc", modified=datetime(2024, 6, 1))
        tgt = make_game(name="DOOM", game_id="123", plugin_id=STEAM_PLUGIN_ID,
                       description="", modified=datetime(2024, 1, 1))
        self.source_db.add_game(src)
        self.target_db.add_game(tgt)

        config = MergeConfig(strategy_type=MergeStrategyType.MERGE_ALL)
        merger = LibraryMerger(self.source_db, self.target_db, config)
        report = merger.execute()

        assert report.games_updated == 1
        assert report.games_added == 0
        updated = self.target_db.get_game(tgt.id)
        assert updated.description == "Source desc"

    def test_match_by_fuzzy_title(self):
        src = make_game(name="The Witcher 3: Wild Hunt",
                       description="From source", modified=datetime(2024, 6, 1))
        tgt = make_game(name="Witcher 3 Wild Hunt",
                       description="", modified=datetime(2024, 1, 1))
        self.source_db.add_game(src)
        self.target_db.add_game(tgt)

        config = MergeConfig(
            strategy_type=MergeStrategyType.MERGE_ALL,
            fuzzy_match_threshold=0.75,
        )
        merger = LibraryMerger(self.source_db, self.target_db, config)
        report = merger.execute()

        assert report.games_updated == 1
        assert report.games_added == 0

    def test_keep_source_strategy(self):
        src = make_game(name="Game", description="Source", modified=datetime(2024, 1, 1),
                       game_id="same", plugin_id=STEAM_PLUGIN_ID)
        tgt = make_game(name="Game", description="Target", modified=datetime(2024, 6, 1),
                       game_id="same", plugin_id=STEAM_PLUGIN_ID)
        self.source_db.add_game(src)
        self.target_db.add_game(tgt)

        config = MergeConfig(strategy_type=MergeStrategyType.KEEP_SOURCE)
        merger = LibraryMerger(self.source_db, self.target_db, config)
        merger.execute()

        updated = self.target_db.get_game(tgt.id)
        assert updated.description == "Source"

    def test_keep_target_strategy(self):
        src = make_game(name="Game", description="Source", modified=datetime(2024, 1, 1),
                       game_id="same", plugin_id=STEAM_PLUGIN_ID)
        tgt = make_game(name="Game", description="Target", modified=datetime(2024, 6, 1),
                       game_id="same", plugin_id=STEAM_PLUGIN_ID)
        self.source_db.add_game(src)
        self.target_db.add_game(tgt)

        config = MergeConfig(strategy_type=MergeStrategyType.KEEP_TARGET)
        merger = LibraryMerger(self.source_db, self.target_db, config)
        merger.execute()

        updated = self.target_db.get_game(tgt.id)
        assert updated.description == "Target"

    def test_preview_without_execution(self):
        src = make_game(name="Preview Game")
        self.source_db.add_game(src)

        config = MergeConfig()
        merger = LibraryMerger(self.source_db, self.target_db, config)
        preview = merger.preview()

        assert len(preview.games_to_add) == 1
        assert self.target_db.game_count() == 0  # Not actually added

    def test_selective_merge_by_game_id(self):
        g1 = make_game(name="Include")
        g2 = make_game(name="Exclude")
        self.source_db.add_games_batch([g1, g2])

        config = MergeConfig(selective_game_ids={g1.id})
        merger = LibraryMerger(self.source_db, self.target_db, config)
        report = merger.execute()

        assert report.games_added == 1
        added = self.target_db.get_all_games()
        assert added[0].name == "Include"

    def test_no_update_when_disabled(self):
        src = make_game(name="Game", description="New", game_id="x", plugin_id=STEAM_PLUGIN_ID)
        tgt = make_game(name="Game", description="Old", game_id="x", plugin_id=STEAM_PLUGIN_ID)
        self.source_db.add_game(src)
        self.target_db.add_game(tgt)

        config = MergeConfig(update_existing=False)
        merger = LibraryMerger(self.source_db, self.target_db, config)
        report = merger.execute()

        assert report.games_updated == 0
        updated = self.target_db.get_game(tgt.id)
        assert updated.description == "Old"

    def test_validate_library(self):
        g1 = make_game(name="Valid")
        g2 = make_game(name="")  # Empty name
        self.target_db.add_games_batch([g1, g2])

        config = MergeConfig()
        merger = LibraryMerger(self.source_db, self.target_db, config)
        issues = merger.validate_library(self.target_db)
        assert any("no name" in i for i in issues)

    def test_merge_report_json(self):
        src = make_game(name="Game")
        self.source_db.add_game(src)

        config = MergeConfig()
        merger = LibraryMerger(self.source_db, self.target_db, config)
        report = merger.execute()

        json_str = report.to_json()
        import json
        data = json.loads(json_str)
        assert data["games_added"] == 1
