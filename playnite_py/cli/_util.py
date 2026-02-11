"""Shared utilities for CLI command handlers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _default_data_dir() -> str:
    """Return the default data directory, respecting PLAYNITE_DATA_DIR."""
    return os.environ.get(
        "PLAYNITE_DATA_DIR",
        str(Path.home() / ".playnite_py"),
    )


def _output(data: Any, json_mode: bool) -> None:
    """Print *data* in human-readable or JSON format."""
    if json_mode:
        print(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, dict):
            for key, value in data.items():
                print(f"  {key}: {value}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    summary = item.get("name") or item.get("id") or str(item)
                    print(f"  - {summary}")
                else:
                    print(f"  - {item}")
        else:
            print(data)


def _bool_arg(v: str) -> bool:
    """Parse a boolean CLI argument string."""
    return v.lower() in ("true", "1", "yes")


def _build_app(data_dir: str):
    """Build and return the core application objects (database, engine, action manager)."""
    from playnite_py.models.database import GameDatabase
    from playnite_py.scripting.engine import ScriptEngine
    from playnite_py.actions.manager import ActionManager

    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "library.json")
    ext_dir = os.path.join(data_dir, "extensions")
    log_dir = os.path.join(data_dir, "logs")
    venvs_dir = os.path.join(data_dir, "venvs")

    db = GameDatabase(path=db_path)
    engine = ScriptEngine(
        extensions_dir=ext_dir,
        database=db,
        data_dir=data_dir,
        log_dir=log_dir,
        venvs_dir=venvs_dir,
    )
    action_mgr = ActionManager(db)
    return db, engine, action_mgr
