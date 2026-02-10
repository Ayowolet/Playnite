"""Tests for AchievementExporter."""

import json
import csv
import io



class TestExportJSON:
    def test_export_json_string(self, exporter, tracker, sample_game_id, sample_achievements):
        """export_json with no path returns a valid JSON string containing the game."""
        result = exporter.export_json()
        data = json.loads(result)
        assert "exported_at" in data
        assert "games" in data
        assert len(data["games"]) == 1
        assert data["games"][0]["name"] == "Test Game"
        assert len(data["games"][0]["achievements"]) == 5

    def test_export_json_file(self, exporter, tracker, sample_game_id, sample_achievements, tmp_path):
        """export_json with a path writes a valid JSON file to disk."""
        out = tmp_path / "export.json"
        exporter.export_json(output_path=str(out))
        assert out.exists()
        data = json.loads(out.read_text())
        assert len(data["games"]) == 1

    def test_export_json_single_game(self, exporter, tracker, sample_platform_id, sample_game_id, sample_achievements):
        """export_json filtered to a single game_id only includes that game."""
        gid2 = tracker.add_manual_game("TestManual", "Other Game")
        tracker.add_manual_achievement(gid2, name="X", unlocked=False, global_pct=50.0)

        result = exporter.export_json(game_id=sample_game_id)
        data = json.loads(result)
        assert len(data["games"]) == 1
        assert data["games"][0]["name"] == "Test Game"


class TestExportCSV:
    def test_export_csv_string(self, exporter, tracker, sample_game_id, sample_achievements):
        """export_csv with no path returns a non-empty CSV string with a header."""
        result = exporter.export_csv()
        assert len(result) > 0
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 5
        assert "game_name" in reader.fieldnames
        assert "achievement_name" in reader.fieldnames

    def test_export_csv_file(self, exporter, tracker, sample_game_id, sample_achievements, tmp_path):
        """export_csv with a path writes the file to disk."""
        out = tmp_path / "export.csv"
        exporter.export_csv(output_path=str(out))
        assert out.exists()
        content = out.read_text()
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 5

    def test_export_csv_has_all_rows(
        self, exporter, tracker, sample_platform_id, sample_game_id, sample_achievements
    ):
        """CSV export across multiple games includes rows from every game."""
        gid2 = tracker.add_manual_game("TestManual", "Game Two")
        tracker.add_manual_achievement(gid2, name="Extra", unlocked=False, global_pct=50.0)

        result = exporter.export_csv()
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        # 5 from sample game + 1 from Game Two
        assert len(rows) == 6
        game_names = {r["game_name"] for r in rows}
        assert "Test Game" in game_names
        assert "Game Two" in game_names
