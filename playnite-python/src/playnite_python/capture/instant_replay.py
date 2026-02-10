"""Instant replay buffer for capturing last N seconds of gameplay."""
import threading
import time
from collections import deque
from typing import Optional, Deque
from pathlib import Path
import numpy as np
import cv2
from loguru import logger
import mss


class InstantReplayBuffer:
    """
    Circular buffer that continuously captures frames for instant replay.

    Maintains a rolling window of the last N seconds of gameplay.
    When triggered, saves the buffer to disk as a video file.
    """

    def __init__(
        self,
        duration_seconds: int = 30,
        fps: int = 30,
        quality: str = "medium",
    ):
        """
        Initialize instant replay buffer.

        Args:
            duration_seconds: How many seconds of gameplay to buffer (default: 30)
            fps: Frames per second to capture (default: 30)
            quality: Capture quality - "low", "medium", "high" (default: medium)
        """
        self.duration_seconds = duration_seconds
        self.fps = fps
        self.quality = quality

        # Calculate buffer size
        self.max_frames = duration_seconds * fps
        self.frame_buffer: Deque[np.ndarray] = deque(maxlen=self.max_frames)
        self.timestamp_buffer: Deque[float] = deque(maxlen=self.max_frames)

        # Capture settings based on quality
        self.scale_factor = {
            "low": 0.5,      # 50% resolution
            "medium": 0.75,  # 75% resolution
            "high": 1.0,     # Full resolution
        }[quality]

        # State
        self.is_recording = False
        self.capture_thread: Optional[threading.Thread] = None
        self.sct = mss.mss()

        # Performance metrics
        self.frames_captured = 0
        self.frames_dropped = 0

    def start(self) -> bool:
        """
        Start capturing frames in background thread.

        Returns:
            True if started successfully, False otherwise
        """
        if self.is_recording:
            logger.warning("Instant replay buffer already recording")
            return False

        try:
            self.is_recording = True
            self.capture_thread = threading.Thread(
                target=self._capture_loop, daemon=True, name="InstantReplay"
            )
            self.capture_thread.start()

            logger.info(
                f"Started instant replay buffer: {self.duration_seconds}s at {self.fps} FPS ({self.quality})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to start instant replay buffer: {e}")
            self.is_recording = False
            return False

    def stop(self):
        """Stop capturing frames."""
        if not self.is_recording:
            return

        logger.info("Stopping instant replay buffer...")
        self.is_recording = False

        if self.capture_thread:
            self.capture_thread.join(timeout=2.0)

        logger.info(
            f"Stopped instant replay. Captured: {self.frames_captured}, Dropped: {self.frames_dropped}"
        )

    def _capture_loop(self):
        """Background thread that continuously captures frames."""
        frame_interval = 1.0 / self.fps
        next_capture_time = time.time()

        while self.is_recording:
            current_time = time.time()

            # Check if it's time to capture next frame
            if current_time >= next_capture_time:
                try:
                    # Capture screen
                    monitor = self.sct.monitors[1]  # Primary monitor
                    screenshot = self.sct.grab(monitor)

                    # Convert to numpy array
                    frame = np.array(screenshot)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                    # Scale if needed
                    if self.scale_factor < 1.0:
                        width = int(frame.shape[1] * self.scale_factor)
                        height = int(frame.shape[0] * self.scale_factor)
                        frame = cv2.resize(
                            frame, (width, height), interpolation=cv2.INTER_AREA
                        )

                    # Add to buffer (oldest frame automatically dropped if full)
                    self.frame_buffer.append(frame)
                    self.timestamp_buffer.append(current_time)
                    self.frames_captured += 1

                    # Schedule next capture
                    next_capture_time += frame_interval

                    # If we're falling behind, skip frames
                    if next_capture_time < current_time:
                        frames_behind = int((current_time - next_capture_time) / frame_interval)
                        self.frames_dropped += frames_behind
                        next_capture_time = current_time + frame_interval
                        logger.warning(
                            f"Instant replay falling behind, dropped {frames_behind} frames"
                        )

                except Exception as e:
                    logger.error(f"Error capturing frame for instant replay: {e}")
                    self.frames_dropped += 1

            else:
                # Sleep until next capture time
                sleep_time = next_capture_time - current_time
                if sleep_time > 0:
                    time.sleep(min(sleep_time, 0.001))  # Sleep max 1ms at a time

    def save(self, output_path: Path) -> bool:
        """
        Save buffered frames to video file.

        Args:
            output_path: Path to save video file

        Returns:
            True if saved successfully, False otherwise
        """
        if not self.frame_buffer:
            logger.warning("No frames in buffer to save")
            return False

        try:
            logger.info(f"Saving instant replay to {output_path} ({len(self.frame_buffer)} frames)")

            # Get frame dimensions from first frame
            first_frame = self.frame_buffer[0]
            height, width = first_frame.shape[:2]

            # Create video writer
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(output_path), fourcc, self.fps, (width, height))

            if not writer.isOpened():
                raise RuntimeError("Failed to open video writer")

            # Write all buffered frames
            frames_written = 0
            for frame in self.frame_buffer:
                writer.write(frame)
                frames_written += 1

            writer.release()

            # Verify file was created
            if not output_path.exists() or output_path.stat().st_size == 0:
                raise RuntimeError("Video file was not created or is empty")

            logger.info(
                f"✓ Saved instant replay: {frames_written} frames, "
                f"{output_path.stat().st_size / (1024*1024):.2f} MB"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to save instant replay: {e}")
            return False

    def get_buffer_info(self) -> dict:
        """
        Get information about current buffer state.

        Returns:
            Dictionary with buffer statistics
        """
        current_frames = len(self.frame_buffer)
        current_duration = current_frames / self.fps if self.fps > 0 else 0

        return {
            "is_recording": self.is_recording,
            "duration_seconds": self.duration_seconds,
            "fps": self.fps,
            "quality": self.quality,
            "scale_factor": self.scale_factor,
            "buffered_frames": current_frames,
            "buffered_duration": current_duration,
            "max_frames": self.max_frames,
            "frames_captured": self.frames_captured,
            "frames_dropped": self.frames_dropped,
            "buffer_fullness": current_frames / self.max_frames if self.max_frames > 0 else 0,
        }

    def clear(self):
        """Clear the buffer."""
        self.frame_buffer.clear()
        self.timestamp_buffer.clear()
        logger.info("Cleared instant replay buffer")

    def __del__(self):
        """Cleanup when object is destroyed."""
        self.stop()


class InstantReplayManager:
    """
    Manages instant replay buffers for multiple games/sessions.

    Handles lifecycle: starting buffer when game launches, saving on trigger,
    stopping when game exits.
    """

    def __init__(self):
        self.buffers: dict[str, InstantReplayBuffer] = {}
        self.default_duration = 30  # seconds
        self.default_fps = 30
        self.default_quality = "medium"

    def create_buffer(
        self,
        session_id: str,
        duration_seconds: Optional[int] = None,
        fps: Optional[int] = None,
        quality: Optional[str] = None,
    ) -> bool:
        """
        Create and start a new instant replay buffer for a session.

        Args:
            session_id: Unique session identifier
            duration_seconds: Buffer duration (default: 30)
            fps: Frames per second (default: 30)
            quality: Capture quality (default: "medium")

        Returns:
            True if created successfully, False otherwise
        """
        if session_id in self.buffers:
            logger.warning(f"Buffer already exists for session {session_id}")
            return False

        try:
            buffer = InstantReplayBuffer(
                duration_seconds=duration_seconds or self.default_duration,
                fps=fps or self.default_fps,
                quality=quality or self.default_quality,
            )

            if buffer.start():
                self.buffers[session_id] = buffer
                logger.info(f"Created instant replay buffer for session {session_id}")
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"Failed to create instant replay buffer: {e}")
            return False

    def save_replay(self, session_id: str, output_path: Path) -> bool:
        """
        Save buffered replay to file.

        Args:
            session_id: Session identifier
            output_path: Where to save the replay video

        Returns:
            True if saved successfully, False otherwise
        """
        buffer = self.buffers.get(session_id)
        if not buffer:
            logger.error(f"No buffer found for session {session_id}")
            return False

        return buffer.save(output_path)

    def get_buffer_info(self, session_id: str) -> Optional[dict]:
        """Get information about a session's buffer."""
        buffer = self.buffers.get(session_id)
        if not buffer:
            return None

        return buffer.get_buffer_info()

    def stop_buffer(self, session_id: str) -> bool:
        """
        Stop and remove a buffer.

        Args:
            session_id: Session identifier

        Returns:
            True if stopped successfully, False otherwise
        """
        buffer = self.buffers.pop(session_id, None)
        if not buffer:
            logger.warning(f"No buffer found for session {session_id}")
            return False

        buffer.stop()
        logger.info(f"Stopped and removed buffer for session {session_id}")
        return True

    def stop_all(self):
        """Stop all active buffers."""
        logger.info(f"Stopping {len(self.buffers)} instant replay buffers...")

        for session_id in list(self.buffers.keys()):
            self.stop_buffer(session_id)

    def get_active_sessions(self) -> list[str]:
        """Get list of sessions with active buffers."""
        return list(self.buffers.keys())

    def __del__(self):
        """Cleanup when manager is destroyed."""
        self.stop_all()
