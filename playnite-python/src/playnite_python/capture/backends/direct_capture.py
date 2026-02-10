"""Direct screen capture backend using mss and opencv."""
import asyncio
from pathlib import Path
from typing import Optional
import numpy as np
from PIL import Image
from loguru import logger

try:
    import mss
    import cv2
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False
    logger.warning("mss or cv2 not available, direct capture backend disabled")

from .base import CaptureBackend


class DirectCaptureBackend(CaptureBackend):
    """
    Direct screen capture using mss (screenshots) and OpenCV (video).

    Fast and lightweight, but captures the entire screen rather than
    specific game windows.
    """

    def __init__(self):
        self.sct = None
        self.recording = False
        self.video_writer = None
        self.video_path = None
        self.record_task = None
        self.monitor_index = 1  # Primary monitor

    async def initialize(self, game_name: str, process_id: int) -> bool:
        """Initialize direct capture."""
        if not MSS_AVAILABLE:
            logger.error("mss/cv2 not available")
            return False

        try:
            self.sct = mss.mss()
            logger.info(f"Direct capture initialized for {game_name} (PID: {process_id})")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize direct capture: {e}")
            return False

    async def capture_screenshot(self, output_path: Path) -> bool:
        """Capture screenshot using mss."""
        if not self.sct:
            logger.error("Capture backend not initialized")
            return False

        try:
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Capture primary monitor
            monitor = self.sct.monitors[self.monitor_index]
            screenshot = self.sct.grab(monitor)

            # Convert to PIL Image and save
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            img.save(output_path, "PNG", optimize=True)

            logger.info(f"Screenshot saved: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Screenshot capture failed: {e}")
            return False

    async def start_recording(self, output_path: Path, quality: str = "high") -> bool:
        """Start video recording."""
        if not self.sct:
            logger.error("Capture backend not initialized")
            return False

        if self.recording:
            logger.warning("Already recording")
            return False

        try:
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            monitor = self.sct.monitors[self.monitor_index]

            # Quality settings
            quality_settings = {
                "low": (20, 15),     # FPS, quality
                "medium": (30, 20),
                "high": (60, 25),
            }
            fps, cv2_quality = quality_settings.get(quality, quality_settings["medium"])

            # Setup video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            size = (monitor["width"], monitor["height"])

            self.video_writer = cv2.VideoWriter(
                str(output_path),
                fourcc,
                fps,
                size
            )

            if not self.video_writer.isOpened():
                logger.error("Failed to open video writer")
                return False

            self.video_path = output_path
            self.recording = True

            # Start recording loop in background
            self.record_task = asyncio.create_task(self._record_loop(fps))

            logger.info(f"Video recording started: {output_path} ({quality}, {fps} FPS)")
            return True

        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            return False

    async def _record_loop(self, fps: int):
        """Background loop to capture video frames."""
        frame_delay = 1.0 / fps

        try:
            monitor = self.sct.monitors[self.monitor_index]

            while self.recording:
                # Capture frame
                screenshot = self.sct.grab(monitor)

                # Convert to numpy array (BGR format for OpenCV)
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                # Write frame
                self.video_writer.write(frame)

                # Control frame rate
                await asyncio.sleep(frame_delay)

        except Exception as e:
            logger.error(f"Recording loop error: {e}")
            self.recording = False

    async def stop_recording(self) -> Optional[Path]:
        """Stop video recording."""
        if not self.recording:
            logger.warning("Not currently recording")
            return None

        try:
            self.recording = False

            # Wait for recording loop to finish
            if self.record_task:
                await self.record_task

            # Release video writer
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None

            logger.info(f"Video recording stopped: {self.video_path}")
            return self.video_path

        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")
            return None

    async def is_recording(self) -> bool:
        """Check if currently recording."""
        return self.recording

    async def cleanup(self) -> None:
        """Cleanup resources."""
        if self.recording:
            await self.stop_recording()

        if self.sct:
            self.sct.close()
            self.sct = None

        logger.info("Direct capture backend cleaned up")
