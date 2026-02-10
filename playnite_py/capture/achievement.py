"""
Achievement capture — screenshot on achievement unlock events.

Two detection modes
-------------------
1. **Manual trigger** — call :meth:`AchievementDetector.trigger_capture` from
   your own event handler (e.g. when a game API fires an achievement event).

2. **Template monitoring** — register a PNG crop of the achievement pop-up
   overlay via :meth:`AchievementDetector.register_template`.  A background
   thread captures the screen at a configurable interval and computes
   normalised cross-correlation against each registered template.  When a
   match exceeds ``match_threshold`` a screenshot is saved automatically.

Both modes write a tagged PNG screenshot and a JSON sidecar.

If no display is available (headless server) the template-monitoring loop
silently skips screen captures; manual triggers always work regardless.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

try:
    import numpy as np  # type: ignore[import-untyped]
    _NUMPY_AVAILABLE = True
except ImportError:
    _NUMPY_AVAILABLE = False


@dataclass
class AchievementCapture:
    """Metadata for a single captured achievement event."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    file_path: Path = field(default_factory=Path)
    sidecar_path: Path = field(default_factory=Path)
    game_name: Optional[str] = None
    achievement_name: Optional[str] = None
    captured_at: datetime = field(default_factory=datetime.utcnow)
    detection_method: str = "manual"   # "manual" | "template"
    template_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "file_path": str(self.file_path),
            "game_name": self.game_name,
            "achievement_name": self.achievement_name,
            "captured_at": self.captured_at.isoformat(),
            "detection_method": self.detection_method,
            "template_score": round(self.template_score, 4),
        }


class AchievementDetector:
    """
    Captures screenshots whenever an achievement is unlocked.

    Parameters
    ----------
    output_dir:
        Directory where achievement screenshots are saved.
    match_threshold:
        Correlation threshold (0–1) for template matching; default 0.85.
    """

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        match_threshold: float = 0.85,
    ) -> None:
        self.output_dir = (
            output_dir
            or Path.home() / "Videos" / "PlayniteCaptures" / "achievements"
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.match_threshold = match_threshold

        self._templates: Dict[str, "Image.Image"] = {}  # name → PIL image
        self._templates_lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._callbacks: List[Callable[[AchievementCapture], None]] = []
        self._captures: List[AchievementCapture] = []

    # ------------------------------------------------------------------ #
    # Template registration                                                #
    # ------------------------------------------------------------------ #

    def register_template(self, name: str, template_path: Path) -> None:
        """
        Register an achievement pop-up template for auto-detection.

        ``template_path`` should be a PNG crop of the achievement overlay
        at the exact pixel dimensions it appears on screen (or close to it).
        """
        if not _PIL_AVAILABLE:
            raise RuntimeError(
                "Pillow is required for template matching.  pip install Pillow"
            )
        img = Image.open(str(template_path)).convert("RGB")
        with self._templates_lock:
            self._templates[name] = img

    def on_achievement(
        self, callback: Callable[["AchievementCapture"], None]
    ) -> None:
        """Register a callback invoked whenever an achievement is captured."""
        self._callbacks.append(callback)

    # ------------------------------------------------------------------ #
    # Manual trigger                                                       #
    # ------------------------------------------------------------------ #

    def trigger_capture(
        self,
        game_name: Optional[str] = None,
        achievement_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> "AchievementCapture":
        """
        Manually trigger an achievement screenshot.

        Use this when your code already knows an achievement fired (e.g. from
        a game API webhook or an in-process hook).
        """
        from .screenshot import ScreenshotCapture

        cap_obj = ScreenshotCapture(output_dir=self.output_dir, fmt="png")
        ss = cap_obj.capture(
            game_name=game_name,
            game_id=None,
            add_timestamp_overlay=True,
        )

        result = AchievementCapture(
            file_path=ss.file_path,
            sidecar_path=ss.file_path.with_suffix(".json"),
            game_name=game_name,
            achievement_name=achievement_name,
            detection_method="manual",
        )
        self._write_sidecar(result, tags)
        self._captures.append(result)
        self._fire_callbacks(result)
        return result

    # ------------------------------------------------------------------ #
    # Background monitoring                                                #
    # ------------------------------------------------------------------ #

    def start_monitoring(
        self,
        game_name: Optional[str] = None,
        interval_seconds: float = 2.0,
    ) -> None:
        """
        Start background screen monitoring for achievement pop-ups.

        Captures the screen every ``interval_seconds`` seconds and compares
        the top-right corner against all registered templates.  Silently
        skips if no display or Pillow is unavailable.
        """
        if self._monitor_thread and self._monitor_thread.is_alive():
            return  # Already running

        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(game_name, interval_seconds),
            daemon=True,
            name="achievement-monitor",
        )
        self._monitor_thread.start()

    def stop_monitoring(self) -> None:
        """Stop background monitoring and join the monitor thread."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
            self._monitor_thread = None

    @property
    def is_monitoring(self) -> bool:
        """True if the background monitor thread is running."""
        return bool(self._monitor_thread and self._monitor_thread.is_alive())

    def get_captures(self) -> List["AchievementCapture"]:
        """Return all achievement captures recorded this session."""
        return list(self._captures)

    def status(self) -> Dict[str, Any]:
        with self._templates_lock:
            template_keys = list(self._templates.keys())
        return {
            "monitoring": self.is_monitoring,
            "templates_registered": template_keys,
            "captures_count": len(self._captures),
            "match_threshold": self.match_threshold,
        }

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _monitor_loop(self, game_name: Optional[str], interval: float) -> None:
        if not _PIL_AVAILABLE:
            return  # Cannot compare templates without PIL

        from .screenshot import ScreenshotCapture
        cap_obj = ScreenshotCapture(output_dir=self.output_dir, fmt="png")

        while not self._stop_event.is_set():
            try:
                with self._templates_lock:
                    has_templates = bool(self._templates)
                if has_templates:
                    ss = cap_obj.capture(game_name=game_name)
                    try:
                        screen = Image.open(str(ss.file_path)).convert("RGB")
                    except Exception:
                        self._stop_event.wait(interval)
                        continue

                    matched = False
                    with self._templates_lock:
                        templates_snapshot = dict(self._templates)
                    for tname, template in templates_snapshot.items():
                        score = self._correlate(screen, template)
                        if score >= self.match_threshold:
                            result = AchievementCapture(
                                file_path=ss.file_path,
                                sidecar_path=ss.file_path.with_suffix(".json"),
                                game_name=game_name,
                                achievement_name=tname,
                                detection_method="template",
                                template_score=score,
                            )
                            self._write_sidecar(result)
                            self._captures.append(result)
                            self._fire_callbacks(result)
                            matched = True
                            # Cool-down: avoid re-triggering the same pop-up
                            self._stop_event.wait(interval * 5)
                            break

                    if not matched:
                        # Discard the temp screenshot to avoid clutter
                        try:
                            ss.file_path.unlink(missing_ok=True)
                            ss.file_path.with_suffix(".json").unlink(missing_ok=True)
                        except Exception:
                            log.debug("Could not remove temp screenshot %s", ss.file_path)
            except Exception:
                log.debug("Achievement monitor iteration failed (headless?)", exc_info=True)

            self._stop_event.wait(interval)

    @staticmethod
    def _correlate(screen: "Image.Image", template: "Image.Image") -> float:
        """
        Normalised cross-correlation between the template and the matching
        corner region of the screen (top-right, the most common pop-up spot).

        Returns a score in [0, 1]; requires numpy.
        Falls back to 0.0 if numpy is unavailable.
        """
        if not _NUMPY_AVAILABLE:
            return 0.0
        try:
            tw, th = template.size
            sw, sh = screen.size
            # Crop top-right corner the same size as the template
            region = screen.crop((max(0, sw - tw), 0, sw, min(th, sh)))
            if region.size != template.size:
                region = region.resize(template.size, Image.LANCZOS)

            a = np.array(region, dtype=float).ravel()
            b = np.array(template, dtype=float).ravel()
            if a.std() < 1e-6 or b.std() < 1e-6:
                return 0.0
            corr = float(np.corrcoef(a, b)[0, 1])
            return max(0.0, corr)
        except Exception:
            return 0.0

    def _fire_callbacks(self, capture: "AchievementCapture") -> None:
        for cb in self._callbacks:
            try:
                cb(capture)
            except Exception:
                log.warning("Achievement callback raised an exception", exc_info=True)

    def _write_sidecar(
        self,
        cap: "AchievementCapture",
        tags: Optional[List[str]] = None,
    ) -> None:
        meta = cap.to_dict()
        meta["tags"] = (tags or []) + ["achievement"]
        try:
            cap.sidecar_path.write_text(
                json.dumps(meta, indent=2), encoding="utf-8"
            )
        except Exception:
            log.warning("Failed to write achievement sidecar %s", cap.sidecar_path, exc_info=True)
