"""Controller manager for detecting and managing game controllers."""

from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Make pygame optional - only needed for actual controller operations
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    pygame = None
    logger.warning("pygame not available - controller features will be disabled")


class Controller:
    """Represents a connected game controller."""

    def __init__(self, joystick_id: int, pygame_joystick):
        self.id = joystick_id
        self.joystick = pygame_joystick
        self.name = pygame_joystick.get_name()
        self.connected_at = datetime.utcnow()
        self.button_states = {}
        self.axis_states = {}

    def get_button_state(self, button_id: int) -> bool:
        """Get current state of a button."""
        try:
            return self.joystick.get_button(button_id)
        except (IndexError, AttributeError):
            # IndexError: button_id out of range
            # AttributeError: joystick not properly initialized
            return False

    def get_axis_value(self, axis_id: int) -> float:
        """Get current value of an axis (-1.0 to 1.0)."""
        try:
            return self.joystick.get_axis(axis_id)
        except (IndexError, AttributeError):
            # IndexError: axis_id out of range
            # AttributeError: joystick not properly initialized
            return 0.0

    def get_hat_value(self, hat_id: int) -> tuple:
        """Get current value of a hat/d-pad."""
        try:
            return self.joystick.get_hat(hat_id)
        except (IndexError, AttributeError):
            # IndexError: hat_id out of range
            # AttributeError: joystick not properly initialized
            return (0, 0)

    def rumble(self, low_frequency: float, high_frequency: float, duration_ms: int):
        """
        Trigger controller rumble/vibration.

        Args:
            low_frequency: Low frequency motor intensity (0.0-1.0)
            high_frequency: High frequency motor intensity (0.0-1.0)
            duration_ms: Duration in milliseconds
        """
        try:
            self.joystick.rumble(low_frequency, high_frequency, duration_ms)
        except AttributeError:
            # Rumble not supported on this controller
            pass

    def stop_rumble(self):
        """Stop controller rumble."""
        try:
            self.joystick.stop_rumble()
        except AttributeError:
            pass

    def to_dict(self) -> Dict[str, Any]:
        """Convert controller info to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'num_buttons': self.joystick.get_numbuttons(),
            'num_axes': self.joystick.get_numaxes(),
            'num_hats': self.joystick.get_numhats(),
            'connected_at': self.connected_at.isoformat()
        }


class ControllerManager:
    """Manages connected controllers."""

    def __init__(self, headless: bool = False):
        """
        Initialize controller manager.

        Args:
            headless: If True, don't initialize pygame (for testing)
        """
        self.headless = headless
        self.controllers: Dict[int, Controller] = {}
        self.initialized = False

        if not headless:
            self._init_pygame()

    def _init_pygame(self):
        """Initialize pygame for controller input."""
        if not PYGAME_AVAILABLE:
            raise ImportError(
                "pygame is required for controller operations. "
                "Install it with: pip install pygame"
            )
        try:
            pygame.init()
            pygame.joystick.init()
            self.initialized = True
            logger.info("pygame initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize pygame: {e}", exc_info=True)
            self.initialized = False

    def detect_controllers(self) -> List[Controller]:
        """
        Detect and initialize connected controllers.

        Returns:
            List of detected controllers
        """
        if not self.initialized:
            return list(self.controllers.values())

        # Check for new controllers
        joystick_count = pygame.joystick.get_count()

        for i in range(joystick_count):
            if i not in self.controllers:
                try:
                    joystick = pygame.joystick.Joystick(i)
                    joystick.init()
                    controller = Controller(i, joystick)
                    self.controllers[i] = controller
                    logger.info(f"Controller connected: {controller.name} (ID: {i})")
                except Exception as e:
                    logger.error(f"Failed to initialize controller {i}: {e}", exc_info=True)

        return list(self.controllers.values())

    def get_controller(self, controller_id: int) -> Optional[Controller]:
        """Get controller by ID."""
        return self.controllers.get(controller_id)

    def get_all_controllers(self) -> List[Controller]:
        """Get all connected controllers."""
        return list(self.controllers.values())

    def disconnect_controller(self, controller_id: int) -> bool:
        """
        Disconnect/remove a controller.

        Args:
            controller_id: ID of controller to disconnect

        Returns:
            True if controller was disconnected
        """
        if controller_id in self.controllers:
            controller = self.controllers[controller_id]
            try:
                controller.joystick.quit()
            except AttributeError:
                # Joystick already disconnected or not properly initialized
                pass
            del self.controllers[controller_id]
            return True
        return False

    def get_controller_count(self) -> int:
        """Get number of connected controllers."""
        return len(self.controllers)

    def has_controllers(self) -> bool:
        """Check if any controllers are connected."""
        return len(self.controllers) > 0

    def rumble_controller(self, controller_id: int, low_freq: float = 0.5,
                          high_freq: float = 0.5, duration_ms: int = 500):
        """
        Trigger rumble on a specific controller.

        Args:
            controller_id: ID of controller
            low_freq: Low frequency motor (0.0-1.0)
            high_freq: High frequency motor (0.0-1.0)
            duration_ms: Duration in milliseconds
        """
        controller = self.get_controller(controller_id)
        if controller:
            controller.rumble(low_freq, high_freq, duration_ms)

    def shutdown(self):
        """Shutdown controller manager and cleanup."""
        for controller_id in list(self.controllers.keys()):
            self.disconnect_controller(controller_id)

        if self.initialized and not self.headless:
            try:
                if pygame:
                    pygame.joystick.quit()
                    pygame.quit()
            except AttributeError:
                # pygame already cleaned up or not properly initialized
                pass
