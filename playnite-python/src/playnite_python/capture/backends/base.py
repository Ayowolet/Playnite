"""Abstract base class for capture backends."""
from abc import ABC, abstractmethod
from typing import Optional
from pathlib import Path


class CaptureBackend(ABC):
    """Abstract interface for screenshot and video capture backends."""

    @abstractmethod
    async def initialize(self, game_name: str, process_id: int) -> bool:
        """
        Initialize capture backend for a game.

        Args:
            game_name: Name of the game being captured
            process_id: Process ID of the running game

        Returns:
            True if initialization successful
        """
        pass

    @abstractmethod
    async def capture_screenshot(self, output_path: Path) -> bool:
        """
        Capture a screenshot and save to file.

        Args:
            output_path: Full path where screenshot should be saved

        Returns:
            True if capture successful
        """
        pass

    @abstractmethod
    async def start_recording(self, output_path: Path, quality: str = "high") -> bool:
        """
        Start video recording.

        Args:
            output_path: Full path where video should be saved
            quality: Quality setting (low, medium, high)

        Returns:
            True if recording started successfully
        """
        pass

    @abstractmethod
    async def stop_recording(self) -> Optional[Path]:
        """
        Stop video recording.

        Returns:
            Path to saved video file, or None if failed
        """
        pass

    @abstractmethod
    async def is_recording(self) -> bool:
        """
        Check if currently recording.

        Returns:
            True if recording is active
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """
        Cleanup resources and stop any active captures.
        """
        pass
