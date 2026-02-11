"""Tests for IncrementalMerger."""

import json
import os
import sys
from datetime import datetime

import pytest
from gamelibmanager.db.database import GameDatabase
from gamelibmanager.merger.incremental import IncrementalMerger
from tests.factories import make_game, make_lookup_tables


class TestIncrementalMerger:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.db = GameDatabase(str(tmp_path / "test.db"))
        self.db.open()
        make_lookup_tables(self.db)
        yield
        self.db.close()

    def test_no_previous_merge(self):
        inc = IncrementalMerger(self.db)
        result = inc.get_last_merge_time("source_lib")
        assert result is None

    def test_get_last_merge_time(self):
        self.db.conn.execute(
            "INSERT INTO merge_history (timestamp, source_library, target_library, strategy) "
            "VALUES (?, ?, ?, ?)",
            ("2024-06-01T12:00:00", "source_lib", "target_lib", "merge_all"),
        )
        self.db.conn.commit()

        inc = IncrementalMerger(self.db)
        result = inc.get_last_merge_time("source_lib")
        assert result is not None
        assert result.year == 2024

    def test_get_changed_games(self, tmp_path):
        source_db = GameDatabase(str(tmp_path / "source.db"))
        source_db.open()
        make_lookup_tables(source_db)

        g1 = make_game(name="Old", modified=datetime(2024, 1, 1))
        g2 = make_game(name="New", modified=datetime(2024, 7, 1))
        source_db.add_games_batch([g1, g2])

        inc = IncrementalMerger(self.db)
        changed = inc.get_changed_games(source_db, datetime(2024, 6, 1))

        assert len(changed) == 1
        assert changed[0].name == "New"

        source_db.close()

    @pytest.mark.skipif(sys.platform != "win32", reason="normcase only lowercases on Windows")
    def test_get_last_merge_time_case_insensitive_windows(self):
        """Merge history lookup should match paths regardless of case on Windows."""
        self.db.conn.execute(
            "INSERT INTO merge_history (timestamp, source_library, target_library, strategy) "
            "VALUES (?, ?, ?, ?)",
            ("2024-06-01T12:00:00", "C:\\Games\\Source", "C:\\Games\\Target", "merge_all"),
        )
        self.db.conn.commit()

        inc = IncrementalMerger(self.db)
        # Query with different case — should match on Windows
        result = inc.get_last_merge_time("c:\\games\\source")
        assert result is not None
        assert result.year == 2024

    def test_get_last_merge_time_normcase_applied(self):
        """Verify normcase is applied: path equal after normcase matches."""
        raw_path = "/Games/Source"
        self.db.conn.execute(
            "INSERT INTO merge_history (timestamp, source_library, target_library, strategy) "
            "VALUES (?, ?, ?, ?)",
            ("2024-06-01T12:00:00", raw_path, "/target", "merge_all"),
        )
        self.db.conn.commit()

        inc = IncrementalMerger(self.db)
        result = inc.get_last_merge_time(os.path.normcase(raw_path))
        assert result is not None
        assert result.year == 2024
