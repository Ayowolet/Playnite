"""Button mapping configuration — loads/saves JSON or YAML files."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_MAPPING: Dict[str, Any] = {
    "buttons": {
        "BTN_SOUTH": "select",      # A / Cross
        "BTN_EAST": "back",         # B / Circle
        "BTN_NORTH": "details",     # Y / Triangle
        "BTN_WEST": "context",      # X / Square
        "BTN_TL": "page_left",      # LB / L1
        "BTN_TR": "page_right",     # RB / R1
        "BTN_SELECT": "menu",       # Select / Back
        "BTN_START": "start",       # Start / Options
        "BTN_THUMBL": "toggle_view",
        "BTN_THUMBR": "zoom",
        "ABS_HAT0Y:-1": "up",
        "ABS_HAT0Y:1": "down",
        "ABS_HAT0X:-1": "left",
        "ABS_HAT0X:1": "right",
    },
    "axes": {
        "ABS_Y": {"negative": "up", "positive": "down", "threshold": 0.5},
        "ABS_X": {"negative": "left", "positive": "right", "threshold": 0.5},
    },
}


class ButtonMapping:
    """Manages controller button-to-action mappings with JSON/YAML persistence."""

    def __init__(self, mapping: Optional[Dict[str, Any]] = None):
        import copy
        self._mapping: Dict[str, Any] = copy.deepcopy(mapping if mapping is not None else DEFAULT_MAPPING)

    @classmethod
    def load_from_file(cls, path: str) -> "ButtonMapping":
        """Load from a JSON or YAML file."""
        p = Path(path).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Mapping file not found: {p}")
        with open(p) as f:
            if p.suffix in (".yml", ".yaml"):
                try:
                    import yaml
                    data = yaml.safe_load(f)
                except ImportError as exc:
                    raise ImportError("pyyaml is required to load YAML mapping files") from exc
            else:
                data = json.load(f)
        return cls(data)

    def save_to_file(self, path: str) -> None:
        """Save current mapping to JSON or YAML."""
        p = Path(path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            if p.suffix in (".yml", ".yaml"):
                try:
                    import yaml
                    yaml.dump(self._mapping, f, default_flow_style=False)
                except ImportError as exc:
                    raise ImportError("pyyaml is required to save YAML mapping files") from exc
            else:
                json.dump(self._mapping, f, indent=2)

    def map_input(self, event) -> Optional[str]:
        """
        Convert an InputEvent to an action string.

        Returns None if the event does not match any mapping or is a
        button-release (value == 0).
        """
        if event.event_type == "button":
            # Direct button press
            if event.value > 0:
                action = self._mapping.get("buttons", {}).get(event.code)
                if action:
                    return action
            # D-pad encoded as "CODE:VALUE"
            hat_key = f"{event.code}:{int(event.value)}"
            return self._mapping.get("buttons", {}).get(hat_key)

        if event.event_type == "axis":
            axes = self._mapping.get("axes", {})
            config = axes.get(event.code)
            if config:
                threshold = config.get("threshold", 0.5)
                if event.value < -threshold:
                    return config.get("negative")
                if event.value > threshold:
                    return config.get("positive")

        return None

    def set_button(self, code: str, action: str) -> None:
        self._mapping.setdefault("buttons", {})[code] = action

    def set_axis(self, code: str, negative: str, positive: str, threshold: float = 0.5) -> None:
        self._mapping.setdefault("axes", {})[code] = {
            "negative": negative,
            "positive": positive,
            "threshold": threshold,
        }

    def get_mapping(self) -> Dict[str, Any]:
        return dict(self._mapping)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._mapping)
