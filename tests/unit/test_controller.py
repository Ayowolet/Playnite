"""Unit tests for controller system."""

import pytest

from playnite_py.controller import (
    ControllerManager, InputHandler, ControllerSimulator,
    ControllerConfig, ButtonMapping, ControllerEvent, InputType
)
from playnite_py.controller.mapping import StandardButton, NavigationAction


class TestControllerManager:
    """Test controller manager."""

    def test_init_headless(self):
        """Test initializing in headless mode."""
        manager = ControllerManager(headless=True)
        assert manager.headless is True
        assert manager.initialized is False

    def test_get_controller_count(self):
        """Test getting controller count."""
        manager = ControllerManager(headless=True)
        assert manager.get_controller_count() == 0

    def test_has_controllers(self):
        """Test checking for controllers."""
        manager = ControllerManager(headless=True)
        assert manager.has_controllers() is False


class TestInputHandler:
    """Test input handler."""

    def test_init_headless(self):
        """Test initializing in headless mode."""
        handler = InputHandler(headless=True)
        assert handler.headless is True

    def test_register_listener(self):
        """Test registering event listener."""
        handler = InputHandler(headless=True)
        events_received = []

        def callback(event):
            events_received.append(event)

        handler.register_listener(InputType.BUTTON_PRESS, callback)
        assert len(handler.event_listeners[InputType.BUTTON_PRESS]) == 1

    def test_inject_event(self):
        """Test injecting synthetic events."""
        handler = InputHandler(headless=True)
        events_received = []

        def callback(event):
            events_received.append(event)

        handler.register_listener(InputType.BUTTON_PRESS, callback)

        event = ControllerEvent(
            controller_id=0,
            input_type=InputType.BUTTON_PRESS,
            button_id=0
        )
        handler.inject_event(event)

        assert len(events_received) == 1
        assert events_received[0].button_id == 0

    def test_event_history(self):
        """Test event history."""
        handler = InputHandler(headless=True)

        for i in range(5):
            event = ControllerEvent(
                controller_id=0,
                input_type=InputType.BUTTON_PRESS,
                button_id=i
            )
            handler.inject_event(event)

        history = handler.get_event_history()
        assert len(history) == 5

    def test_clear_history(self):
        """Test clearing event history."""
        handler = InputHandler(headless=True)

        event = ControllerEvent(
            controller_id=0,
            input_type=InputType.BUTTON_PRESS,
            button_id=0
        )
        handler.inject_event(event)

        handler.clear_history()
        assert len(handler.get_event_history()) == 0


class TestButtonMapping:
    """Test button mapping."""

    def test_default_xbox_mapping(self):
        """Test default Xbox controller mapping."""
        mapping = ButtonMapping.default_xbox_mapping()
        assert mapping.get_standard_button(0) == StandardButton.A
        assert mapping.get_action(StandardButton.A) == NavigationAction.SELECT

    def test_default_playstation_mapping(self):
        """Test default PlayStation controller mapping."""
        mapping = ButtonMapping.default_playstation_mapping()
        assert mapping.get_standard_button(0) == StandardButton.X

    def test_map_button(self):
        """Test mapping a button."""
        mapping = ButtonMapping()
        mapping.map_button(5, StandardButton.RIGHT_BUMPER)
        assert mapping.get_standard_button(5) == StandardButton.RIGHT_BUMPER

    def test_map_action(self):
        """Test mapping an action."""
        mapping = ButtonMapping()
        mapping.map_action(StandardButton.A, NavigationAction.SELECT)
        assert mapping.get_action(StandardButton.A) == NavigationAction.SELECT

    def test_get_action_from_physical(self):
        """Test getting action from physical button."""
        mapping = ButtonMapping()
        mapping.map_button(0, StandardButton.A)
        mapping.map_action(StandardButton.A, NavigationAction.SELECT)

        action = mapping.get_action_from_physical(0)
        assert action == NavigationAction.SELECT

    def test_to_dict(self):
        """Test converting mapping to dict."""
        mapping = ButtonMapping()
        mapping.map_button(0, StandardButton.A)
        mapping.map_action(StandardButton.A, NavigationAction.SELECT)

        data = mapping.to_dict()
        assert '0' in data['buttons']
        assert 'a' in data['actions']

    def test_from_dict(self):
        """Test creating mapping from dict."""
        data = {
            'buttons': {'0': 'a', '1': 'b'},
            'actions': {'a': 'select', 'b': 'back'}
        }
        mapping = ButtonMapping.from_dict(data)

        assert mapping.get_standard_button(0) == StandardButton.A
        assert mapping.get_action(StandardButton.A) == NavigationAction.SELECT


class TestControllerConfig:
    """Test controller configuration."""

    def test_init(self):
        """Test initialization."""
        config = ControllerConfig()
        assert 'xbox' in config.mappings
        assert 'playstation' in config.mappings

    def test_get_default_mapping(self):
        """Test getting default mapping."""
        config = ControllerConfig()
        mapping = config.get_mapping()
        assert mapping is not None

    def test_add_mapping(self):
        """Test adding a custom mapping."""
        config = ControllerConfig()
        custom_mapping = ButtonMapping()
        config.add_mapping("custom", custom_mapping)
        assert config.get_mapping("custom") is not None

    def test_set_default_mapping(self):
        """Test setting default mapping."""
        config = ControllerConfig()
        config.set_default_mapping("playstation")
        assert config.default_mapping_name == "playstation"


class TestControllerSimulator:
    """Test controller simulator."""

    def test_add_virtual_controller(self):
        """Test adding virtual controller."""
        simulator = ControllerSimulator()
        controller = simulator.add_virtual_controller("Test Controller")
        assert controller.name == "Test Controller"
        assert len(simulator.virtual_controllers) == 1

    def test_simulate_button_press(self):
        """Test simulating button press."""
        simulator = ControllerSimulator()
        simulator.add_virtual_controller()

        simulator.simulate_button_press(0, 5)

        history = simulator.input_handler.get_event_history()
        assert len(history) == 1
        assert history[0].button_id == 5
        assert history[0].input_type == InputType.BUTTON_PRESS

    def test_simulate_button_click(self):
        """Test simulating button click."""
        simulator = ControllerSimulator()
        simulator.add_virtual_controller()

        simulator.simulate_button_click(0, 3)

        history = simulator.input_handler.get_event_history()
        assert len(history) == 2  # Press and release

    def test_simulate_axis_motion(self):
        """Test simulating axis motion."""
        simulator = ControllerSimulator()
        simulator.add_virtual_controller()

        simulator.simulate_axis_motion(0, 0, 0.5)

        history = simulator.input_handler.get_event_history()
        assert len(history) == 1
        assert history[0].axis_value == 0.5

    def test_simulate_dpad(self):
        """Test simulating d-pad."""
        simulator = ControllerSimulator()
        simulator.add_virtual_controller()

        simulator.simulate_dpad_up(0)
        simulator.simulate_dpad_down(0)
        simulator.simulate_dpad_left(0)
        simulator.simulate_dpad_right(0)

        history = simulator.input_handler.get_event_history()
        assert len(history) == 4

    def test_simulate_sequence(self):
        """Test simulating input sequence."""
        simulator = ControllerSimulator()
        simulator.add_virtual_controller()

        sequence = [
            {'type': 'press', 'button': 0},
            {'type': 'release', 'button': 0},
            {'type': 'axis', 'axis': 0, 'value': 1.0}
        ]

        simulator.simulate_sequence(0, sequence)

        history = simulator.input_handler.get_event_history()
        assert len(history) == 3
