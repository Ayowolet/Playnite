"""Metadata service for managing capture file metadata."""
import subprocess
import json
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime, timezone
from loguru import logger
from PIL import Image

from sqlalchemy import create_engine, and_, or_
from sqlalchemy.orm import sessionmaker, Session

from ..database.models import Base, CaptureMetadata


class MetadataService:
    """
    Service for managing capture metadata.

    Handles creation, retrieval, updating, and searching of metadata
    for screenshots, videos, and instant replays.
    """

    def __init__(self, db_path: str = "playnite_captures.db"):
        """
        Initialize metadata service.

        Args:
            db_path: Path to SQLite database
        """
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        logger.info(f"Metadata service initialized with database: {db_path}")

    def create_metadata(
        self,
        file_path: Path,
        game_id: str,
        game_name: str,
        session_id: str,
        capture_type: str,
    ) -> Optional[int]:
        """
        Create metadata entry for a new capture.

        Args:
            file_path: Path to captured file
            game_id: Game identifier
            game_name: Game name
            session_id: Capture session ID
            capture_type: Type of capture ("screenshot", "video", "replay")

        Returns:
            Metadata ID if created successfully, None otherwise
        """
        session: Session = self.Session()
        try:
            # Check if file exists
            if not file_path.exists():
                logger.warning(f"File not found for metadata: {file_path}")
                return None

            # Get file size
            file_size = file_path.stat().st_size

            # Extract media properties based on type
            duration = None
            width = None
            height = None
            file_format = file_path.suffix.lstrip(".")

            if capture_type == "screenshot":
                # Get image dimensions
                try:
                    with Image.open(file_path) as img:
                        width, height = img.size
                except Exception as e:
                    logger.warning(f"Could not read image dimensions: {e}")

            elif capture_type in ["video", "replay"]:
                # Get video metadata using ffprobe
                video_info = self._extract_video_metadata(file_path)
                if video_info:
                    duration = video_info.get("duration")
                    width = video_info.get("width")
                    height = video_info.get("height")

            # Create metadata entry
            metadata = CaptureMetadata(
                file_path=str(file_path),
                file_name=file_path.name,
                game_id=game_id,
                game_name=game_name,
                session_id=session_id,
                capture_type=capture_type,
                timestamp=datetime.now(timezone.utc),
                file_size_bytes=file_size,
                duration_seconds=duration,
                resolution_width=width,
                resolution_height=height,
                format=file_format,
                tags=[],
                is_favorite=False,
            )

            session.add(metadata)
            session.commit()

            metadata_id = metadata.id
            logger.info(
                f"Created metadata for {capture_type}: {file_path.name} "
                f"(ID: {metadata_id})"
            )

            return metadata_id

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create metadata: {e}")
            return None

        finally:
            session.close()

    def get_metadata(self, metadata_id: int) -> Optional[Dict]:
        """
        Get metadata by ID.

        Args:
            metadata_id: Metadata identifier

        Returns:
            Metadata dictionary or None
        """
        session: Session = self.Session()
        try:
            metadata = session.query(CaptureMetadata).filter_by(id=metadata_id).first()

            if not metadata:
                return None

            return self._metadata_to_dict(metadata)

        finally:
            session.close()

    def get_metadata_by_path(self, file_path: str) -> Optional[Dict]:
        """
        Get metadata by file path.

        Args:
            file_path: Path to capture file

        Returns:
            Metadata dictionary or None
        """
        session: Session = self.Session()
        try:
            metadata = (
                session.query(CaptureMetadata).filter_by(file_path=file_path).first()
            )

            if not metadata:
                return None

            return self._metadata_to_dict(metadata)

        finally:
            session.close()

    def update_metadata(
        self,
        metadata_id: int,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        rating: Optional[int] = None,
        is_favorite: Optional[bool] = None,
    ) -> bool:
        """
        Update user-editable metadata fields.

        Args:
            metadata_id: Metadata identifier
            tags: New tags list (None to keep existing)
            notes: New notes text (None to keep existing)
            rating: New rating 1-5 (None to keep existing)
            is_favorite: New favorite status (None to keep existing)

        Returns:
            True if updated successfully
        """
        session: Session = self.Session()
        try:
            metadata = session.query(CaptureMetadata).filter_by(id=metadata_id).first()

            if not metadata:
                logger.warning(f"Metadata not found: {metadata_id}")
                return False

            # Update fields if provided
            if tags is not None:
                metadata.tags = tags
            if notes is not None:
                metadata.notes = notes
            if rating is not None:
                if 1 <= rating <= 5:
                    metadata.rating = rating
                else:
                    logger.warning(f"Invalid rating: {rating}, must be 1-5")
            if is_favorite is not None:
                metadata.is_favorite = is_favorite

            metadata.updated_at = datetime.now(timezone.utc)

            session.commit()
            logger.info(f"Updated metadata: {metadata_id}")

            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update metadata: {e}")
            return False

        finally:
            session.close()

    def search_captures(
        self,
        game_id: Optional[str] = None,
        capture_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_favorite: Optional[bool] = None,
        min_rating: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """
        Search captures with filters.

        Args:
            game_id: Filter by game ID
            capture_type: Filter by type ("screenshot", "video", "replay")
            tags: Filter by tags (any match)
            is_favorite: Filter by favorite status
            min_rating: Minimum rating (1-5)
            start_date: Filter by captures after this date
            end_date: Filter by captures before this date
            limit: Maximum results to return
            offset: Number of results to skip

        Returns:
            List of metadata dictionaries
        """
        session: Session = self.Session()
        try:
            query = session.query(CaptureMetadata)

            # Apply filters
            if game_id:
                query = query.filter(CaptureMetadata.game_id == game_id)

            if capture_type:
                query = query.filter(CaptureMetadata.capture_type == capture_type)

            if is_favorite is not None:
                query = query.filter(CaptureMetadata.is_favorite == is_favorite)

            if min_rating:
                query = query.filter(CaptureMetadata.rating >= min_rating)

            if start_date:
                query = query.filter(CaptureMetadata.timestamp >= start_date)

            if end_date:
                query = query.filter(CaptureMetadata.timestamp <= end_date)

            # Tag filtering (JSON field - check if any provided tag is in the tags list)
            if tags:
                # SQLite JSON filtering is limited, so we'll filter in Python
                pass

            # Order by timestamp descending (newest first)
            query = query.order_by(CaptureMetadata.timestamp.desc())

            # Apply pagination
            query = query.limit(limit).offset(offset)

            results = query.all()

            # Post-process tag filtering if needed
            metadata_list = [self._metadata_to_dict(m) for m in results]

            if tags:
                metadata_list = [
                    m
                    for m in metadata_list
                    if m.get("tags") and any(tag in m["tags"] for tag in tags)
                ]

            return metadata_list

        finally:
            session.close()

    def get_game_captures(self, game_id: str) -> Dict[str, List[Dict]]:
        """
        Get all captures for a specific game, grouped by type.

        Args:
            game_id: Game identifier

        Returns:
            Dictionary with screenshots, videos, and replays lists
        """
        session: Session = self.Session()
        try:
            captures = (
                session.query(CaptureMetadata)
                .filter_by(game_id=game_id)
                .order_by(CaptureMetadata.timestamp.desc())
                .all()
            )

            result = {"screenshots": [], "videos": [], "replays": []}

            for capture in captures:
                metadata_dict = self._metadata_to_dict(capture)

                if capture.capture_type == "screenshot":
                    result["screenshots"].append(metadata_dict)
                elif capture.capture_type == "video":
                    result["videos"].append(metadata_dict)
                elif capture.capture_type == "replay":
                    result["replays"].append(metadata_dict)

            return result

        finally:
            session.close()

    def delete_metadata(self, metadata_id: int) -> bool:
        """
        Delete metadata entry.

        Note: This does not delete the actual file, only the metadata.

        Args:
            metadata_id: Metadata identifier

        Returns:
            True if deleted successfully
        """
        session: Session = self.Session()
        try:
            metadata = session.query(CaptureMetadata).filter_by(id=metadata_id).first()

            if not metadata:
                logger.warning(f"Metadata not found: {metadata_id}")
                return False

            session.delete(metadata)
            session.commit()

            logger.info(f"Deleted metadata: {metadata_id}")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to delete metadata: {e}")
            return False

        finally:
            session.close()

    def get_statistics(self) -> Dict:
        """
        Get overall capture statistics.

        Returns:
            Statistics dictionary
        """
        session: Session = self.Session()
        try:
            total_captures = session.query(CaptureMetadata).count()
            total_screenshots = (
                session.query(CaptureMetadata)
                .filter_by(capture_type="screenshot")
                .count()
            )
            total_videos = (
                session.query(CaptureMetadata).filter_by(capture_type="video").count()
            )
            total_replays = (
                session.query(CaptureMetadata).filter_by(capture_type="replay").count()
            )

            total_size = (
                session.query(CaptureMetadata).with_entities(
                    CaptureMetadata.file_size_bytes
                )
            )
            total_size_bytes = sum(
                m.file_size_bytes for m in total_size if m.file_size_bytes
            )

            favorites_count = (
                session.query(CaptureMetadata).filter_by(is_favorite=True).count()
            )

            games_count = session.query(CaptureMetadata.game_id).distinct().count()

            return {
                "total_captures": total_captures,
                "total_screenshots": total_screenshots,
                "total_videos": total_videos,
                "total_replays": total_replays,
                "total_size_bytes": total_size_bytes,
                "total_size_mb": total_size_bytes / (1024 * 1024),
                "total_size_gb": total_size_bytes / (1024 * 1024 * 1024),
                "favorites_count": favorites_count,
                "games_count": games_count,
            }

        finally:
            session.close()

    def _extract_video_metadata(self, video_path: Path) -> Optional[Dict]:
        """
        Extract video metadata using ffprobe.

        Args:
            video_path: Path to video file

        Returns:
            Dictionary with duration, width, height, or None if failed
        """
        try:
            # Run ffprobe to get video info
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    str(video_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.warning(f"ffprobe failed for {video_path}")
                return None

            data = json.loads(result.stdout)

            # Extract duration from format
            duration = None
            if "format" in data and "duration" in data["format"]:
                duration = float(data["format"]["duration"])

            # Extract resolution from video stream
            width = None
            height = None
            if "streams" in data:
                for stream in data["streams"]:
                    if stream.get("codec_type") == "video":
                        width = stream.get("width")
                        height = stream.get("height")
                        break

            return {"duration": duration, "width": width, "height": height}

        except FileNotFoundError:
            logger.warning("ffprobe not found, video metadata extraction disabled")
            return None
        except subprocess.TimeoutExpired:
            logger.warning(f"ffprobe timeout for {video_path}")
            return None
        except Exception as e:
            logger.warning(f"Failed to extract video metadata: {e}")
            return None

    def _metadata_to_dict(self, metadata: CaptureMetadata) -> Dict:
        """
        Convert metadata ORM object to dictionary.

        Args:
            metadata: CaptureMetadata object

        Returns:
            Dictionary representation
        """
        return {
            "id": metadata.id,
            "file_path": metadata.file_path,
            "file_name": metadata.file_name,
            "game_id": metadata.game_id,
            "game_name": metadata.game_name,
            "session_id": metadata.session_id,
            "capture_type": metadata.capture_type,
            "timestamp": metadata.timestamp.isoformat() if metadata.timestamp else None,
            "file_size_bytes": metadata.file_size_bytes,
            "duration_seconds": metadata.duration_seconds,
            "resolution_width": metadata.resolution_width,
            "resolution_height": metadata.resolution_height,
            "format": metadata.format,
            "tags": metadata.tags or [],
            "notes": metadata.notes,
            "rating": metadata.rating,
            "is_favorite": metadata.is_favorite,
            "created_at": metadata.created_at.isoformat() if metadata.created_at else None,
            "updated_at": metadata.updated_at.isoformat() if metadata.updated_at else None,
        }
