"""Keyboard hotkey listener for capture triggers."""
from typing import Callable, Optional
from loguru import logger

try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    logger.warning("pynput not available, hotkey support disabled")


class HotkeyListener:
    """
    Listens for keyboard hotkeys to trigger captures.

    Uses pynput to monitor keyboard events in the background.
    """

    def __init__(self, hotkey: str, callback: Callable):
        """
        Initialize hotkey listener.

        Args:
            hotkey: Hotkey string (e.g., 'f8', 'ctrl+shift+s')
            callback: Function to call when hotkey is pressed
        """
        self.hotkey = hotkey.lower()
        self.callback = callback
        self.listener = None
        self.active = False

        if not PYNPUT_AVAILABLE:
            logger.error("pynput not available, hotkey will not work")

    def start(self):
        """Start listening for hotkey."""
        if not PYNPUT_AVAILABLE:
            logger.warning("Cannot start hotkey listener: pynput not available")
            return

        if self.active:
            logger.warning("Hotkey listener already active")
            return

        try:
            # Parse hotkey
            self.hotkey_set = self._parse_hotkey(self.hotkey)

            # Start keyboard listener
            self.listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release
            )
            self.listener.start()
            self.active = True

            logger.info(f"Hotkey listener started for: {self.hotkey}")

        except Exception as e:
            logger.error(f"Failed to start hotkey listener: {e}")

    def stop(self):
        """Stop listening for hotkey."""
        if not self.active:
            return

        try:
            if self.listener:
                self.listener.stop()
                self.listener = None

            self.active = False
            logger.info(f"Hotkey listener stopped for: {self.hotkey}")

        except Exception as e:
            logger.error(f"Failed to stop hotkey listener: {e}")

    def _parse_hotkey(self, hotkey: str) -> set:
        """
        Parse hotkey string into set of keys.

        Args:
            hotkey: Hotkey string (e.g., 'f8', 'ctrl+shift+s')

        Returns:
            Set of key identifiers
        """
        parts = hotkey.split('+')
        keys = set()

        for part in parts:
            part = part.strip().lower()

            # Map common key names
            key_mapping = {
                'ctrl': keyboard.Key.ctrl,
                'control': keyboard.Key.ctrl,
                'shift': keyboard.Key.shift,
                'alt': keyboard.Key.alt,
                'cmd': keyboard.Key.cmd,
                'win': keyboard.Key.cmd,
            }

            if part in key_mapping:
                keys.add(key_mapping[part])
            else:
                # Single character or function key
                if part.startswith('f') and len(part) <= 3 and part[1:].isdigit():
                    # Function key (f1-f12)
                    keys.add(part)
                else:
                    # Regular character key
                    keys.add(part)

        return keys

    def _on_press(self, key):
        """Handle key press event."""
        try:
            # Get key identifier
            if hasattr(key, 'char') and key.char:
                key_id = key.char.lower()
            elif hasattr(key, 'name'):
                key_id = key.name.lower()
            else:
                key_id = str(key).lower()

            # Check if this matches our hotkey
            if key_id in self.hotkey_set or key in self.hotkey_set:
                # For simple single-key hotkeys
                if len(self.hotkey_set) == 1:
                    logger.debug(f"Hotkey triggered: {self.hotkey}")
                    self.callback()

        except AttributeError:
            pass

    def _on_release(self, key):
        """Handle key release event."""
        # Could implement modifier key handling here for complex hotkeys
        pass


class MultiHotkeyListener:
    """
    Manages multiple hotkey listeners.

    Useful for handling multiple capture actions (screenshot, video, etc.)
    """

    def __init__(self):
        self.listeners = {}

    def add_hotkey(self, name: str, hotkey: str, callback: Callable):
        """
        Add a new hotkey listener.

        Args:
            name: Identifier for this hotkey
            hotkey: Hotkey string
            callback: Function to call when triggered
        """
        if name in self.listeners:
            logger.warning(f"Hotkey {name} already exists, replacing")
            self.remove_hotkey(name)

        listener = HotkeyListener(hotkey, callback)
        listener.start()
        self.listeners[name] = listener

        logger.info(f"Added hotkey '{name}': {hotkey}")

    def remove_hotkey(self, name: str):
        """
        Remove a hotkey listener.

        Args:
            name: Identifier of hotkey to remove
        """
        if name in self.listeners:
            self.listeners[name].stop()
            del self.listeners[name]
            logger.info(f"Removed hotkey: {name}")

    def stop_all(self):
        """Stop all hotkey listeners."""
        for name in list(self.listeners.keys()):
            self.remove_hotkey(name)

        logger.info("All hotkey listeners stopped")
