"""Controller input reading with callback-based event dispatch."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class InputEvent:
    """Represents a single controller input event."""

    device_id: str
    event_type: str  # "button" | "axis"
    code: str  # e.g. "BTN_SOUTH", "ABS_X"
    value: float  # 0/1 for buttons, -1.0..1.0 for axes
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "event_type": self.event_type,
            "code": self.code,
            "value": self.value,
            "timestamp": self.timestamp,
        }


class ControllerInputHandler:
    """
    Reads hardware controller input and dispatches events to registered
    callbacks.  Runs in a background thread; always safe to create even
    when no controller is attached.
    """

    def __init__(self, device_id: Optional[str] = None):
        self.device_id = device_id
        self._callbacks: Dict[str, List[Callable[[InputEvent], None]]] = {
            "button": [],
            "axis": [],
            "any": [],
        }
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._history: List[InputEvent] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_button(self, callback: Callable[[InputEvent], None]) -> None:
        self._callbacks["button"].append(callback)

    def on_axis(self, callback: Callable[[InputEvent], None]) -> None:
        self._callbacks["axis"].append(callback)

    def on_any(self, callback: Callable[[InputEvent], None]) -> None:
        self._callbacks["any"].append(callback)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start background input-reading thread."""
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the background thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # ------------------------------------------------------------------
    # Internal dispatch (also called directly by ControllerSimulator)
    # ------------------------------------------------------------------

    def _dispatch(self, event: InputEvent) -> None:
        with self._lock:
            self._history.append(event)
        for cb in self._callbacks.get(event.event_type, []):
            try:
                cb(event)
            except Exception as e:
                logger.warning("input callback %r raised: %s", cb, e)
        for cb in self._callbacks["any"]:
            try:
                cb(event)
            except Exception as e:
                logger.warning("input callback %r raised: %s", cb, e)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self) -> List[dict]:
        with self._lock:
            return [e.to_dict() for e in self._history]

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    # ------------------------------------------------------------------
    # Background read loop — tries each backend in order
    # ------------------------------------------------------------------

    def _read_loop(self) -> None:
        if self._try_inputs_backend():
            return
        if self._try_pygame_backend():
            return
        # No backend: sit idle so the thread doesn't busy-spin
        while self._running:
            time.sleep(0.1)

    def _try_inputs_backend(self) -> bool:
        try:
            import inputs  # noqa: F401
        except ImportError:
            return False

        try:
            import inputs as _inputs

            while self._running:
                try:
                    for event in _inputs.get_gamepad():
                        if event.ev_type == "Key":
                            self._dispatch(
                                InputEvent(
                                    device_id=self.device_id or "inputs:0",
                                    event_type="button",
                                    code=event.code,
                                    value=float(event.state),
                                )
                            )
                        elif event.ev_type == "Absolute":
                            self._dispatch(
                                InputEvent(
                                    device_id=self.device_id or "inputs:0",
                                    event_type="axis",
                                    code=event.code,
                                    value=float(event.state),
                                )
                            )
                except Exception as e:
                    logger.debug("inputs read error (transient): %s", e)
                    time.sleep(0.1)
        except Exception as e:
            logger.warning("inputs backend loop failed: %s", e)
        return True

    def _try_pygame_backend(self) -> bool:
        try:
            import pygame  # noqa: F401
        except ImportError:
            return False

        try:
            import pygame as _pygame

            if not _pygame.get_init():
                _pygame.init()
            _pygame.joystick.init()

            while self._running:
                for event in _pygame.event.get(
                    [_pygame.JOYBUTTONDOWN, _pygame.JOYBUTTONUP, _pygame.JOYAXISMOTION]
                ):
                    if event.type in (_pygame.JOYBUTTONDOWN, _pygame.JOYBUTTONUP):
                        self._dispatch(
                            InputEvent(
                                device_id=self.device_id or f"pygame:{event.joy}",
                                event_type="button",
                                code=f"BTN_{event.button}",
                                value=1.0 if event.type == _pygame.JOYBUTTONDOWN else 0.0,
                            )
                        )
                    elif event.type == _pygame.JOYAXISMOTION:
                        self._dispatch(
                            InputEvent(
                                device_id=self.device_id or f"pygame:{event.joy}",
                                event_type="axis",
                                code=f"AXIS_{event.axis}",
                                value=float(event.value),
                            )
                        )
                time.sleep(0.01)
        except Exception as e:
            logger.warning("pygame backend loop failed: %s", e)
        return True
