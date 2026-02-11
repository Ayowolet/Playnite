"""
Plain-text and Rich-based report helpers.
All functions return plain strings so they can be used both in Rich-rendered
CLI output and as plain-text file content.
"""
from __future__ import annotations

from typing import Any


def format_table(headers: list[str], rows: list[list[Any]], col_widths: list[int] | None = None) -> str:
    """
    Return a plain-text fixed-width table.

    If *col_widths* is not supplied the width of each column is derived from
    the widest cell in that column (header included).
    """
    if not rows and not headers:
        return ""

    str_rows = [[str(cell) for cell in row] for row in rows]
    all_rows = [headers] + str_rows

    if col_widths is None:
        col_widths = [max(len(r[i]) for r in all_rows if i < len(r)) for i in range(len(headers))]

    def fmt_row(row: list[str]) -> str:
        cells = [str(row[i]).ljust(col_widths[i]) if i < len(row) else " " * col_widths[i] for i in range(len(headers))]
        return "  ".join(cells)

    separator = "  ".join("-" * w for w in col_widths)
    lines = [fmt_row(headers), separator]
    lines += [fmt_row(row) for row in str_rows]
    return "\n".join(lines)


def generate_report(title: str, sections: dict[str, Any]) -> str:
    """
    Generate a structured plain-text report.

    *sections* is an ordered dict mapping section heading → content.
    Content may be:
    - str  → rendered as a paragraph
    - list → rendered as a bullet list
    - dict → rendered as key: value pairs
    """
    lines: list[str] = []
    border = "=" * 72
    lines.append(border)
    lines.append(f"  {title}")
    lines.append(border)

    for heading, content in sections.items():
        lines.append("")
        lines.append(f"  {heading}")
        lines.append("  " + "-" * (len(heading) + 2))
        if isinstance(content, str):
            lines.append(f"  {content}")
        elif isinstance(content, list):
            for item in content:
                lines.append(f"    • {item}")
        elif isinstance(content, dict):
            for k, v in content.items():
                lines.append(f"    {k}: {v}")
        else:
            lines.append(f"  {content}")

    lines.append("")
    lines.append(border)
    return "\n".join(lines)
