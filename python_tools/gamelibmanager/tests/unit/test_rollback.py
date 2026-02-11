"""Tests for RollbackManager."""

import pytest
from gamelibmanager.db.database import GameDatabase
from gamelibmanager.merger.rollback import RollbackManager
from tests.factories import make_game, make_lookup_tables


class TestRollbackManager:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.db = GameDatabase(str(tmp_path / "test.db"))
        self.db.open()
        make_lookup_tables(self.db)

        self.lib_path = tmp_path / "library"
        (self.lib_path / "games").mkdir(parents=True)
        (self.lib_path / "games" / "dummy.json").write_text('{}')

        self.backup_dir = tmp_path / "backups"
        yield
        self.db.close()

    def test_begin_creates_backup(self):
        mgr = RollbackManager(self.db, self.backup_dir, self.lib_path)
        path = mgr.begin_merge()
        assert path.endswith(".zip")

    def test_commit_succeeds(self):
        g = make_game(name="Test")
        self.db.add_game(g)

        mgr = RollbackManager(self.db, self.backup_dir, self.lib_path)
        mgr.begin_merge()

        g2 = make_game(name="New")
        self.db.add_game(g2)

        mgr.commit()
        assert self.db.game_count() == 2

    def test_rollback_restores_state(self):
        g = make_game(name="Original")
        self.db.add_game(g)
        assert self.db.game_count() == 1

        mgr = RollbackManager(self.db, self.backup_dir, self.lib_path)
        mgr.begin_merge()

        g2 = make_game(name="Added During Merge")
        self.db.add_game(g2)
        assert self.db.game_count() == 2

        mgr.rollback_all()
        # After rollback, the added game should be gone
        assert self.db.game_count() == 1

    def test_savepoint_partial_rollback(self):
        mgr = RollbackManager(self.db, self.backup_dir, self.lib_path)
        mgr.begin_merge()

        g1 = make_game(name="Step1")
        self.db.add_game(g1)

        mgr.savepoint("step2")
        g2 = make_game(name="Step2")
        self.db.add_game(g2)
        assert self.db.game_count() == 2

        mgr.rollback_step("step2")
        assert self.db.game_count() == 1

        mgr.commit()
        assert self.db.game_count() == 1
