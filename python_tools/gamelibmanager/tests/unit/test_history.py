"""Tests for ResolutionHistory."""

import uuid

import pytest
from gamelibmanager.db.database import GameDatabase
from gamelibmanager.duplicates.history import ResolutionHistory
from tests.factories import make_game, make_lookup_tables


class TestResolutionHistory:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.db = GameDatabase(str(tmp_path / "test.db"))
        self.db.open()
        make_lookup_tables(self.db)
        self.history = ResolutionHistory(self.db)
        yield
        self.db.close()

    def test_record_and_retrieve(self):
        master_id = uuid.uuid4()
        dup_ids = [uuid.uuid4(), uuid.uuid4()]
        self.history.record("hide", master_id, dup_ids, {"reason": "test"})

        records = self.history.get_history()
        assert len(records) == 1
        assert records[0].action == "hide"
        assert records[0].master_game_id == master_id
        assert len(records[0].duplicate_game_ids) == 2

    def test_get_last(self):
        self.history.record("hide", uuid.uuid4(), [uuid.uuid4()])
        self.history.record("delete", uuid.uuid4(), [uuid.uuid4()])

        last = self.history.get_last()
        assert last is not None
        assert last.action == "delete"

    def test_undo_hide(self):
        g1 = make_game(name="Master")
        g2 = make_game(name="Dup", hidden=True)
        self.db.add_games_batch([g1, g2])

        self.history.record("hide", g1.id, [g2.id])
        undone = self.history.undo_last()

        assert undone is not None
        assert undone.action == "hide"

        # g2 should be un-hidden
        retrieved = self.db.get_game(g2.id)
        assert retrieved.hidden is False

    def test_undo_empty_history(self):
        result = self.history.undo_last()
        assert result is None

    def test_history_limit(self):
        for _ in range(5):
            self.history.record("hide", uuid.uuid4(), [uuid.uuid4()])
        records = self.history.get_history(limit=3)
        assert len(records) == 3

    def test_history_ordering(self):
        self.history.record("hide", uuid.uuid4(), [uuid.uuid4()])
        self.history.record("delete", uuid.uuid4(), [uuid.uuid4()])
        self.history.record("merge", uuid.uuid4(), [uuid.uuid4()])

        records = self.history.get_history()
        # Most recent first
        assert records[0].action == "merge"
        assert records[1].action == "delete"
        assert records[2].action == "hide"
