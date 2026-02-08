"""Controller input and navigation module."""
from .detection import ControllerDetector, ControllerInfo
from .input_handler import ControllerInputHandler, InputEvent
from .mapping import ButtonMapping, DEFAULT_MAPPING
from .navigation import NavigationStateMachine, UIState, NavigationEvent
from .simulation import ControllerSimulator, VibrationController

__all__ = [
    "ControllerDetector",
    "ControllerInfo",
    "ControllerInputHandler",
    "InputEvent",
    "ButtonMapping",
    "DEFAULT_MAPPING",
    "NavigationStateMachine",
    "UIState",
    "NavigationEvent",
    "ControllerSimulator",
    "VibrationController",
]
