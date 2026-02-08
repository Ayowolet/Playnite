"""Controller button mapping and configuration."""

import json
import yaml
from typing import Dict, Any, Optional
from pathlib import Path
from enum import Enum


class StandardButton(Enum):
    """Standard button mappings."""
    A = "a"
    B = "b"
    X = "x"
    Y = "y"
    LEFT_BUMPER = "lb"
    RIGHT_BUMPER = "rb"
    LEFT_TRIGGER = "lt"
    RIGHT_TRIGGER = "rt"
    SELECT = "select"
    START = "start"
    LEFT_STICK_PRESS = "ls_press"
    RIGHT_STICK_PRESS = "rs_press"
    DPAD_UP = "dpad_up"
    DPAD_DOWN = "dpad_down"
    DPAD_LEFT = "dpad_left"
    DPAD_RIGHT = "dpad_right"
    GUIDE = "guide"


class NavigationAction(Enum):
    """Navigation actions for UI."""
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    SELECT = "select"
    BACK = "back"
    MENU = "menu"
    FAVORITE = "favorite"
    FILTER = "filter"
    SEARCH = "search"


class ButtonMapping:
    """Maps physical controller buttons to standard buttons."""

    def __init__(self):
        self.button_map: Dict[int, StandardButton] = {}
        self.action_map: Dict[StandardButton, NavigationAction] = {}

    def map_button(self, physical_button: int, standard_button: StandardButton):
        """Map a physical button to a standard button."""
        self.button_map[physical_button] = standard_button

    def map_action(self, standard_button: StandardButton, action: NavigationAction):
        """Map a standard button to a navigation action."""
        self.action_map[standard_button] = action

    def get_standard_button(self, physical_button: int) -> Optional[StandardButton]:
        """Get standard button for a physical button."""
        return self.button_map.get(physical_button)

    def get_action(self, standard_button: StandardButton) -> Optional[NavigationAction]:
        """Get navigation action for a standard button."""
        return self.action_map.get(standard_button)

    def get_action_from_physical(self, physical_button: int) -> Optional[NavigationAction]:
        """Get navigation action directly from physical button."""
        standard = self.get_standard_button(physical_button)
        if standard:
            return self.get_action(standard)
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert mapping to dictionary."""
        return {
            'buttons': {str(k): v.value for k, v in self.button_map.items()},
            'actions': {k.value: v.value for k, v in self.action_map.items()}
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ButtonMapping':
        """Create mapping from dictionary."""
        mapping = cls()

        if 'buttons' in data:
            for physical, standard in data['buttons'].items():
                try:
                    mapping.map_button(int(physical), StandardButton(standard))
                except (ValueError, KeyError):
                    pass

        if 'actions' in data:
            for standard, action in data['actions'].items():
                try:
                    mapping.map_action(StandardButton(standard), NavigationAction(action))
                except (ValueError, KeyError):
                    pass

        return mapping

    @classmethod
    def default_xbox_mapping(cls) -> 'ButtonMapping':
        """Create default Xbox controller mapping."""
        mapping = cls()

        # Button mappings (Xbox controller standard)
        mapping.map_button(0, StandardButton.A)
        mapping.map_button(1, StandardButton.B)
        mapping.map_button(2, StandardButton.X)
        mapping.map_button(3, StandardButton.Y)
        mapping.map_button(4, StandardButton.LEFT_BUMPER)
        mapping.map_button(5, StandardButton.RIGHT_BUMPER)
        mapping.map_button(6, StandardButton.SELECT)
        mapping.map_button(7, StandardButton.START)
        mapping.map_button(8, StandardButton.LEFT_STICK_PRESS)
        mapping.map_button(9, StandardButton.RIGHT_STICK_PRESS)

        # Action mappings
        mapping.map_action(StandardButton.A, NavigationAction.SELECT)
        mapping.map_action(StandardButton.B, NavigationAction.BACK)
        mapping.map_action(StandardButton.Y, NavigationAction.SEARCH)
        mapping.map_action(StandardButton.X, NavigationAction.FAVORITE)
        mapping.map_action(StandardButton.LEFT_BUMPER, NavigationAction.FILTER)
        mapping.map_action(StandardButton.START, NavigationAction.MENU)

        return mapping

    @classmethod
    def default_playstation_mapping(cls) -> 'ButtonMapping':
        """Create default PlayStation controller mapping."""
        mapping = cls()

        # Button mappings (PS controller)
        mapping.map_button(0, StandardButton.X)
        mapping.map_button(1, StandardButton.A)  # Circle
        mapping.map_button(2, StandardButton.B)  # Square
        mapping.map_button(3, StandardButton.Y)  # Triangle
        mapping.map_button(4, StandardButton.LEFT_BUMPER)
        mapping.map_button(5, StandardButton.RIGHT_BUMPER)
        mapping.map_button(8, StandardButton.SELECT)
        mapping.map_button(9, StandardButton.START)
        mapping.map_button(10, StandardButton.LEFT_STICK_PRESS)
        mapping.map_button(11, StandardButton.RIGHT_STICK_PRESS)

        # Action mappings
        mapping.map_action(StandardButton.X, NavigationAction.SELECT)
        mapping.map_action(StandardButton.A, NavigationAction.BACK)
        mapping.map_action(StandardButton.Y, NavigationAction.SEARCH)
        mapping.map_action(StandardButton.B, NavigationAction.FAVORITE)
        mapping.map_action(StandardButton.LEFT_BUMPER, NavigationAction.FILTER)
        mapping.map_action(StandardButton.START, NavigationAction.MENU)

        return mapping


class ControllerConfig:
    """Controller configuration management."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path
        self.mappings: Dict[str, ButtonMapping] = {}
        self.default_mapping_name = "xbox"

        # Load default mappings
        self.mappings["xbox"] = ButtonMapping.default_xbox_mapping()
        self.mappings["playstation"] = ButtonMapping.default_playstation_mapping()

        if config_path and config_path.exists():
            self.load_from_file(config_path)

    def add_mapping(self, name: str, mapping: ButtonMapping):
        """Add a controller mapping."""
        self.mappings[name] = mapping

    def get_mapping(self, name: Optional[str] = None) -> Optional[ButtonMapping]:
        """Get a controller mapping by name."""
        if name is None:
            name = self.default_mapping_name
        return self.mappings.get(name)

    def set_default_mapping(self, name: str):
        """Set the default mapping."""
        if name in self.mappings:
            self.default_mapping_name = name

    def save_to_file(self, file_path: Path, format: str = 'yaml'):
        """
        Save configuration to file.

        Args:
            file_path: Path to save to
            format: Format ('json' or 'yaml')
        """
        data = {
            'default_mapping': self.default_mapping_name,
            'mappings': {name: mapping.to_dict() for name, mapping in self.mappings.items()}
        }

        file_path.parent.mkdir(parents=True, exist_ok=True)

        if format == 'yaml':
            with open(file_path, 'w') as f:
                yaml.dump(data, f, default_flow_style=False)
        else:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)

    def load_from_file(self, file_path: Path):
        """Load configuration from file."""
        if not file_path.exists():
            return

        with open(file_path, 'r') as f:
            if file_path.suffix in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        if 'default_mapping' in data:
            self.default_mapping_name = data['default_mapping']

        if 'mappings' in data:
            for name, mapping_data in data['mappings'].items():
                self.mappings[name] = ButtonMapping.from_dict(mapping_data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'default_mapping': self.default_mapping_name,
            'mappings': {name: mapping.to_dict() for name, mapping in self.mappings.items()}
        }
