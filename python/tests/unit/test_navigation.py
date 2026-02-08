"""Unit tests for the navigation state machine."""
import pytest

from playnite.controller.navigation import NavigationStateMachine, UIState, TRANSITIONS
from playnite.controller.mapping import ButtonMapping
from playnite.controller.simulation import ControllerSimulator


class TestNavigationStateMachine:
    def test_initial_state(self):
        nav = NavigationStateMachine()
        assert nav.current_state == UIState.MAIN_MENU
        assert nav.state_name == "main_menu"

    def test_valid_transition(self):
        nav = NavigationStateMachine()
        result = nav.navigate("select")
        assert result is True
        assert nav.current_state == UIState.LIBRARY

    def test_invalid_transition_returns_false(self):
        nav = NavigationStateMachine()
        result = nav.navigate("back")  # no "back" from main_menu
        assert result is False
        assert nav.current_state == UIState.MAIN_MENU  # unchanged

    def test_navigation_cursor_moves(self):
        nav = NavigationStateMachine()
        nav.navigate("down")
        assert nav.get_state()["cursor_position"]["row"] == 1
        nav.navigate("right")
        assert nav.get_state()["cursor_position"]["col"] == 1

    def test_cursor_clamped_above_zero(self):
        nav = NavigationStateMachine()
        nav.navigate("up")  # already at 0
        assert nav.get_state()["cursor_position"]["row"] == 0

    def test_state_change_callback(self):
        nav = NavigationStateMachine()
        events = []
        nav.on_state_change(events.append)
        nav.navigate("select")  # -> LIBRARY
        assert len(events) == 1
        assert events[0].to_state == "library"

    def test_history_recorded(self):
        nav = NavigationStateMachine()
        nav.navigate("select")
        nav.navigate("search")
        history = nav.get_history()
        assert len(history) == 2
        assert history[0]["action"] == "select"
        assert history[1]["action"] == "search"

    def test_reset(self):
        nav = NavigationStateMachine()
        nav.navigate("select")
        nav.reset()
        assert nav.current_state == UIState.MAIN_MENU
        assert nav.get_history() == []

    def test_can_navigate(self):
        nav = NavigationStateMachine()
        assert nav.can_navigate("select")
        assert nav.can_navigate("up")  # cursor movement always valid
        assert not nav.can_navigate("back")

    def test_get_state_dict(self):
        nav = NavigationStateMachine()
        state = nav.get_state()
        assert "current_state" in state
        assert "cursor_position" in state
        assert "available_actions" in state
        assert "view_config" in state

    def test_full_navigation_path(self):
        nav = NavigationStateMachine()
        path = ["select", "select", "back", "back"]
        expected = ["library", "game_detail", "library", "main_menu"]
        for action, exp_state in zip(path, expected):
            nav.navigate(action)
            assert nav.state_name == exp_state

    def test_set_view_config(self):
        nav = NavigationStateMachine()
        nav.set_view_config(fullscreen_mode=True, grid_size="large")
        cfg = nav.get_view_config()
        assert cfg["fullscreen_mode"] is True
        assert cfg["grid_size"] == "large"

    def test_custom_initial_state(self):
        nav = NavigationStateMachine(UIState.LIBRARY)
        assert nav.state_name == "library"


class TestSimulationNavigation:
    def test_simulate_navigation_workflow(self):
        """Simulate a controller-driven navigation session end-to-end."""
        mapping = ButtonMapping()
        sim = ControllerSimulator()
        nav = NavigationStateMachine()

        records = sim.simulate_navigation(
            ["select", "search", "back", "select"],
            mapping,
            nav,
        )

        states = [r["state"] for r in records]
        assert states == ["library", "search", "library", "game_detail"]

    def test_navigate_via_button_press(self):
        """Pressing BTN_SOUTH (mapped to 'select') should drive the state machine."""
        mapping = ButtonMapping()
        nav = NavigationStateMachine()
        handler_events = []
        sim = ControllerSimulator()
        sim.handler.on_button(lambda e: handler_events.append(mapping.map_input(e)))

        sim.tap_button("BTN_SOUTH")  # select
        actions = [a for a in handler_events if a]
        assert "select" in actions
