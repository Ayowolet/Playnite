"""Controller simulator for testing without physical hardware."""

from typing import Optional, List

from .input_handler import ControllerEvent, InputType, InputHandler


class VirtualController:
    """Virtual controller for testing."""

    def __init__(self, controller_id: int, name: str = "Virtual Controller"):
        self.id = controller_id
        self.name = name
        self.button_states = {}
        self.axis_values = {}

    def press_button(self, button_id: int) -> ControllerEvent:
        """Simulate button press."""
        self.button_states[button_id] = True
        return ControllerEvent(
            controller_id=self.id,
            input_type=InputType.BUTTON_PRESS,
            button_id=button_id
        )

    def release_button(self, button_id: int) -> ControllerEvent:
        """Simulate button release."""
        self.button_states[button_id] = False
        return ControllerEvent(
            controller_id=self.id,
            input_type=InputType.BUTTON_RELEASE,
            button_id=button_id
        )

    def move_axis(self, axis_id: int, value: float) -> ControllerEvent:
        """Simulate axis movement."""
        self.axis_values[axis_id] = value
        return ControllerEvent(
            controller_id=self.id,
            input_type=InputType.AXIS_MOTION,
            axis_id=axis_id,
            axis_value=value
        )

    def move_hat(self, hat_id: int, x: int, y: int) -> ControllerEvent:
        """Simulate hat/d-pad movement."""
        return ControllerEvent(
            controller_id=self.id,
            input_type=InputType.HAT_MOTION,
            hat_id=hat_id,
            hat_value=(x, y)
        )


class ControllerSimulator:
    """
    Simulator for testing controller input without physical hardware.

    Works with InputHandler in headless mode.
    """

    def __init__(self, input_handler: Optional[InputHandler] = None):
        """
        Initialize simulator.

        Args:
            input_handler: InputHandler to inject events into
        """
        self.input_handler = input_handler or InputHandler(headless=True)
        self.virtual_controllers: List[VirtualController] = []

    def add_virtual_controller(self, name: str = "Virtual Controller") -> VirtualController:
        """
        Add a virtual controller.

        Args:
            name: Name for the virtual controller

        Returns:
            Created virtual controller
        """
        controller_id = len(self.virtual_controllers)
        controller = VirtualController(controller_id, name)
        self.virtual_controllers.append(controller)
        return controller

    def get_virtual_controller(self, controller_id: int) -> Optional[VirtualController]:
        """Get virtual controller by ID."""
        if 0 <= controller_id < len(self.virtual_controllers):
            return self.virtual_controllers[controller_id]
        return None

    def simulate_button_press(self, controller_id: int, button_id: int):
        """Simulate a button press on a virtual controller."""
        controller = self.get_virtual_controller(controller_id)
        if controller:
            event = controller.press_button(button_id)
            self.input_handler.inject_event(event)

    def simulate_button_release(self, controller_id: int, button_id: int):
        """Simulate a button release on a virtual controller."""
        controller = self.get_virtual_controller(controller_id)
        if controller:
            event = controller.release_button(button_id)
            self.input_handler.inject_event(event)

    def simulate_button_click(self, controller_id: int, button_id: int):
        """Simulate a button click (press and release)."""
        self.simulate_button_press(controller_id, button_id)
        self.simulate_button_release(controller_id, button_id)

    def simulate_axis_motion(self, controller_id: int, axis_id: int, value: float):
        """Simulate axis motion on a virtual controller."""
        controller = self.get_virtual_controller(controller_id)
        if controller:
            event = controller.move_axis(axis_id, value)
            self.input_handler.inject_event(event)

    def simulate_hat_motion(self, controller_id: int, hat_id: int, x: int, y: int):
        """Simulate hat/d-pad motion on a virtual controller."""
        controller = self.get_virtual_controller(controller_id)
        if controller:
            event = controller.move_hat(hat_id, x, y)
            self.input_handler.inject_event(event)

    def simulate_dpad_up(self, controller_id: int):
        """Simulate d-pad up."""
        self.simulate_hat_motion(controller_id, 0, 0, 1)

    def simulate_dpad_down(self, controller_id: int):
        """Simulate d-pad down."""
        self.simulate_hat_motion(controller_id, 0, 0, -1)

    def simulate_dpad_left(self, controller_id: int):
        """Simulate d-pad left."""
        self.simulate_hat_motion(controller_id, 0, -1, 0)

    def simulate_dpad_right(self, controller_id: int):
        """Simulate d-pad right."""
        self.simulate_hat_motion(controller_id, 0, 1, 0)

    def simulate_sequence(self, controller_id: int, sequence: List[dict]):
        """
        Simulate a sequence of inputs.

        Args:
            controller_id: ID of virtual controller
            sequence: List of input dictionaries with 'type', 'button'/'axis', etc.

        Example:
            [
                {'type': 'press', 'button': 0},
                {'type': 'release', 'button': 0},
                {'type': 'axis', 'axis': 0, 'value': 0.5}
            ]
        """
        for input_spec in sequence:
            input_type = input_spec.get('type')

            if input_type == 'press':
                self.simulate_button_press(controller_id, input_spec['button'])
            elif input_type == 'release':
                self.simulate_button_release(controller_id, input_spec['button'])
            elif input_type == 'click':
                self.simulate_button_click(controller_id, input_spec['button'])
            elif input_type == 'axis':
                self.simulate_axis_motion(
                    controller_id,
                    input_spec['axis'],
                    input_spec['value']
                )
            elif input_type == 'hat':
                self.simulate_hat_motion(
                    controller_id,
                    input_spec.get('hat', 0),
                    input_spec['x'],
                    input_spec['y']
                )
