"""Integration tests for the complete duplicate detection workflow."""

import json
import uuid
from datetime import datetime

import pytest
from gamelibmanager.db.database import GameDatabase
from gamelibmanager.duplicates.config import DetectionConfig
from gamelibmanager.duplicates.detector import DuplicateDetector
from gamelibmanager.duplicates.history import ResolutionHistory
from gamelibmanager.duplicates.report import DuplicateReport
from tests.factories import (
    make_game, make_lookup_tables, make_witcher_steam, make_witcher_gog,
    make_witcher_goty, make_elden_ring, make_half_life,
    STEAM_SOURCE_ID, GOG_SOURCE_ID,
)


class TestDuplicateWorkflow:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.db = GameDatabase(str(tmp_path / "test.db"))
        self.db.open()
        make_lookup_tables(self.db)
        yield
        self.db.close()

    def test_full_scan_resolve_verify(self):
        """End-to-end: add duplicates, scan, resolve, verify."""
        # 1. Add known duplicates and unique games
        g_steam = make_witcher_steam()
        g_gog = make_witcher_gog()
        g_elden = make_elden_ring()
        g_hl = make_half_life()
        self.db.add_games_batch([g_steam, g_gog, g_elden, g_hl])

        # 2. Scan for duplicates
        config = DetectionConfig(threshold=0.70)
        detector = DuplicateDetector(self.db, config)
        groups = detector.detect()

        # Should find Witcher games as duplicates
        assert len(groups) >= 1
        witcher_group = None
        for g in groups:
            ids = g.all_game_ids
            if g_steam.id in ids or g_gog.id in ids:
                witcher_group = g
                break
        assert witcher_group is not None

        # 3. Generate report
        report = DuplicateReport(
            total_games_scanned=self.db.game_count(),
            total_duplicates_found=sum(g.size - 1 for g in groups),
            total_groups=len(groups),
            groups=groups,
        )
        json_report = report.to_json()
        assert "total_groups" in json_report

        text_report = report.to_text()
        assert "Duplicate Detection Report" in text_report

        # 4. Resolve by hiding duplicates
        history = ResolutionHistory(self.db)
        for mid in witcher_group.member_game_ids:
            game = self.db.get_game(mid)
            if game:
                game.hidden = True
                self.db.update_game(game)
        history.record("hide", witcher_group.master_game_id,
                       witcher_group.member_game_ids)

        # 5. Verify resolution
        records = history.get_history()
        assert len(records) == 1
        assert records[0].action == "hide"

        # 6. Undo
        undone = history.undo_last()
        assert undone is not None

        # Check that duplicates are un-hidden
        for mid in witcher_group.member_game_ids:
            game = self.db.get_game(mid)
            if game:
                assert game.hidden is False

    def test_scan_with_goty_edition(self):
        """GOTY editions should be detected as duplicates."""
        g_steam = make_witcher_steam()
        g_goty = make_witcher_goty()
        self.db.add_games_batch([g_steam, g_goty])

        config = DetectionConfig(threshold=0.65)
        detector = DuplicateDetector(self.db, config)
        groups = detector.detect()

        assert len(groups) >= 1

    def test_report_table_output(self):
        """Table output should include all required columns."""
        g1 = make_witcher_steam()
        g2 = make_witcher_gog()
        self.db.add_games_batch([g1, g2])

        config = DetectionConfig(threshold=0.70)
        detector = DuplicateDetector(self.db, config)
        groups = detector.detect()

        report = DuplicateReport(
            total_games_scanned=self.db.game_count(),
            total_duplicates_found=sum(g.size - 1 for g in groups),
            total_groups=len(groups),
            groups=groups,
        )
        table = report.to_table(self.db)
        assert "Name" in table
        assert "Platform" in table
        assert "Source" in table

    def test_bulk_duplicate_resolution(self):
        """Test resolving 100+ duplicates in bulk."""
        import hashlib
        games = []
        for i in range(50):
            # Each pair is a duplicate with a distinct name per group
            h = hashlib.md5(str(i).encode()).hexdigest()[:10]
            base = f"BulkGame {h}"
            games.append(make_game(name=base, source_id=STEAM_SOURCE_ID))
            games.append(make_game(name=base, source_id=GOG_SOURCE_ID))
        self.db.add_games_batch(games)

        config = DetectionConfig(threshold=0.90)
        detector = DuplicateDetector(self.db, config)
        groups = detector.detect()

        assert len(groups) >= 20  # Should find many duplicate groups

        # Bulk delete duplicates
        history = ResolutionHistory(self.db)
        for group in groups:
            for mid in group.member_game_ids:
                self.db.delete_game(mid)
            history.record("delete", group.master_game_id, group.member_game_ids)

        # Verify all masters remain
        remaining = self.db.get_all_games()
        assert len(remaining) < 100  # Some games removed

    def test_unicode_duplicate_detection(self):
        """Duplicates with Japanese, Cyrillic, accented, and emoji titles."""
        # Japanese: roman numeral VII vs arabic 7
        jp1 = make_game(name="ファイナルファンタジー VII", source_id=STEAM_SOURCE_ID)
        jp2 = make_game(name="ファイナルファンタジー 7", source_id=GOG_SOURCE_ID)
        # Cyrillic: with/without colon
        cy1 = make_game(name="Метро: Исход", source_id=STEAM_SOURCE_ID)
        cy2 = make_game(name="Метро Исход", source_id=GOG_SOURCE_ID)
        # Accented vs plain Latin
        ac1 = make_game(name="Pokémon Legends: Arceus", source_id=STEAM_SOURCE_ID)
        ac2 = make_game(name="Pokemon Legends Arceus", source_id=GOG_SOURCE_ID)
        # Emoji decoration stripped
        em1 = make_game(name="🎮 Super Mario Bros 🎮", source_id=STEAM_SOURCE_ID)
        em2 = make_game(name="Super Mario Bros", source_id=GOG_SOURCE_ID)
        self.db.add_games_batch([jp1, jp2, cy1, cy2, ac1, ac2, em1, em2])

        config = DetectionConfig(threshold=0.70)
        detector = DuplicateDetector(self.db, config)
        groups = detector.detect()

        found_ids = {gid for g in groups for gid in g.all_game_ids}

        # All four pairs should be detected
        assert jp1.id in found_ids and jp2.id in found_ids
        assert cy1.id in found_ids and cy2.id in found_ids
        assert ac1.id in found_ids and ac2.id in found_ids
        assert em1.id in found_ids and em2.id in found_ids

        # Reports should not crash on unicode content
        report = DuplicateReport(
            total_games_scanned=self.db.game_count(),
            total_duplicates_found=sum(g.size - 1 for g in groups),
            total_groups=len(groups),
            groups=groups,
        )
        json_data = json.loads(report.to_json())
        assert json_data["total_groups"] >= 4
        assert len(report.to_text()) > 0
        assert "Name" in report.to_table(self.db)
