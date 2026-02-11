"""Tests for ConflictDetector."""

import uuid

import pytest
from gamelibmanager.merger.conflict import ConflictDetector
from gamelibmanager.models.game import Game
from gamelibmanager.models.release_date import ReleaseDate


class TestConflictDetector:
    def setup_method(self):
        self.detector = ConflictDetector()

    def test_identical_games_no_conflicts(self):
        a = Game(name="DOOM", description="Great game")
        b = Game(name="DOOM", description="Great game")
        conflicts = self.detector.detect_conflicts(a, b)
        assert len(conflicts) == 0

    def test_different_description(self):
        a = Game(name="DOOM", description="Version A")
        b = Game(name="DOOM", description="Version B")
        conflicts = self.detector.detect_conflicts(a, b)
        field_names = [c.field_name for c in conflicts]
        assert "description" in field_names

    def test_different_genre_lists(self):
        a = Game(name="Game", genre_ids=[uuid.uuid4()])
        b = Game(name="Game", genre_ids=[uuid.uuid4()])
        conflicts = self.detector.detect_conflicts(a, b)
        field_names = [c.field_name for c in conflicts]
        assert "genre_ids" in field_names

    def test_same_genre_lists_different_order(self):
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        a = Game(name="Game", genre_ids=[id1, id2])
        b = Game(name="Game", genre_ids=[id2, id1])
        conflicts = self.detector.detect_conflicts(a, b)
        field_names = [c.field_name for c in conflicts]
        assert "genre_ids" not in field_names

    def test_both_none_no_conflict(self):
        a = Game(name="Game")
        b = Game(name="Game")
        conflicts = self.detector.detect_conflicts(a, b)
        assert len(conflicts) == 0

    def test_one_none_one_value_is_conflict(self):
        a = Game(name="Game", description="Has desc")
        b = Game(name="Game", description="")
        conflicts = self.detector.detect_conflicts(a, b)
        field_names = [c.field_name for c in conflicts]
        assert "description" in field_names

    def test_different_release_date(self):
        a = Game(name="Game", release_date=ReleaseDate(2020))
        b = Game(name="Game", release_date=ReleaseDate(2021))
        conflicts = self.detector.detect_conflicts(a, b)
        field_names = [c.field_name for c in conflicts]
        assert "release_date" in field_names

    def test_uuid_field_difference(self):
        a = Game(name="Game", source_id=uuid.uuid4())
        b = Game(name="Game", source_id=uuid.uuid4())
        conflicts = self.detector.detect_conflicts(a, b)
        field_names = [c.field_name for c in conflicts]
        assert "source_id" in field_names

    def test_score_difference(self):
        a = Game(name="Game", user_score=85)
        b = Game(name="Game", user_score=90)
        conflicts = self.detector.detect_conflicts(a, b)
        field_names = [c.field_name for c in conflicts]
        assert "user_score" in field_names

    def test_conflict_values_captured(self):
        a = Game(name="Game", description="A desc")
        b = Game(name="Game", description="B desc")
        conflicts = self.detector.detect_conflicts(a, b)
        desc_conflict = [c for c in conflicts if c.field_name == "description"][0]
        assert desc_conflict.source_value == "A desc"
        assert desc_conflict.target_value == "B desc"
