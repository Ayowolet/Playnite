"""Controller detection — enumerates connected game controllers."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class ControllerInfo:
    """Metadata about a connected controller."""

    device_id: str
    name: str
    backend: str
    connected: bool = True

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "backend": self.backend,
            "connected": self.connected,
        }


class ControllerDetector:
    """
    Scans for connected game controllers using whichever backends are
    available in the current environment.

    Priority order: inputs → pygame → (none)
    The simulation backend is always reported as available for testing.
    """

    def __init__(self):
        self._available_backends: List[str] = []
        self._probe_backends()

    def _probe_backends(self) -> None:
        try:
            import inputs  # noqa: F401
            self._available_backends.append("inputs")
        except ImportError:
            pass

        try:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame  # noqa: F401
            self._available_backends.append("pygame")
        except ImportError:
            pass

        # Simulation is always available
        self._available_backends.append("simulation")

    @property
    def available_backends(self) -> List[str]:
        return list(self._available_backends)

    def scan(self) -> List[ControllerInfo]:
        """Return a list of all currently connected controllers."""
        controllers: List[ControllerInfo] = []

        if "inputs" in self._available_backends:
            controllers.extend(self._scan_inputs())

        # Always try pygame regardless of whether inputs found devices
        if "pygame" in self._available_backends:
            seen_names = {c.name for c in controllers}
            for ctrl in self._scan_pygame():
                if ctrl.name not in seen_names:
                    controllers.append(ctrl)

        return controllers

    def is_connected(self, device_id: str) -> bool:
        return any(c.device_id == device_id for c in self.scan())

    # ------------------------------------------------------------------
    # Backend implementations
    # ------------------------------------------------------------------

    def _scan_inputs(self) -> List[ControllerInfo]:
        result = []
        try:
            import inputs

            for i, device in enumerate(inputs.devices.gamepads):
                name = getattr(device, "name", f"Controller {i}")
                result.append(ControllerInfo(device_id=f"inputs:{i}", name=name, backend="inputs"))
        except Exception as e:
            logger.warning("inputs backend scan failed: %s", e)
        return result

    def _scan_pygame(self) -> List[ControllerInfo]:
        result = []
        try:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame

            if not pygame.get_init():
                pygame.init()
            pygame.joystick.init()
            for i in range(pygame.joystick.get_count()):
                j = pygame.joystick.Joystick(i)
                j.init()
                result.append(
                    ControllerInfo(device_id=f"pygame:{i}", name=j.get_name(), backend="pygame")
                )
        except Exception as e:
            logger.warning("pygame backend scan failed: %s", e)
        return result
