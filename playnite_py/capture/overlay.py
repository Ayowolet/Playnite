"""
Capture overlay — a floating recording-status window.

What this implements
--------------------
A small topmost floating window (using tkinter) that shows the current
capture state: recording (● REC), buffering (● BUF), or idle (● IDLE).

Limitations / known blocker
----------------------------
A *true* transparent game overlay — one that renders directly over a
fullscreen DirectX / Metal / Vulkan context — requires platform-native
compiled components:

- **Windows**: A layered ``HWND`` with ``WS_EX_LAYERED | WS_EX_TRANSPARENT``
  drawn via GDI/Direct2D, or a D3D11 swap-chain hook (as used by Fraps,
  RTSS, etc.).
- **macOS**: A ``CGWindow`` with ``kCGWindowLayerStatusBar`` or a
  ``CATransparentLayer`` rendered over the game window via the CoreGraphics
  compositor.
- **Linux**: An ``_NET_WM_WINDOW_TYPE_NOTIFICATION`` override-redirect X11
  window; on Wayland, a ``layer-shell`` surface.

None of these are available in pure Python without C-extension bindings.

What we provide instead is a borderless, translucent, always-on-top tkinter
window that floats *above* windowed/borderless-windowed games.  It works on
macOS, Windows, and most Linux desktop environments that support compositing.
It is silently disabled in headless environments (no ``$DISPLAY`` /
``$WAYLAND_DISPLAY``).
"""

from __future__ import annotations

import atexit
import os
import sys
import threading
from typing import Any, Dict, Optional

_TKINTER_AVAILABLE = False
try:
    import tkinter as tk  # noqa: F401 — checked at runtime
    _TKINTER_AVAILABLE = True
except Exception:
    pass


class CaptureOverlay:
    """
    Floating recording-status indicator window.

    Displays a colour-coded indicator in a screen corner:

    - ``● REC``  (red)    — video recording is active
    - ``● BUF``  (yellow) — instant replay buffer is active
    - ``● IDLE`` (grey)   — capture system is running but not recording

    The window is borderless, always-on-top, and semi-transparent.
    All methods are no-ops when no display is available.

    Parameters
    ----------
    opacity:
        Window transparency, 0.1 (nearly invisible) to 1.0 (fully opaque).
    position:
        Screen corner: ``"top-left"``, ``"top-right"``,
        ``"bottom-left"``, ``"bottom-right"``.
    """

    _CORNER_OFFSET = 16  # pixels from screen edge

    def __init__(
        self,
        opacity: float = 0.80,
        position: str = "top-right",
    ) -> None:
        self.opacity = max(0.1, min(1.0, opacity))
        self.position = position

        self._root: Any = None          # tk.Tk instance (Any to avoid import)
        self._label: Any = None         # tk.Label
        self._thread: Optional[threading.Thread] = None
        self._visible = False
        self._recording = False
        self._buffering = False
        self._game_name: Optional[str] = None
        self._lock = threading.Lock()
        self._available = _TKINTER_AVAILABLE and self._has_display()
        atexit.register(self._atexit_stop)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def show(self) -> None:
        """
        Display the overlay window.

        Spawns a daemon thread that runs the tkinter event loop.
        No-op if no display is available.
        """
        if not self._available or self._visible:
            return
        self._thread = threading.Thread(
            target=self._run_tk, daemon=True, name="capture-overlay"
        )
        self._thread.start()
        self._visible = True

    def hide(self) -> None:
        """Destroy the overlay window."""
        if not self._visible:
            return
        self._visible = False
        if self._root is not None:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass
        self._root = None

    def set_recording(
        self, recording: bool, game_name: Optional[str] = None
    ) -> None:
        """Update recording state (shown as ● REC in red)."""
        with self._lock:
            self._recording = recording
            if game_name is not None:
                self._game_name = game_name
        self._schedule_refresh()

    def set_buffering(self, buffering: bool) -> None:
        """Update replay-buffer state (shown as ● BUF in yellow)."""
        with self._lock:
            self._buffering = buffering
        self._schedule_refresh()

    @property
    def is_available(self) -> bool:
        """True when a graphical display is reachable."""
        return self._available

    def status(self) -> Dict[str, Any]:
        return {
            "available": self._available,
            "visible": self._visible,
            "recording": self._recording,
            "buffering": self._buffering,
            "game_name": self._game_name,
        }

    # ------------------------------------------------------------------ #
    # Private — tkinter event loop                                         #
    # ------------------------------------------------------------------ #

    def _run_tk(self) -> None:
        try:
            import tkinter as _tk

            root = _tk.Tk()
            self._root = root

            root.overrideredirect(True)        # no title bar / borders
            root.attributes("-topmost", True)  # always on top
            try:
                root.attributes("-alpha", self.opacity)
            except Exception:
                pass  # some WMs don't support alpha

            root.configure(bg="black")
            root.resizable(False, False)

            self._label = _tk.Label(
                root, text="",
                fg="white", bg="black",
                font=("Courier", 11, "bold"),
                padx=8, pady=4,
            )
            self._label.pack()
            self._update_label()
            self._position_window(root)

            def poll() -> None:
                if not self._visible:
                    root.destroy()
                    return
                self._update_label()
                self._position_window(root)
                root.after(500, poll)

            root.after(500, poll)
            root.mainloop()
        except Exception:
            pass  # silently fail on headless / WM errors
        finally:
            self._root = None
            self._visible = False

    def _update_label(self) -> None:
        if self._label is None:
            return
        with self._lock:
            recording = self._recording
            buffering = self._buffering
            game = self._game_name

        if recording:
            text, color = "● REC", "#ff4444"
        elif buffering:
            text, color = "● BUF", "#ffcc00"
        else:
            text, color = "● IDLE", "#888888"

        if game:
            text += f"  {game[:20]}"

        try:
            self._label.config(text=text, fg=color)
        except Exception:
            pass

    def _atexit_stop(self) -> None:
        """Best-effort hide called by atexit handler on abnormal exit."""
        if self._visible:
            try:
                self.hide()
            except Exception:
                pass

    def _schedule_refresh(self) -> None:
        """Thread-safe label refresh via the Tk event queue."""
        if self._root is not None:
            try:
                self._root.after(0, self._update_label)
            except Exception:
                pass

    def _position_window(self, root: Any) -> None:
        try:
            root.update_idletasks()
            w = root.winfo_reqwidth()
            h = root.winfo_reqheight()
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            off = self._CORNER_OFFSET

            if self.position == "top-left":
                x, y = off, off
            elif self.position == "top-right":
                x, y = sw - w - off, off
            elif self.position == "bottom-left":
                x, y = off, sh - h - off
            else:  # bottom-right
                x, y = sw - w - off, sh - h - off

            root.geometry(f"+{x}+{y}")
        except Exception:
            pass

    @staticmethod
    def _has_display() -> bool:
        """Return False when running in a headless environment."""
        if sys.platform in ("darwin", "win32"):
            return True  # macOS / Windows always have a display session
        # Linux / BSD: check for X11 or Wayland
        return bool(
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        )
