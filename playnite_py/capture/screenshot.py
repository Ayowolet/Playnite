"""
Screenshot capture module.

Backends (in order of preference):
1. mss  — fastest, cross-platform, no display server dependency
2. PIL.ImageGrab — good macOS/Windows support
3. mock/test — returns a blank image for testing

Screenshots are saved with a JSON sidecar file containing game metadata.
"""

from __future__ import annotations

import io
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    import mss
    import mss.tools
    _MSS_AVAILABLE = True
except ImportError:
    _MSS_AVAILABLE = False

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


@dataclass
class ScreenshotResult:
    """Result of a screenshot capture operation."""
    id: str
    file_path: Path
    sidecar_path: Path
    width: int
    height: int
    file_size_bytes: int
    captured_at: datetime
    game_name: Optional[str]
    game_id: Optional[str]
    backend: str
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "file_path": str(self.file_path),
            "width": self.width,
            "height": self.height,
            "file_size_bytes": self.file_size_bytes,
            "captured_at": self.captured_at.isoformat(),
            "game_name": self.game_name,
            "game_id": self.game_id,
            "backend": self.backend,
            "session_id": self.session_id,
        }


class ScreenshotCapture:
    """
    Captures screenshots using the best available backend.

    Usage
    -----
        cap = ScreenshotCapture(output_dir=Path("captures"))
        result = cap.capture(game_name="Hollow Knight", game_id="abc123")
        print(result.file_path)
    """

    BACKENDS = ["mss", "pil", "mock"]

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        fmt: str = "png",
        quality: int = 95,
        backend: Optional[str] = None,
    ) -> None:
        self.output_dir = output_dir or Path.home() / "Pictures" / "PlayniteCaptures"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.fmt = fmt.lower()
        self.quality = quality
        self._backend = backend or self._detect_backend()

    def _detect_backend(self) -> str:
        if _MSS_AVAILABLE:
            return "mss"
        if _PIL_AVAILABLE:
            return "pil"
        return "mock"

    @property
    def backend(self) -> str:
        return self._backend

    def get_available_backends(self) -> list[str]:
        available = []
        if _MSS_AVAILABLE:
            available.append("mss")
        if _PIL_AVAILABLE:
            available.append("pil")
        available.append("mock")
        return available

    # ------------------------------------------------------------------ #
    # Capture                                                              #
    # ------------------------------------------------------------------ #

    def capture(
        self,
        game_name: Optional[str] = None,
        game_id: Optional[str] = None,
        monitor: int = 1,
        region: Optional[Tuple[int, int, int, int]] = None,  # (left, top, width, height)
        add_timestamp_overlay: bool = False,
        session_id: Optional[str] = None,
    ) -> ScreenshotResult:
        """
        Capture a screenshot and save to disk.

        Parameters
        ----------
        game_name:
            Game currently running (for metadata and directory organisation).
        game_id:
            Library game ID.
        monitor:
            Monitor index (1-based, mss convention).
        region:
            Optional crop region (left, top, width, height).
        add_timestamp_overlay:
            Draw capture timestamp in corner of image.
        """
        capture_id = str(uuid.uuid4())
        now = datetime.utcnow()
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp_str}_{capture_id[:8]}.{self.fmt}"
        dest = self.output_dir / filename

        width, height = 0, 0

        if self._backend == "mss" and _MSS_AVAILABLE:
            width, height = self._capture_mss(dest, monitor, region)
        elif self._backend == "pil" and _PIL_AVAILABLE:
            width, height = self._capture_pil(dest, region)
        else:
            width, height = self._capture_mock(dest)

        if add_timestamp_overlay and _PIL_AVAILABLE:
            self._add_timestamp_overlay(dest, now)

        file_size = dest.stat().st_size if dest.exists() else 0
        sidecar = self._write_sidecar(dest, capture_id, game_name, game_id, now, width, height,
                                      session_id=session_id)

        return ScreenshotResult(
            id=capture_id,
            file_path=dest,
            sidecar_path=sidecar,
            width=width,
            height=height,
            file_size_bytes=file_size,
            captured_at=now,
            game_name=game_name,
            game_id=game_id,
            backend=self._backend,
            session_id=session_id,
        )

    # ------------------------------------------------------------------ #
    # Backend implementations                                              #
    # ------------------------------------------------------------------ #

    def _capture_mss(
        self, dest: Path, monitor: int, region: Optional[Tuple[int, int, int, int]]
    ) -> Tuple[int, int]:
        with mss.mss() as sct:
            if region:
                left, top, width, height = region
                mon = {"top": top, "left": left, "width": width, "height": height}
            else:
                monitors = sct.monitors
                if monitor < len(monitors):
                    mon = monitors[monitor]
                else:
                    mon = monitors[0]
                width = mon.get("width", 1920)
                height = mon.get("height", 1080)

            screenshot = sct.grab(mon)
            if self.fmt == "png":
                mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(dest))
            else:
                img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
                img.save(str(dest), quality=self.quality)
            return screenshot.size

    def _capture_pil(
        self, dest: Path, region: Optional[Tuple[int, int, int, int]]
    ) -> Tuple[int, int]:
        from PIL import ImageGrab
        if region:
            left, top, w, h = region
            img = ImageGrab.grab(bbox=(left, top, left + w, top + h))
        else:
            img = ImageGrab.grab()
        width, height = img.size
        if self.fmt == "jpeg" or self.fmt == "jpg":
            img.save(str(dest), "JPEG", quality=self.quality)
        else:
            img.save(str(dest))
        return width, height

    def _capture_mock(self, dest: Path) -> Tuple[int, int]:
        """Create a placeholder 400×225 grey image for testing."""
        if _PIL_AVAILABLE:
            img = Image.new("RGB", (400, 225), color=(50, 50, 60))
            draw = ImageDraw.Draw(img)
            draw.text((10, 100), "Mock Screenshot", fill=(200, 200, 200))
            img.save(str(dest))
            return 400, 225
        else:
            # Write minimal PNG bytes
            dest.write_bytes(self._minimal_png_bytes())
            return 1, 1

    @staticmethod
    def _minimal_png_bytes() -> bytes:
        """1×1 white pixel PNG."""
        return (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00'
            b'\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8'
            b'\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82'
        )

    # ------------------------------------------------------------------ #
    # Annotations                                                          #
    # ------------------------------------------------------------------ #

    def _add_timestamp_overlay(self, path: Path, dt: datetime) -> None:
        if not _PIL_AVAILABLE or not path.exists():
            return
        try:
            img = Image.open(str(path))
            draw = ImageDraw.Draw(img)
            ts = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            draw.text((10, img.height - 25), ts, fill=(255, 255, 255))
            img.save(str(path))
        except Exception:
            pass

    def crop(self, source: Path, dest: Path, region: Tuple[int, int, int, int]) -> Path:
        """
        Crop an existing screenshot.
        region = (left, top, right, bottom) in pixels.
        """
        if not _PIL_AVAILABLE:
            raise RuntimeError("Pillow is required for image cropping")
        img = Image.open(str(source))
        cropped = img.crop(region)
        cropped.save(str(dest))
        return dest

    def annotate(
        self,
        source: Path,
        dest: Path,
        text: str,
        position: Tuple[int, int] = (10, 10),
        color: Tuple[int, int, int] = (255, 255, 255),
    ) -> Path:
        """Add a text annotation to a screenshot."""
        if not _PIL_AVAILABLE:
            raise RuntimeError("Pillow is required for annotations")
        img = Image.open(str(source))
        draw = ImageDraw.Draw(img)
        draw.text(position, text, fill=color)
        img.save(str(dest))
        return dest

    # ------------------------------------------------------------------ #
    # Sidecar metadata                                                     #
    # ------------------------------------------------------------------ #

    def _write_sidecar(
        self,
        image_path: Path,
        capture_id: str,
        game_name: Optional[str],
        game_id: Optional[str],
        captured_at: datetime,
        width: int,
        height: int,
        session_id: Optional[str] = None,
    ) -> Path:
        sidecar = image_path.with_suffix(".json")
        meta: Dict[str, Any] = {
            "id": capture_id,
            "capture_type": "screenshot",
            "game_name": game_name,
            "game_id": game_id,
            "captured_at": captured_at.isoformat(),
            "resolution": f"{width}x{height}",
            "format": self.fmt,
            "backend": self._backend,
        }
        if session_id:
            meta["session_id"] = session_id
        sidecar.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return sidecar
