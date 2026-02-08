"""Input handler for processing controller events."""

from typing import Callable, Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Make pygame optional
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    pygame = None


class InputType(Enum):
    """Types of controller input."""
    BUTTON_PRESS = "button_press"
    BUTTON_RELEASE = "button_release"
    AXIS_MOTION = "axis_motion"
    HAT_MOTION = "hat_motion"


@dataclass
class ControllerEvent:
    """Represents a controller input event."""
    controller_id: int
    input_type: InputType
    button_id: Optional[int] = None
    axis_id: Optional[int] = None
    axis_value: Optional[float] = None
    hat_id: Optional[int] = None
    hat_value: Optional[tuple] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            'controller_id': self.controller_id,
            'input_type': self.input_type.value,
            'button_id': self.button_id,
            'axis_id': self.axis_id,
            'axis_value': self.axis_value,
            'hat_id': self.hat_id,
            'hat_value': self.hat_value,
            'timestamp': self.timestamp.isoformat()
        }


class InputHandler:
    """
    Handles controller input and provides event-based API.

    Can operate in headless mode for testing.
    """

    def __init__(self, headless: bool = False):
        """
        Initialize input handler.

        Args:
            headless: If True, don't process real pygame events (for testing)
        """
        self.headless = headless
        self.event_listeners: Dict[InputType, List[Callable]] = {
            InputType.BUTTON_PRESS: [],
            InputType.BUTTON_RELEASE: [],
            InputType.AXIS_MOTION: [],
            InputType.HAT_MOTION: [],
        }
        self.event_history: List[ControllerEvent] = []
        self.max_history = 100

    def register_listener(self, input_type: InputType, callback: Callable):
        """
        Register a callback for specific input type.

        Args:
            input_type: Type of input to listen for
            callback: Function to call when event occurs (receives ControllerEvent)
        """
        if input_type not in self.event_listeners:
            self.event_listeners[input_type] = []
        self.event_listeners[input_type].append(callback)

    def unregister_listener(self, input_type: InputType, callback: Callable):
        """Unregister a callback."""
        if input_type in self.event_listeners:
            try:
                self.event_listeners[input_type].remove(callback)
            except ValueError:
                pass

    def process_events(self) -> List[ControllerEvent]:
        """
        Process pending controller events.

        Returns:
            List of controller events processed
        """
        if self.headless:
            return []

        events = []
        for pygame_event in pygame.event.get():
            event = self._process_pygame_event(pygame_event)
            if event:
                events.append(event)
                self._dispatch_event(event)
                self._add_to_history(event)

        return events

    def _process_pygame_event(self, pygame_event) -> Optional[ControllerEvent]:
        """Convert pygame event to ControllerEvent."""
        event = None

        if pygame_event.type == pygame.JOYBUTTONDOWN:
            event = ControllerEvent(
                controller_id=pygame_event.joy,
                input_type=InputType.BUTTON_PRESS,
                button_id=pygame_event.button
            )
        elif pygame_event.type == pygame.JOYBUTTONUP:
            event = ControllerEvent(
                controller_id=pygame_event.joy,
                input_type=InputType.BUTTON_RELEASE,
                button_id=pygame_event.button
            )
        elif pygame_event.type == pygame.JOYAXISMOTION:
            event = ControllerEvent(
                controller_id=pygame_event.joy,
                input_type=InputType.AXIS_MOTION,
                axis_id=pygame_event.axis,
                axis_value=pygame_event.value
            )
        elif pygame_event.type == pygame.JOYHATMOTION:
            event = ControllerEvent(
                controller_id=pygame_event.joy,
                input_type=InputType.HAT_MOTION,
                hat_id=pygame_event.hat,
                hat_value=pygame_event.value
            )

        return event

    def _dispatch_event(self, event: ControllerEvent):
        """Dispatch event to registered listeners."""
        listeners = self.event_listeners.get(event.input_type, [])
        for callback in listeners:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Error in event listener: {e}", exc_info=True)

    def _add_to_history(self, event: ControllerEvent):
        """Add event to history."""
        self.event_history.append(event)
        if len(self.event_history) > self.max_history:
            self.event_history.pop(0)

    def get_event_history(self, limit: Optional[int] = None) -> List[ControllerEvent]:
        """
        Get event history.

        Args:
            limit: Maximum number of events to return (most recent)

        Returns:
            List of events
        """
        if limit:
            return self.event_history[-limit:]
        return self.event_history.copy()

    def clear_history(self):
        """Clear event history."""
        self.event_history.clear()

    def inject_event(self, event: ControllerEvent):
        """
        Inject a synthetic event (for testing).

        Args:
            event: Event to inject
        """
        self._dispatch_event(event)
        self._add_to_history(event)

    def wait_for_input(self, timeout_ms: int = 5000) -> Optional[ControllerEvent]:
        """
        Wait for next controller input.

        Args:
            timeout_ms: Timeout in milliseconds

        Returns:
            First controller event or None if timeout
        """
        if self.headless:
            return None

        start_time = pygame.time.get_ticks()
        while pygame.time.get_ticks() - start_time < timeout_ms:
            for pygame_event in pygame.event.get():
                event = self._process_pygame_event(pygame_event)
                if event:
                    self._add_to_history(event)
                    return event
            pygame.time.wait(10)

        return None
