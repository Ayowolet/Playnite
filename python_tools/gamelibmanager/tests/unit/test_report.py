"""Tests for MergeReport."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from gamelibmanager.merger.report import MergeReport


class TestMergeReportToText:
    def test_to_text_basic(self):
        report = MergeReport()
        text = report.to_text()
        assert "Merge Report" in text
        assert "=" * 40 in text
        assert "Games added:" in text
        assert "Games updated:" in text
        assert "Games skipped:" in text

    def test_to_text_with_errors(self):
        report = MergeReport(errors=["disk full", "permission denied"])
        text = report.to_text()
        assert "Errors:" in text
        assert "  ! disk full" in text
        assert "  ! permission denied" in text

    def test_to_text_with_warnings(self):
        report = MergeReport(warnings=["low space", "duplicate detected"])
        text = report.to_text()
        assert "Warnings:" in text
        assert "  ? low space" in text
        assert "  ? duplicate detected" in text

    def test_to_text_no_timestamp(self):
        report = MergeReport(timestamp=None)
        text = report.to_text()
        assert "Timestamp: N/A" in text

    def test_to_text_with_timestamp(self):
        ts = datetime(2024, 7, 15, 10, 30, 0)
        report = MergeReport(timestamp=ts)
        text = report.to_text()
        assert f"Timestamp: {ts.isoformat()}" in text


class TestMergeReportToJson:
    def test_to_json_with_timestamp(self):
        ts = datetime(2024, 7, 15, 10, 30, 0)
        report = MergeReport(timestamp=ts)
        data = json.loads(report.to_json())
        assert data["timestamp"] == ts.isoformat()

    def test_to_json_without_timestamp(self):
        report = MergeReport(timestamp=None)
        data = json.loads(report.to_json())
        assert data["timestamp"] is None

    def test_to_json_duration_rounded(self):
        report = MergeReport(duration_seconds=1.23456789)
        data = json.loads(report.to_json())
        assert data["duration_seconds"] == 1.235

    def test_to_json_with_errors_and_warnings(self):
        report = MergeReport(
            errors=["err1", "err2"],
            warnings=["warn1"],
        )
        data = json.loads(report.to_json())
        assert data["errors"] == ["err1", "err2"]
        assert data["warnings"] == ["warn1"]
