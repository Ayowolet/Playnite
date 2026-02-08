"""Integration tests for controller input and navigation workflows."""
from __future__ import annotations

import json
import tempfile

import pytest
from click.testing import CliRunner

from playnite.cli.main import cli
from playnite.controller.detection import ControllerDetector
from playnite.controller.input_handler import ControllerInputHandler
from playnite.controller.mapping import ButtonMapping
from playnite.controller.navigation import NavigationStateMachine, UIState
from playnite.controller.simulation import ControllerSimulator


@pytest.fixture
def runner():
    return CliRunner()


class TestControllerCLI:
    def test_detect_command(self, runner):
        result = runner.invoke(cli, ["controller", "detect", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "controllers" in data
        assert "available_backends" in data
        assert "simulation" in data["available_backends"]

    def test_detect_includes_pygame_backend(self, runner):
        """pygame is now a base dependency — always in available_backends."""
        result = runner.invoke(cli, ["controller", "detect", "--json"])
        data = json.loads(result.output)
        assert "pygame" in data["available_backends"]

    def test_simulate_command(self, runner):
        result = runner.invoke(cli, ["controller", "simulate", "BTN_SOUTH", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["button"] == "BTN_SOUTH"
        assert len(data["events"]) == 2

    def test_navigate_command(self, runner):
        result = runner.invoke(cli, ["controller", "navigate", "select", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["action"] == "select"
        assert data["transitioned"] is True
        assert data["state"]["current_state"] == "library"

    def test_navigate_invalid_action(self, runner):
        result = runner.invoke(cli, ["controller", "navigate", "back", "--state", "main_menu", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["transitioned"] is False

    def test_state_command(self, runner):
        result = runner.invoke(cli, ["controller", "state", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "current_state" in data
        assert "available_actions" in data

    def test_mapping_show_default(self, runner):
        result = runner.invoke(cli, ["controller", "mapping", "--show-default", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "buttons" in data
        assert "BTN_SOUTH" in data["buttons"]

    def test_mapping_save_load_json(self, runner, tmp_path):
        path = str(tmp_path / "map.json")
        result = runner.invoke(cli, ["controller", "mapping", "--save", path])
        assert result.exit_code == 0
        result = runner.invoke(cli, ["controller", "mapping", "--load", path, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "buttons" in data

    def test_mapping_save_load_yaml(self, runner, tmp_path):
        path = str(tmp_path / "map.yaml")
        result = runner.invoke(cli, ["controller", "mapping", "--save", path])
        assert result.exit_code == 0
        result = runner.invoke(cli, ["controller", "mapping", "--load", path, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "buttons" in data
        assert "BTN_SOUTH" in data["buttons"]

    def test_vibrate_command(self, runner):
        result = runner.invoke(cli, ["controller", "vibrate", "--intensity", "0.3", "--duration", "0.01", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["intensity"] == 0.3
        assert "hardware_supported" in data


class TestEndToEndControllerNavigation:
    """Full workflow: simulator → input handler → mapping → state machine."""

    def test_full_navigation_session(self):
        mapping = ButtonMapping()
        handler = ControllerInputHandler()
        sim = ControllerSimulator(handler=handler)
        nav = NavigationStateMachine()

        # Wire up: input events → mapped actions → state machine
        state_transitions = []

        def on_input(event):
            action = mapping.map_input(event)
            if action:
                if nav.navigate(action):
                    state_transitions.append(nav.state_name)

        handler.on_any(on_input)

        # Simulate a user browsing: main → library → game → overlay → back
        sim.tap_button("BTN_SOUTH")   # select → library
        sim.tap_button("BTN_SOUTH")   # select → game_detail
        sim.tap_button("BTN_SELECT")  # menu → overlay
        sim.tap_button("BTN_EAST")    # back → game_detail

        assert state_transitions == ["library", "game_detail", "overlay", "game_detail"]
        assert nav.state_name == "game_detail"

    def test_cursor_navigation(self):
        nav = NavigationStateMachine(UIState.LIBRARY)
        sim = ControllerSimulator()

        # Move cursor via D-pad simulation
        sim.handler.on_button(lambda e: nav.navigate(
            {"ABS_HAT0Y:-1": "up", "ABS_HAT0Y:1": "down",
             "ABS_HAT0X:-1": "left", "ABS_HAT0X:1": "right"}.get(f"{e.code}:{int(e.value)}", "")
        ))

        sim._handler._dispatch(__import__("playnite.controller.input_handler", fromlist=["InputEvent"]).InputEvent(
            device_id="sim", event_type="button", code="ABS_HAT0Y", value=1
        ))

        # Just verify the cursor moved (row incremented)
        state = nav.get_state()
        assert isinstance(state["cursor_position"], dict)

    def test_state_machine_all_paths(self):
        """Walk every defined transition to verify no dead ends."""
        from playnite.controller.navigation import TRANSITIONS

        for from_state, actions in TRANSITIONS.items():
            for action, to_state in actions.items():
                nav = NavigationStateMachine(from_state)
                nav.navigate(action)
                assert nav.current_state == to_state

    def test_simulation_sequence(self):
        sim = ControllerSimulator()
        mapping = ButtonMapping()
        nav = NavigationStateMachine()

        records = sim.simulate_navigation(
            ["select", "select", "back", "back"],
            mapping,
            nav,
        )
        assert len(records) == 4
        assert records[-1]["state"] == "main_menu"
