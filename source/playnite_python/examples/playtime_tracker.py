"""
Playtime Tracker extension script.

Maintains a detailed playtime log in a CSV file, tracking individual gaming
sessions with start/stop timestamps, duration, and cumulative totals.

Config (playtime_tracker.yaml)
--------------------------------
enabled: true
timeout: 5
sandbox_level: standard
metadata:
  author: Playnite Python Contributors
  version: 1.0
  description: Detailed playtime CSV logger
"""

import csv
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_FILE = Path.home() / ".playnite_python" / "playtime_sessions.csv"
_session_start: dict = {}   # game_id -> start datetime

# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def _ensure_csv():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "session_id", "game_id", "game_name",
                "start_time", "end_time",
                "duration_seconds", "duration_formatted",
            ])


def _fmt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# Lifecycle hooks
# ---------------------------------------------------------------------------

def on_script_loaded():
    _ensure_csv()
    __logger.Info(f"Playtime Tracker active — log: {LOG_FILE}")


def on_game_started(game):
    """Record session start."""
    _session_start[game.id] = datetime.now()
    __logger.Info(f"Session started: {game.name}")


def on_game_stopped(game, elapsed_seconds):
    """Append session record to the CSV log."""
    start = _session_start.pop(game.id, None)
    end = datetime.now()
    if start is None:
        start = end  # fallback

    _ensure_csv()
    session_id = f"{game.id[:8]}-{int(start.timestamp())}"
    try:
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                session_id,
                game.id,
                game.name,
                start.isoformat(timespec="seconds"),
                end.isoformat(timespec="seconds"),
                int(elapsed_seconds),
                _fmt(elapsed_seconds),
            ])
        __logger.Info(
            f"Session logged: {game.name} — {_fmt(elapsed_seconds)}"
        )
    except Exception as exc:
        __logger.Error(f"Failed to write playtime log: {exc}")


# ---------------------------------------------------------------------------
# Menu export — "View Playtime Stats"
# ---------------------------------------------------------------------------

def show_stats():
    """Display summary stats via the notification API."""
    if not LOG_FILE.exists():
        api.notifications.show("No sessions recorded yet.", "info")
        return
    totals: dict = {}
    with open(LOG_FILE, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = row.get("game_name", "Unknown")
            totals[name] = totals.get(name, 0) + int(row.get("duration_seconds", 0))
    if not totals:
        api.notifications.show("No playtime data.", "info")
        return
    top5 = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:5]
    msg = "\n".join(f"{name}: {_fmt(sec)}" for name, sec in top5)
    api.notifications.show(f"Top 5 played games:\n{msg}", "info")


__exports = [
    {"Name": "View Playtime Stats", "Function": "show_stats"},
]
