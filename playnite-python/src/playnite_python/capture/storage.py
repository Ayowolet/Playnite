"""Media storage organization and management."""
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import shutil
from loguru import logger

from ..core.config import settings


class CaptureStorage:
    """Manages organization and storage of captured media."""

    def __init__(self, base_path: Path = None):
        self.base_path = base_path or settings.capture_base_path
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Capture storage initialized: {self.base_path}")

    def get_game_directory(self, game_id: str) -> Path:
        """
        Get directory for game captures.

        Args:
            game_id: Game identifier

        Returns:
            Path to game's capture directory
        """
        game_dir = self.base_path / game_id
        game_dir.mkdir(exist_ok=True)
        return game_dir

    def get_screenshot_path(self, game_id: str, session_id: str = None) -> Path:
        """
        Generate path for new screenshot.

        Args:
            game_id: Game identifier
            session_id: Optional session ID to include in filename

        Returns:
            Path where screenshot should be saved
        """
        game_dir = self.get_game_directory(game_id)
        screenshots_dir = game_dir / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        counter = 1

        while True:
            if session_id:
                filename = f"screenshot_{session_id}_{timestamp}_{counter:03d}.png"
            else:
                filename = f"screenshot_{timestamp}_{counter:03d}.png"

            path = screenshots_dir / filename
            if not path.exists():
                return path
            counter += 1

    def get_video_path(self, game_id: str, session_id: str = None) -> Path:
        """
        Generate path for new video.

        Args:
            game_id: Game identifier
            session_id: Optional session ID to include in filename

        Returns:
            Path where video should be saved
        """
        game_dir = self.get_game_directory(game_id)
        videos_dir = game_dir / "videos"
        videos_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if session_id:
            filename = f"video_{session_id}_{timestamp}.mp4"
        else:
            filename = f"video_{timestamp}.mp4"

        return videos_dir / filename

    def get_replay_path(self, game_id: str, session_id: Optional[str] = None) -> Path:
        """
        Generate path for instant replay video.

        Args:
            game_id: Game identifier
            session_id: Optional session identifier

        Returns:
            Path where replay should be saved
        """
        game_dir = self.get_game_directory(game_id)
        replays_dir = game_dir / "replays"
        replays_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if session_id:
            filename = f"replay_{session_id}_{timestamp}.mp4"
        else:
            filename = f"replay_{timestamp}.mp4"

        return replays_dir / filename

    def list_captures(self, game_id: str) -> Dict[str, List[Path]]:
        """
        List all captures for a game.

        Args:
            game_id: Game identifier

        Returns:
            Dictionary with 'screenshots' and 'videos' lists
        """
        game_dir = self.get_game_directory(game_id)

        screenshots_dir = game_dir / "screenshots"
        videos_dir = game_dir / "videos"
        replays_dir = game_dir / "replays"

        captures = {
            "screenshots": [],
            "videos": [],
            "replays": []
        }

        # Find screenshots
        if screenshots_dir.exists():
            captures["screenshots"] = sorted(
                screenshots_dir.glob("*.png"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

        # Find videos
        if videos_dir.exists():
            captures["videos"] = sorted(
                videos_dir.glob("*.mp4"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

        # Find replays
        if replays_dir.exists():
            captures["replays"] = sorted(
                replays_dir.glob("*.mp4"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

        logger.debug(
            f"Game {game_id}: {len(captures['screenshots'])} screenshots, "
            f"{len(captures['videos'])} videos, {len(captures['replays'])} replays"
        )

        return captures

    def get_storage_usage(self, game_id: str = None) -> Dict:
        """
        Calculate storage usage.

        Args:
            game_id: Optional game ID (if None, calculates total usage)

        Returns:
            Dictionary with storage statistics
        """
        if game_id:
            game_dir = self.get_game_directory(game_id)
            total_size = sum(
                f.stat().st_size for f in game_dir.rglob('*') if f.is_file()
            )

            captures = self.list_captures(game_id)

            return {
                "game_id": game_id,
                "size_bytes": total_size,
                "size_mb": round(total_size / 1024 / 1024, 2),
                "screenshot_count": len(captures["screenshots"]),
                "video_count": len(captures["videos"]),
            }
        else:
            # Calculate total usage across all games
            total_size = sum(
                f.stat().st_size for f in self.base_path.rglob('*') if f.is_file()
            )

            # Count games with captures
            game_dirs = [d for d in self.base_path.iterdir() if d.is_dir()]

            total_screenshots = 0
            total_videos = 0

            for game_dir in game_dirs:
                screenshots_dir = game_dir / "screenshots"
                videos_dir = game_dir / "videos"

                if screenshots_dir.exists():
                    total_screenshots += len(list(screenshots_dir.glob("*.png")))
                if videos_dir.exists():
                    total_videos += len(list(videos_dir.glob("*.mp4")))

            return {
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / 1024 / 1024, 2),
                "total_size_gb": round(total_size / 1024 / 1024 / 1024, 2),
                "game_count": len(game_dirs),
                "total_screenshots": total_screenshots,
                "total_videos": total_videos,
            }

    def cleanup_old_captures(
        self, game_id: str, keep_count: int = 100, max_age_days: int = 90
    ) -> int:
        """
        Clean up old captures to save space.

        Args:
            game_id: Game identifier
            keep_count: Minimum number of recent captures to keep
            max_age_days: Delete captures older than this many days

        Returns:
            Number of files deleted
        """
        from datetime import timedelta

        deleted_count = 0
        max_age = datetime.now() - timedelta(days=max_age_days)

        captures = self.list_captures(game_id)

        # Process screenshots
        for i, screenshot in enumerate(captures["screenshots"]):
            # Keep most recent files
            if i < keep_count:
                continue

            # Delete if older than max age
            file_time = datetime.fromtimestamp(screenshot.stat().st_mtime)
            if file_time < max_age:
                screenshot.unlink()
                deleted_count += 1
                logger.debug(f"Deleted old screenshot: {screenshot}")

        # Process videos (same logic)
        for i, video in enumerate(captures["videos"]):
            if i < keep_count:
                continue

            file_time = datetime.fromtimestamp(video.stat().st_mtime)
            if file_time < max_age:
                video.unlink()
                deleted_count += 1
                logger.debug(f"Deleted old video: {video}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old captures for game {game_id}")

        return deleted_count

    def delete_game_captures(self, game_id: str) -> bool:
        """
        Delete all captures for a game.

        Args:
            game_id: Game identifier

        Returns:
            True if successful
        """
        try:
            game_dir = self.get_game_directory(game_id)
            if game_dir.exists():
                shutil.rmtree(game_dir)
                logger.info(f"Deleted all captures for game {game_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete captures for game {game_id}: {e}")
            return False
