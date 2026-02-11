"""Tests for DuplicateDetector."""

import uuid
from datetime import datetime

import pytest
from gamelibmanager.db.database import GameDatabase
from gamelibmanager.duplicates.config import DetectionConfig, DetectionFilter
from gamelibmanager.duplicates.detector import DuplicateDetector
from gamelibmanager.models.game import Game
from gamelibmanager.models.release_date import ReleaseDate
from tests.factories import (
    STEAM_SOURCE_ID, GOG_SOURCE_ID, PC_PLATFORM_ID, STEAM_PLUGIN_ID, GOG_PLUGIN_ID,
    make_game, make_lookup_tables, make_witcher_steam, make_witcher_gog,
    make_witcher_goty, make_elden_ring, make_half_life,
)


class TestDuplicateDetector:
    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        self.db_path = tmp_path / "test.db"
        self.db = GameDatabase(str(self.db_path))
        self.db.open()
        make_lookup_tables(self.db)
        yield
        self.db.close()

    def test_finds_exact_duplicates(self):
        g1 = make_game(name="DOOM", game_id="123", plugin_id=STEAM_PLUGIN_ID)
        g2 = make_game(name="DOOM", game_id="123", plugin_id=STEAM_PLUGIN_ID)
        self.db.add_games_batch([g1, g2])

        detector = DuplicateDetector(self.db)
        groups = detector.detect()
        assert len(groups) == 1
        assert groups[0].size == 2

    def test_finds_near_duplicates(self):
        g1 = make_witcher_steam()
        g2 = make_witcher_gog()
        self.db.add_games_batch([g1, g2])

        config = DetectionConfig(threshold=0.70)
        detector = DuplicateDetector(self.db, config)
        groups = detector.detect()
        assert len(groups) == 1

    def test_catches_goty_edition(self):
        g1 = make_witcher_steam()
        g2 = make_witcher_goty()
        self.db.add_games_batch([g1, g2])

        config = DetectionConfig(threshold=0.70)
        detector = DuplicateDetector(self.db, config)
        groups = detector.detect()
        assert len(groups) == 1

    def test_no_false_positives(self):
        """Elden Ring and Half-Life 2 should not be grouped."""
        g1 = make_elden_ring()
        g2 = make_half_life()
        self.db.add_games_batch([g1, g2])

        detector = DuplicateDetector(self.db)
        groups = detector.detect()
        assert len(groups) == 0

    def test_threshold_respected(self):
        g1 = make_game(name="Diablo III")
        g2 = make_game(name="Diablo IV")
        self.db.add_games_batch([g1, g2])

        # High threshold should not match
        config = DetectionConfig(threshold=0.95)
        detector = DuplicateDetector(self.db, config)
        groups = detector.detect()
        assert len(groups) == 0

    def test_exclude_hidden(self):
        g1 = make_game(name="DOOM", hidden=True)
        g2 = make_game(name="DOOM")
        self.db.add_games_batch([g1, g2])

        config = DetectionConfig(filters=DetectionFilter(include_hidden=False))
        detector = DuplicateDetector(self.db, config)
        groups = detector.detect()
        assert len(groups) == 0

    def test_exclude_uninstalled(self):
        g1 = make_game(name="DOOM", is_installed=False)
        g2 = make_game(name="DOOM", is_installed=True)
        self.db.add_games_batch([g1, g2])

        config = DetectionConfig(filters=DetectionFilter(include_uninstalled=False))
        detector = DuplicateDetector(self.db, config)
        groups = detector.detect()
        assert len(groups) == 0

    def test_source_priority_master_selection(self):
        g_steam = make_game(name="DOOM", source_id=STEAM_SOURCE_ID, description="Full desc")
        g_gog = make_game(name="DOOM", source_id=GOG_SOURCE_ID)
        self.db.add_games_batch([g_steam, g_gog])

        config = DetectionConfig(source_priority=["Steam", "GOG"])
        detector = DuplicateDetector(self.db, config)
        groups = detector.detect()
        assert len(groups) == 1
        assert groups[0].master_game_id == g_steam.id

    def test_transitive_grouping(self):
        """If A~B and B~C, all three should be in one group."""
        g1 = make_game(name="The Witcher 3 Wild Hunt")
        g2 = make_game(name="The Witcher III: Wild Hunt")
        g3 = make_game(name="Witcher 3 Wild Hunt GOTY")
        self.db.add_games_batch([g1, g2, g3])

        config = DetectionConfig(threshold=0.65)
        detector = DuplicateDetector(self.db, config)
        groups = detector.detect()
        assert len(groups) == 1
        assert groups[0].size == 3

    def test_check_similarity_mode(self):
        g1 = make_game(name="DOOM Eternal")
        g2 = make_game(name="DOOM")
        g3 = make_game(name="Minecraft")
        self.db.add_games_batch([g1, g2, g3])

        target = make_game(name="DOOM")
        config = DetectionConfig(threshold=0.70)
        detector = DuplicateDetector(self.db, config)
        groups = detector.check_similarity(target)
        # Should find g2 as match (DOOM vs DOOM)
        assert len(groups) >= 1

    def test_name_filter(self):
        g1 = make_game(name="DOOM")
        g2 = make_game(name="DOOM Eternal")
        g3 = make_game(name="Minecraft")
        self.db.add_games_batch([g1, g2, g3])

        config = DetectionConfig(
            threshold=0.70,
            filters=DetectionFilter(name_pattern="DOOM"),
        )
        detector = DuplicateDetector(self.db, config)
        groups = detector.detect()
        # Should only consider DOOM games, not Minecraft
        for group in groups:
            ids = group.all_game_ids
            for gid in ids:
                game = self.db.get_game(gid)
                assert "DOOM" in game.name or "doom" in game.name.lower()

    def test_confidence_scores_present(self):
        g1 = make_game(name="DOOM")
        g2 = make_game(name="DOOM")
        self.db.add_games_batch([g1, g2])

        detector = DuplicateDetector(self.db)
        groups = detector.detect()
        assert len(groups) == 1
        for mid in groups[0].member_game_ids:
            assert mid in groups[0].confidence_scores
            assert 0.0 <= groups[0].confidence_scores[mid] <= 1.0

    def test_bulk_detection(self):
        """Test detection with 100+ games."""
        games = []
        # Create 10 groups of 3 duplicates each using distinct base names
        base_names = [
            "Alpha Centauri", "Battlefield Vietnam", "Crysis Warhead",
            "DOOM Eternal", "Europa Universalis", "Fallout Shelter",
            "Grand Theft Auto", "Hollow Knight", "Icewind Dale",
            "Jupiter Hell",
        ]
        for base_name in base_names:
            for j in range(3):
                variant = base_name if j == 0 else f"The {base_name} Remastered"
                games.append(make_game(name=variant))
        # Add 70 unique games with highly distinct names
        import hashlib
        for i in range(70):
            h = hashlib.md5(str(i).encode()).hexdigest()[:10]
            games.append(make_game(name=f"Xgame {h}"))
        self.db.add_games_batch(games)

        config = DetectionConfig(threshold=0.70)
        detector = DuplicateDetector(self.db, config)
        groups = detector.detect()
        assert len(groups) >= 5  # Should find at least some duplicate groups

    def test_empty_library(self):
        detector = DuplicateDetector(self.db)
        groups = detector.detect()
        assert len(groups) == 0

    def test_single_game(self):
        self.db.add_game(make_game(name="Solo Game"))
        detector = DuplicateDetector(self.db)
        groups = detector.detect()
        assert len(groups) == 0
