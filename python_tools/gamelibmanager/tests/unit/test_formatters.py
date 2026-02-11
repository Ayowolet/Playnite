"""Tests for CLI output formatting utilities."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from gamelibmanager.cli.formatters import format_output


class TestFormatOutputJson:
    def test_json_with_dict(self):
        data = {"name": "Test Game", "score": 95}
        result = format_output(data, "json")
        assert json.loads(result) == data
        # Verify pretty-printing (indent=2)
        assert result == json.dumps(data, indent=2)

    def test_json_with_json_string(self):
        original = {"key": "value", "num": 42}
        json_str = json.dumps(original)
        result = format_output(json_str, "json")
        # Should be re-formatted with indent=2
        assert result == json.dumps(original, indent=2)

    def test_json_with_invalid_string(self):
        data = "not valid json at all"
        result = format_output(data, "json")
        assert result == "not valid json at all"

    def test_json_with_datetime(self):
        dt = datetime(2024, 6, 15, 12, 30, 0)
        data = {"timestamp": dt}
        result = format_output(data, "json")
        parsed = json.loads(result)
        assert parsed["timestamp"] == "2024-06-15 12:30:00"


class TestFormatOutputTable:
    def test_table_with_to_table(self):
        class FakeTable:
            def to_table(self):
                return "col1 | col2\n---- | ----\na    | b"

        result = format_output(FakeTable(), "table")
        assert result == "col1 | col2\n---- | ----\na    | b"

    def test_table_fallback_to_text(self):
        class FakeText:
            def to_text(self):
                return "text representation"

        result = format_output(FakeText(), "table")
        assert result == "text representation"

    def test_table_fallback_to_str(self):
        result = format_output(12345, "table")
        assert result == "12345"


class TestFormatOutputText:
    def test_text_with_to_text(self):
        class FakeText:
            def to_text(self):
                return "formatted text output"

        result = format_output(FakeText(), "text")
        assert result == "formatted text output"

    def test_text_fallback_to_str(self):
        result = format_output(["a", "b", "c"], "text")
        assert result == "['a', 'b', 'c']"
