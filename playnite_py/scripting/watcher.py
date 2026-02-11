"""File system watcher for script hot-reload."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ScriptFileWatcher:
    """Watches the extensions directory for changes and triggers reloads."""

    def __init__(
        self,
        extensions_dir: str,
        reload_callback: Callable[[str], Any],
        scripts_dict_ref: Callable[[], dict[str, Any]],
    ):
        self._extensions_dir = Path(extensions_dir)
        self._reload_callback = reload_callback
        self._scripts_dict_ref = scripts_dict_ref
        self._watcher_running = False
        self._observer: Any = None

    def start(self) -> None:
        """Start watching extensions directory for changes."""
        if self._watcher_running:
            return

        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            watcher = self

            class _Handler(FileSystemEventHandler):
                def __init__(self):
                    self._debounce: dict[str, float] = {}

                def on_modified(self, event):
                    if event.is_directory:
                        return
                    self._handle_change(event.src_path)

                def on_created(self, event):
                    if event.is_directory:
                        return
                    self._handle_change(event.src_path)

                def _handle_change(self, path: str):
                    # Debounce: ignore rapid consecutive events
                    now = time.time()
                    if path in self._debounce and now - self._debounce[path] < 1.0:
                        return
                    self._debounce[path] = now

                    # Determine which script was modified
                    rel = Path(path)
                    try:
                        rel = rel.relative_to(watcher._extensions_dir)
                        script_id = rel.parts[0] if rel.parts else None
                    except ValueError:
                        return

                    scripts = watcher._scripts_dict_ref()
                    if script_id and script_id in scripts:
                        logger.info("Detected change in script '%s', reloading", script_id)
                        try:
                            watcher._reload_callback(script_id)
                        except Exception as e:
                            logger.error("Hot-reload failed for %s: %s", script_id, e)

            observer = Observer()
            observer.schedule(_Handler(), str(self._extensions_dir), recursive=True)
            observer.daemon = True
            observer.start()
            self._observer = observer
            self._watcher_running = True
            logger.info("File watcher started for %s", self._extensions_dir)

        except ImportError:
            logger.warning("watchdog not installed; file watcher unavailable")

    def stop(self) -> None:
        """Stop the file system watcher and release resources."""
        self._watcher_running = False
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=5)
            except Exception as e:
                logger.warning("Error stopping file watcher: %s", e)
            self._observer = None
