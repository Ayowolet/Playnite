"""Unit tests for controller detection, input, mapping, and simulation."""
import pytest

from playnite.controller.detection import ControllerDetector, ControllerInfo
from playnite.controller.input_handler import ControllerInputHandler, InputEvent
from playnite.controller.mapping import ButtonMapping, DEFAULT_MAPPING
from playnite.controller.simulation import ControllerSimulator, VibrationController


class TestControllerDetection:
    def test_scan_returns_list(self):
        detector = ControllerDetector()
        devices = detector.scan()
        assert isinstance(devices, list)

    def test_available_backends_always_has_simulation(self):
        detector = ControllerDetector()
        assert "simulation" in detector.available_backends

    def test_pygame_backend_available(self):
        """pygame is now a base dependency so should always be detected."""
        detector = ControllerDetector()
        assert "pygame" in detector.available_backends

    def test_controller_info_to_dict(self):
        info = ControllerInfo(device_id="test:0", name="Pad", backend="simulation")
        d = info.to_dict()
        assert d["device_id"] == "test:0"
        assert d["name"] == "Pad"
        assert d["backend"] == "simulation"


class TestInputEvent:
    def test_event_to_dict(self):
        event = InputEvent(device_id="sim:0", event_type="button", code="BTN_A", value=1.0)
        d = event.to_dict()
        assert d["device_id"] == "sim:0"
        assert d["event_type"] == "button"
        assert d["code"] == "BTN_A"
        assert d["value"] == 1.0
        assert "timestamp" in d


class TestControllerInputHandler:
    def test_dispatch_calls_button_callback(self):
        handler = ControllerInputHandler()
        received = []
        handler.on_button(received.append)
        event = InputEvent(device_id="sim", event_type="button", code="BTN_X", value=1.0)
        handler._dispatch(event)
        assert len(received) == 1
        assert received[0].code == "BTN_X"

    def test_dispatch_calls_any_callback(self):
        handler = ControllerInputHandler()
        received = []
        handler.on_any(received.append)
        handler._dispatch(InputEvent(device_id="sim", event_type="axis", code="ABS_X", value=0.5))
        assert len(received) == 1

    def test_history_tracks_events(self):
        handler = ControllerInputHandler()
        for i in range(3):
            handler._dispatch(InputEvent(device_id="sim", event_type="button", code=f"BTN_{i}", value=1.0))
        assert len(handler.get_history()) == 3

    def test_clear_history(self):
        handler = ControllerInputHandler()
        handler._dispatch(InputEvent(device_id="sim", event_type="button", code="BTN_0", value=1.0))
        handler.clear_history()
        assert handler.get_history() == []


class TestButtonMapping:
    def test_default_mapping_loads(self):
        m = ButtonMapping()
        assert "buttons" in m.get_mapping()
        assert "axes" in m.get_mapping()

    def test_map_button_press(self):
        m = ButtonMapping()
        event = InputEvent(device_id="sim", event_type="button", code="BTN_SOUTH", value=1.0)
        assert m.map_input(event) == "select"

    def test_map_button_release_returns_none(self):
        m = ButtonMapping()
        event = InputEvent(device_id="sim", event_type="button", code="BTN_SOUTH", value=0.0)
        assert m.map_input(event) is None

    def test_map_axis_positive(self):
        m = ButtonMapping()
        event = InputEvent(device_id="sim", event_type="axis", code="ABS_Y", value=0.8)
        assert m.map_input(event) == "down"

    def test_map_axis_negative(self):
        m = ButtonMapping()
        event = InputEvent(device_id="sim", event_type="axis", code="ABS_Y", value=-0.8)
        assert m.map_input(event) == "up"

    def test_map_axis_dead_zone_returns_none(self):
        m = ButtonMapping()
        event = InputEvent(device_id="sim", event_type="axis", code="ABS_Y", value=0.1)
        assert m.map_input(event) is None

    def test_set_and_get_mapping(self):
        m = ButtonMapping()
        m.set_button("BTN_CUSTOM", "my_action")
        assert m.map_input(InputEvent("s", "button", "BTN_CUSTOM", 1.0)) == "my_action"

    def test_save_load_json(self, tmp_path):
        path = str(tmp_path / "mapping.json")
        m = ButtonMapping()
        m.set_button("BTN_TEST", "test_action")
        m.save_to_file(path)
        loaded = ButtonMapping.load_from_file(path)
        assert loaded.map_input(InputEvent("s", "button", "BTN_TEST", 1.0)) == "test_action"

    def test_save_load_yaml(self, tmp_path):
        path = str(tmp_path / "mapping.yaml")
        m = ButtonMapping()
        m.set_button("BTN_YAML", "yaml_action")
        m.save_to_file(path)
        loaded = ButtonMapping.load_from_file(path)
        assert loaded.map_input(InputEvent("s", "button", "BTN_YAML", 1.0)) == "yaml_action"

    def test_save_load_yaml_with_custom_axis(self, tmp_path):
        path = str(tmp_path / "mapping.yml")
        m = ButtonMapping()
        m.set_axis("ABS_CUSTOM", "left", "right", threshold=0.3)
        m.save_to_file(path)
        loaded = ButtonMapping.load_from_file(path)
        event_right = InputEvent("s", "axis", "ABS_CUSTOM", 0.5)
        assert loaded.map_input(event_right) == "right"


class TestControllerSimulator:
    def test_press_returns_event(self):
        sim = ControllerSimulator()
        e = sim.press_button("BTN_A")
        assert e.value == 1.0
        assert e.code == "BTN_A"

    def test_release_returns_event(self):
        sim = ControllerSimulator()
        e = sim.release_button("BTN_A")
        assert e.value == 0.0

    def test_tap_dispatches_two_events(self):
        sim = ControllerSimulator()
        events = sim.tap_button("BTN_X")
        assert len(events) == 2
        assert events[0].value == 1.0
        assert events[1].value == 0.0

    def test_callbacks_fired_on_simulate(self):
        sim = ControllerSimulator()
        received = []
        sim.handler.on_button(received.append)
        sim.tap_button("BTN_Y")
        assert len(received) == 2  # press + release

    def test_move_axis(self):
        sim = ControllerSimulator()
        received = []
        sim.handler.on_axis(received.append)
        sim.move_axis("ABS_X", 0.75)
        assert len(received) == 1
        assert received[0].value == 0.75

    def test_axis_clamped(self):
        sim = ControllerSimulator()
        e = sim.move_axis("ABS_X", 999)
        assert e.value == 1.0

    def test_simulate_sequence(self):
        sim = ControllerSimulator()
        received = []
        sim.handler.on_any(received.append)
        sim.simulate_sequence([
            ("button", "BTN_A", 1.0),
            ("axis", "ABS_X", 0.5),
        ])
        # 2 button events (press+release) + 1 axis event
        assert len(received) == 3


class TestVibrationController:
    def test_vibrate_does_not_raise(self):
        vib = VibrationController()
        result = vib.vibrate(0.5, 0.01)
        assert isinstance(result, bool)

    def test_is_active_after_vibrate(self):
        vib = VibrationController()
        vib.vibrate(1.0, 10)  # long duration
        assert vib.is_active

    def test_stop_clears_active(self):
        vib = VibrationController()
        vib.vibrate(1.0, 10)
        vib.stop()
        assert not vib.is_active

    def test_vibration_concurrent(self):
        import threading
        vib = VibrationController()
        errors = []

        def _worker():
            try:
                vib.vibrate(0.5, 10)
                _ = vib.is_active
                vib.stop()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
