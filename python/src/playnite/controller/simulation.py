"""
Controller simulation for headless / automated testing.

ControllerSimulator injects synthetic InputEvents directly into a
ControllerInputHandler without requiring physical hardware.
VibrationController provides a cross-platform rumble API that degrades
gracefully when hardware support is unavailable.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

from .input_handler import ControllerInputHandler, InputEvent
from .mapping import ButtonMapping
from .navigation import NavigationStateMachine

logger = logging.getLogger(__name__)


class ControllerSimulator:
    """
    Generates synthetic controller input for testing purposes.

    Usage::

        sim = ControllerSimulator()
        sim.press_button("BTN_SOUTH")
        sim.release_button("BTN_SOUTH")
        # -- or shorthand --
        sim.tap_button("BTN_SOUTH")
    """

    def __init__(
        self,
        handler: Optional[ControllerInputHandler] = None,
        device_id: str = "simulator:0",
    ):
        self.device_id = device_id
        self._handler = handler if handler is not None else ControllerInputHandler(device_id=device_id)

    @property
    def handler(self) -> ControllerInputHandler:
        return self._handler

    # ------------------------------------------------------------------
    # Basic input injection
    # ------------------------------------------------------------------

    def press_button(self, code: str) -> InputEvent:
        event = InputEvent(device_id=self.device_id, event_type="button", code=code, value=1.0)
        self._handler._dispatch(event)
        return event

    def release_button(self, code: str) -> InputEvent:
        event = InputEvent(device_id=self.device_id, event_type="button", code=code, value=0.0)
        self._handler._dispatch(event)
        return event

    def tap_button(self, code: str, hold_seconds: float = 0.0) -> List[InputEvent]:
        """Press then release a button, optionally holding for *hold_seconds*."""
        events = [self.press_button(code)]
        if hold_seconds > 0:
            time.sleep(hold_seconds)
        events.append(self.release_button(code))
        return events

    def move_axis(self, code: str, value: float) -> InputEvent:
        clamped = max(-1.0, min(1.0, value))
        event = InputEvent(device_id=self.device_id, event_type="axis", code=code, value=clamped)
        self._handler._dispatch(event)
        return event

    # ------------------------------------------------------------------
    # Sequence simulation
    # ------------------------------------------------------------------

    def simulate_sequence(
        self, sequence: List[Tuple[str, str, float]]
    ) -> List[InputEvent]:
        """
        Simulate a sequence of inputs.

        Each tuple is ``(event_type, code, value)``.
        Use ``event_type="delay"`` with ``code`` as a float string to pause.

        Example::

            sim.simulate_sequence([
                ("button", "BTN_SOUTH", 1.0),
                ("delay", "0.1", 0),
                ("button", "BTN_EAST", 1.0),
            ])
        """
        events = []
        for item in sequence:
            etype, code, value = item
            if etype == "delay":
                time.sleep(float(code))
            elif etype == "button":
                events.extend(self.tap_button(code, hold_seconds=0.0))
            elif etype == "axis":
                events.append(self.move_axis(code, value))
        return events

    def simulate_navigation(
        self,
        actions: List[str],
        mapping: ButtonMapping,
        nav_machine: NavigationStateMachine,
    ) -> List[dict]:
        """
        Drive a NavigationStateMachine through a list of abstract actions
        (e.g. ["up", "select"]) by looking up the corresponding button codes
        in *mapping* and simulating the presses, then calling navigate().

        Returns a list of state-transition records.
        """
        # Build reverse map: action → button code
        action_to_button: Dict[str, str] = {}
        for code, action in mapping.get_mapping().get("buttons", {}).items():
            if action not in action_to_button:
                action_to_button[action] = code

        records = []
        for action in actions:
            button = action_to_button.get(action)
            if button:
                self.tap_button(button)
            transitioned = nav_machine.navigate(action)
            records.append(
                {
                    "action": action,
                    "state": nav_machine.state_name,
                    "transitioned": transitioned,
                }
            )
        return records


class VibrationController:
    """
    Cross-platform controller vibration / rumble API.

    On platforms without haptic feedback, the call is logged but does not
    raise an exception — allowing tests to run without hardware.
    """

    def __init__(self, device_id: str = "default"):
        self.device_id = device_id
        self._active = False
        self._stop_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def vibrate(self, intensity: float = 0.5, duration: float = 0.2) -> bool:
        """
        Trigger rumble at *intensity* (0–1) for *duration* seconds.

        Returns True if a hardware backend accepted the request.
        Thread-safe: may be called from any thread.
        """
        intensity = max(0.0, min(1.0, intensity))

        if self._try_evdev(intensity, duration):
            return True

        with self._lock:
            if self._stop_timer is not None:
                self._stop_timer.cancel()
                self._stop_timer = None
            self._active = True
            if duration > 0:
                self._stop_timer = threading.Timer(duration, self._stop)
                self._stop_timer.daemon = True
                self._stop_timer.start()
        return False

    def stop(self) -> None:
        with self._lock:
            if self._stop_timer is not None:
                self._stop_timer.cancel()
                self._stop_timer = None
        self._stop()

    def _stop(self) -> None:
        with self._lock:
            self._active = False

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def _try_evdev(self, intensity: float, duration: float) -> bool:
        """Linux evdev force-feedback (best-effort)."""
        try:
            import evdev  # type: ignore[import]

            for path in evdev.list_devices():
                device = evdev.InputDevice(path)
                caps = device.capabilities(verbose=False)
                if evdev.ecodes.EV_FF in caps:
                    rumble = evdev.ff.Rumble(
                        strong_magnitude=int(intensity * 0xFFFF),
                        weak_magnitude=int(intensity * 0xFFFF),
                    )
                    effect = evdev.ff.Effect(
                        evdev.ecodes.FF_RUMBLE,
                        -1,
                        0,
                        evdev.ff.Trigger(0, 0),
                        evdev.ff.Replay(int(duration * 1000), 0),
                        evdev.ff.EffectType(ff_rumble_effect=rumble),
                    )
                    effect_id = device.upload_effect(effect)
                    device.write(evdev.ecodes.EV_FF, effect_id, 1)
                    return True
        except Exception as e:
            logger.warning("evdev force-feedback unavailable: %s", e)
        return False
