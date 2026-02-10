"""
Global hotkey listener for the capture system.

Binds configurable keyboard shortcuts to screenshot, video recording,
and instant-replay actions.  Runs in a daemon thread so it does not
block the rest of the application.

Hotkey format
-------------
Keys are expressed as pynput key strings, e.g. ``"f12"``, ``"<ctrl>+f12"``,
``"<ctrl>+<shift>+s"``.  The format follows ``pynput.keyboard.GlobalHotKeys``
syntax:

- Single key: ``"f12"``
- Modifier combination: ``"<ctrl>+<shift>+s"``

Fallback behaviour
------------------
If pynput is not installed or a display is unavailable (headless), the
listener silently becomes a no-op.  All methods remain callable and return
gracefully.  This keeps the capture system fully functional via CLI even
without hotkey support.
"""

from __future__ import annotations

import atexit
import logging
import threading
from typing import Any, Callable, Dict, Optional

log = logging.getLogger(__name__)

_PYNPUT_AVAILABLE = False
try:
    from pynput.keyboard import GlobalHotKeys  # type: ignore[import-untyped]
    _PYNPUT_AVAILABLE = True
except Exception:
    pass  # Optional dependency — hotkeys are silently disabled


def _normalise_key(key: str) -> str:
    """
    Convert a simple key name to pynput GlobalHotKeys format.

    Examples
    --------
    ``"f12"``           → ``"<f12>"``  (function keys need angle brackets)
    ``"<ctrl>+f12"``    → ``"<ctrl>+<f12>"``
    ``"<ctrl>+s"``      → ``"<ctrl>+s"``  (unchanged)
    """
    import re
    # Function keys: f1-f24
    key = re.sub(r'(?<![<\w])(f\d{1,2})(?![>\w])', r'<\1>', key, flags=re.IGNORECASE)
    return key.lower()


class HotkeyListener:
    """
    Global hotkey listener for in-game capture shortcuts.

    Binds up to three actions:
    - **screenshot_key** — capture a screenshot immediately
    - **record_key**     — toggle video recording on/off
    - **replay_key**     — save the current replay buffer

    Parameters
    ----------
    on_screenshot:
        Callable invoked when the screenshot hotkey is pressed.
    on_record_toggle:
        Callable invoked when the record hotkey is pressed.
    on_save_replay:
        Callable invoked when the replay-save hotkey is pressed.
    screenshot_key:
        Key string for screenshot (default ``"f12"``).
    record_key:
        Key string for record toggle (default ``"f9"``).
    replay_key:
        Key string for replay save (default ``"f10"``).
    """

    def __init__(
        self,
        on_screenshot: Optional[Callable[[], None]] = None,
        on_record_toggle: Optional[Callable[[], None]] = None,
        on_save_replay: Optional[Callable[[], None]] = None,
        screenshot_key: str = "f12",
        record_key: str = "f9",
        replay_key: str = "f10",
    ) -> None:
        self._on_screenshot = on_screenshot
        self._on_record_toggle = on_record_toggle
        self._on_save_replay = on_save_replay
        self.screenshot_key = screenshot_key
        self.record_key = record_key
        self.replay_key = replay_key

        self._listener: Any = None   # GlobalHotKeys instance
        self._thread: Optional[threading.Thread] = None
        self._running = False
        atexit.register(self._atexit_stop)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def start(self) -> bool:
        """
        Start the global hotkey listener in a background daemon thread.

        Returns
        -------
        bool
            ``True`` if the listener started successfully, ``False`` if
            pynput is unavailable or the listener failed to start.
        """
        if not _PYNPUT_AVAILABLE:
            return False
        if self._running:
            return True

        bindings: Dict[str, Callable] = {}

        def _safe(fn: Optional[Callable[[], None]]) -> Callable[[], None]:
            def _wrapped():
                if fn:
                    try:
                        fn()
                    except Exception:
                        log.warning("Hotkey callback raised an exception", exc_info=True)
            return _wrapped

        if self._on_screenshot:
            bindings[_normalise_key(self.screenshot_key)] = _safe(self._on_screenshot)
        if self._on_record_toggle:
            bindings[_normalise_key(self.record_key)] = _safe(self._on_record_toggle)
        if self._on_save_replay:
            bindings[_normalise_key(self.replay_key)] = _safe(self._on_save_replay)

        if not bindings:
            return False

        try:
            self._listener = GlobalHotKeys(bindings)
            self._thread = threading.Thread(
                target=self._listener.run,
                daemon=True,
                name="hotkey-listener",
            )
            self._thread.start()
            self._running = True
            return True
        except Exception:
            return False

    def stop(self) -> None:
        """Stop the hotkey listener."""
        self._running = False
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                log.debug("Error stopping hotkey listener", exc_info=True)
            self._listener = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    @property
    def is_running(self) -> bool:
        """True if the listener thread is active."""
        return bool(
            self._running
            and self._thread is not None
            and self._thread.is_alive()
        )

    def status(self) -> Dict[str, Any]:
        return {
            "running": self.is_running,
            "pynput_available": _PYNPUT_AVAILABLE,
            "screenshot_key": self.screenshot_key,
            "record_key": self.record_key,
            "replay_key": self.replay_key,
        }

    def _atexit_stop(self) -> None:
        """Best-effort stop invoked by atexit on abnormal interpreter shutdown."""
        if self._running:
            try:
                self.stop()
            except Exception:
                log.debug("atexit stop raised", exc_info=True)

    def update_keys(
        self,
        screenshot_key: Optional[str] = None,
        record_key: Optional[str] = None,
        replay_key: Optional[str] = None,
    ) -> None:
        """
        Change the hotkey bindings.  Restarts the listener if currently active.
        """
        was_running = self.is_running
        if was_running:
            self.stop()
        if screenshot_key is not None:
            self.screenshot_key = screenshot_key
        if record_key is not None:
            self.record_key = record_key
        if replay_key is not None:
            self.replay_key = replay_key
        if was_running:
            self.start()
