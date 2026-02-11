"""Tests for MergePreview."""

from __future__ import annotations

import json

import pytest

from gamelibmanager.merger.conflict import FieldConflict
from gamelibmanager.merger.preview import MergePreview
from gamelibmanager.models.game import Game
from tests.factories import make_game


class TestMergePreviewToText:
    def test_to_text_basic(self):
        preview = MergePreview()
        text = preview.to_text()
        assert "Merge Preview" in text
        assert "=" * 40 in text
        assert "Games to add:    0" in text
        assert "Games to update: 0" in text
        assert "Games to skip:   0" in text

    def test_to_text_with_add(self):
        games = [make_game(name="Game A"), make_game(name="Game B")]
        preview = MergePreview(games_to_add=games)
        text = preview.to_text()
        assert "New games to add:" in text
        assert "  + Game A" in text
        assert "  + Game B" in text

    def test_to_text_truncation_add(self):
        games = [make_game(name=f"Game {i}") for i in range(25)]
        preview = MergePreview(games_to_add=games)
        text = preview.to_text()
        assert "  + Game 0" in text
        assert "  + Game 19" in text
        assert "  ... and 5 more" in text
        assert "  + Game 20" not in text

    def test_to_text_with_update(self):
        src = make_game(name="Source Game")
        tgt = make_game(name="Target Game")
        conflict = FieldConflict(
            field_name="description",
            source_value="old",
            target_value="new",
        )
        preview = MergePreview(games_to_update=[(src, tgt, [conflict])])
        text = preview.to_text()
        assert "Games to update:" in text
        assert "  ~ Target Game (1 conflicts: description)" in text

    def test_to_text_truncation_update(self):
        updates = []
        for i in range(25):
            src = make_game(name=f"Src {i}")
            tgt = make_game(name=f"Tgt {i}")
            conflict = FieldConflict(
                field_name="description",
                source_value="a",
                target_value="b",
            )
            updates.append((src, tgt, [conflict]))
        preview = MergePreview(games_to_update=updates)
        text = preview.to_text()
        assert "  ~ Tgt 0" in text
        assert "  ~ Tgt 19" in text
        assert "  ... and 5 more" in text
        assert "  ~ Tgt 20" not in text


class TestMergePreviewToJson:
    def test_to_json_basic(self):
        preview = MergePreview()
        data = json.loads(preview.to_json())
        assert data["games_to_add"] == 0
        assert data["games_to_update"] == 0
        assert data["games_to_skip"] == 0
        assert data["total_conflicts"] == 0
        assert data["media_files_to_copy"] == 0
        assert data["add_details"] == []
        assert data["update_details"] == []
        assert data["skip_details"] == []

    def test_to_json_with_updates(self):
        src = make_game(name="Source")
        tgt = make_game(name="Target")
        conflict = FieldConflict(
            field_name="description",
            source_value="old",
            target_value="new",
        )
        preview = MergePreview(
            games_to_update=[(src, tgt, [conflict])],
            total_conflicts=1,
        )
        data = json.loads(preview.to_json())
        assert data["games_to_update"] == 1
        assert len(data["update_details"]) == 1
        detail = data["update_details"][0]
        assert detail["source_id"] == str(src.id)
        assert detail["target_id"] == str(tgt.id)
        assert detail["name"] == "Target"
        assert detail["conflicts"] == 1
        assert detail["conflict_fields"] == ["description"]

    def test_to_json_with_skip_details(self):
        skipped = [make_game(name="Skipped Game")]
        preview = MergePreview(games_to_skip=skipped)
        data = json.loads(preview.to_json())
        assert data["games_to_skip"] == 1
        assert len(data["skip_details"]) == 1
        assert data["skip_details"][0]["id"] == str(skipped[0].id)
        assert data["skip_details"][0]["name"] == "Skipped Game"
