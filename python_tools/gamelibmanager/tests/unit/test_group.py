"""Tests for DuplicateGroup."""

import uuid

from gamelibmanager.duplicates.group import DuplicateGroup


class TestDuplicateGroup:
    def test_size(self):
        g = DuplicateGroup(
            group_id=0,
            master_game_id=uuid.uuid4(),
            member_game_ids=[uuid.uuid4(), uuid.uuid4()],
        )
        assert g.size == 3

    def test_size_master_only(self):
        g = DuplicateGroup(group_id=0, master_game_id=uuid.uuid4())
        assert g.size == 1

    def test_all_game_ids(self):
        master = uuid.uuid4()
        m1, m2 = uuid.uuid4(), uuid.uuid4()
        g = DuplicateGroup(
            group_id=0,
            master_game_id=master,
            member_game_ids=[m1, m2],
        )
        all_ids = g.all_game_ids
        assert len(all_ids) == 3
        assert all_ids[0] == master
        assert m1 in all_ids
        assert m2 in all_ids
