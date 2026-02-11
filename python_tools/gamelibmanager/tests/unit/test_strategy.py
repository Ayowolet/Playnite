"""Tests for merge strategies."""

import uuid
from datetime import datetime

import pytest
from gamelibmanager.merger.strategy import (
    KeepNewestStrategy, KeepOldestStrategy, KeepSourceStrategy,
    KeepTargetStrategy, MergeAllStrategy, MergeStrategyType, create_strategy,
)
from gamelibmanager.models.game import Game


class TestKeepNewestStrategy:
    def test_prefers_newer_source(self):
        s = KeepNewestStrategy()
        source = Game(name="S", modified=datetime(2024, 6, 1))
        target = Game(name="T", modified=datetime(2024, 1, 1))
        assert s.resolve("description", "src_val", "tgt_val", source, target) == "src_val"

    def test_prefers_newer_target(self):
        s = KeepNewestStrategy()
        source = Game(name="S", modified=datetime(2024, 1, 1))
        target = Game(name="T", modified=datetime(2024, 6, 1))
        assert s.resolve("description", "src_val", "tgt_val", source, target) == "tgt_val"


class TestKeepOldestStrategy:
    def test_prefers_older_source(self):
        s = KeepOldestStrategy()
        source = Game(name="S", modified=datetime(2020, 1, 1))
        target = Game(name="T", modified=datetime(2024, 1, 1))
        assert s.resolve("description", "src_val", "tgt_val", source, target) == "src_val"

    def test_prefers_older_target(self):
        s = KeepOldestStrategy()
        source = Game(name="S", modified=datetime(2024, 1, 1))
        target = Game(name="T", modified=datetime(2020, 1, 1))
        assert s.resolve("description", "src_val", "tgt_val", source, target) == "tgt_val"


class TestKeepSourceStrategy:
    def test_always_returns_source(self):
        s = KeepSourceStrategy()
        source = Game(name="S")
        target = Game(name="T")
        assert s.resolve("description", "src_val", "tgt_val", source, target) == "src_val"


class TestKeepTargetStrategy:
    def test_always_returns_target(self):
        s = KeepTargetStrategy()
        source = Game(name="S")
        target = Game(name="T")
        assert s.resolve("description", "src_val", "tgt_val", source, target) == "tgt_val"


class TestMergeAllStrategy:
    def test_union_lists(self):
        s = MergeAllStrategy()
        source = Game(name="S")
        target = Game(name="T")
        id1, id2, id3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        result = s.resolve("genre_ids", [str(id1), str(id2)], [str(id2), str(id3)], source, target)
        assert len(result) == 3

    def test_prefer_non_empty_source(self):
        s = MergeAllStrategy()
        source = Game(name="S")
        target = Game(name="T")
        assert s.resolve("description", "has value", "", source, target) == "has value"

    def test_prefer_non_empty_target(self):
        s = MergeAllStrategy()
        source = Game(name="S")
        target = Game(name="T")
        assert s.resolve("description", "", "has value", source, target) == "has value"

    def test_both_non_empty_prefers_newest(self):
        s = MergeAllStrategy()
        source = Game(name="S", modified=datetime(2024, 6, 1))
        target = Game(name="T", modified=datetime(2024, 1, 1))
        assert s.resolve("description", "src", "tgt", source, target) == "src"


class TestCreateStrategy:
    def test_creates_all_types(self):
        for st in MergeStrategyType:
            if st == MergeStrategyType.INTERACTIVE:
                strategy = create_strategy(st, prompt_callback=lambda *a: None)
            else:
                strategy = create_strategy(st)
            assert strategy is not None
