"""Output formatting utilities for CLI commands."""

from __future__ import annotations

import json
from typing import Any


def format_output(data: Any, fmt: str) -> str:
    """Format data according to the requested output format."""
    if fmt == "json":
        if isinstance(data, str):
            # Already JSON string
            try:
                parsed = json.loads(data)
                return json.dumps(parsed, indent=2)
            except json.JSONDecodeError:
                return data
        return json.dumps(data, indent=2, default=str)
    if fmt == "table":
        if hasattr(data, "to_table"):
            return data.to_table()
        if hasattr(data, "to_text"):
            return data.to_text()
        return str(data)
    # Default: text
    if hasattr(data, "to_text"):
        return data.to_text()
    return str(data)
