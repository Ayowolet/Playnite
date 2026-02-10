"""API routes for media capture."""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from loguru import logger

from ..models.capture import (
    StartCaptureRequest,
    CaptureSessionResponse,
    ScreenshotResponse,
    VideoResponse,
    StorageUsageResponse,
    GameCapturesResponse,
    CaptureMetadataResponse,
    MetadataUpdateRequest,
    SearchCapturesRequest,
    StatisticsResponse,
)
from ...capture.manager import CaptureManager
from ...capture.storage import CaptureStorage
from ...capture.metadata import MetadataService

router = APIRouter()
manager = CaptureManager()
storage = CaptureStorage()
metadata_service = MetadataService()


@router.post("/start", response_model=CaptureSessionResponse)
async def start_capture(request: StartCaptureRequest):
    """
    Start a new capture session for a game.

    Initializes the capture backend and sets up hotkeys for screenshots and video recording.
    """
    try:
        settings_dict = request.settings.model_dump() if request.settings else {}

        session_id = await manager.start_session(
            game_id=request.game_id,
            game_name=request.game_name,
            process_id=request.process_id,
            settings=settings_dict,
        )

        if not session_id:
            raise HTTPException(
                status_code=500, detail="Failed to start capture session"
            )

        session = manager.get_session(session_id)

        return CaptureSessionResponse(
            session_id=session_id,
            status="active",
            game_name=request.game_name,
            backend=session.backend_name if session else "unknown",
        )

    except Exception as e:
        logger.error(f"Failed to start capture session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/screenshot/{session_id}", response_model=ScreenshotResponse)
async def capture_screenshot(session_id: str):
    """
    Capture a screenshot for an active session.

    The screenshot will be saved to the game's capture directory.
    """
    try:
        file_path = await manager.capture_screenshot(session_id)

        if not file_path:
            raise HTTPException(
                status_code=404,
                detail="Session not found or screenshot capture failed",
            )

        # Get file size
        size_bytes = file_path.stat().st_size if file_path.exists() else None

        return ScreenshotResponse(
            session_id=session_id,
            file_path=str(file_path),
            timestamp=datetime.now(timezone.utc).isoformat(),
            size_bytes=size_bytes,
        )

    except Exception as e:
        logger.error(f"Failed to capture screenshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/video/start/{session_id}", response_model=VideoResponse)
async def start_video_recording(session_id: str, quality: str = "high"):
    """
    Start video recording for a session.

    Args:
        session_id: Capture session identifier
        quality: Video quality (low, medium, high)
    """
    try:
        success = await manager.start_video_recording(session_id, quality)

        if not success:
            raise HTTPException(
                status_code=404,
                detail="Session not found or recording failed to start",
            )

        return VideoResponse(session_id=session_id, recording=True, file_path=None)

    except Exception as e:
        logger.error(f"Failed to start video recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/video/stop/{session_id}", response_model=VideoResponse)
async def stop_video_recording(session_id: str):
    """
    Stop video recording for a session.

    Returns the path to the recorded video file.
    """
    try:
        file_path = await manager.stop_video_recording(session_id)

        return VideoResponse(
            session_id=session_id,
            recording=False,
            file_path=str(file_path) if file_path else None,
        )

    except Exception as e:
        logger.error(f"Failed to stop video recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop/{session_id}")
async def stop_capture(session_id: str):
    """
    Stop a capture session.

    Cleans up resources and returns session statistics.
    """
    try:
        result = await manager.stop_session(session_id)

        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop capture session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions():
    """
    List all active capture sessions.

    Returns information about currently running capture sessions.
    """
    return {"sessions": manager.list_active_sessions()}


@router.get("/storage/usage", response_model=StorageUsageResponse)
async def get_storage_usage():
    """
    Get overall storage usage statistics.

    Returns total storage used by all captures across all games.
    """
    usage = storage.get_storage_usage()
    return StorageUsageResponse(**usage)


@router.get("/storage/game/{game_id}")
async def get_game_storage(game_id: str):
    """
    Get storage usage for a specific game.

    Returns capture counts and storage size for the specified game.
    """
    usage = storage.get_storage_usage(game_id)
    return usage


@router.get("/captures/{game_id}", response_model=GameCapturesResponse)
async def get_game_captures(game_id: str):
    """
    List all captures for a game.

    Returns paths to all screenshots and videos for the specified game.
    """
    captures = storage.list_captures(game_id)

    return GameCapturesResponse(
        game_id=game_id,
        screenshots=[str(p) for p in captures["screenshots"]],
        videos=[str(p) for p in captures["videos"]],
    )


@router.delete("/captures/{game_id}")
async def delete_game_captures(game_id: str):
    """
    Delete all captures for a game.

    Warning: This permanently deletes all screenshots and videos for the game.
    """
    success = storage.delete_game_captures(game_id)

    if success:
        return {"message": f"Deleted all captures for game {game_id}"}
    else:
        raise HTTPException(
            status_code=404, detail="Game not found or deletion failed"
        )


# ============================================================================
# Metadata Endpoints
# ============================================================================


@router.get("/metadata/{metadata_id}", response_model=CaptureMetadataResponse)
async def get_metadata(metadata_id: int):
    """
    Get metadata for a capture by ID.

    Returns detailed metadata including file info, game association,
    resolution, duration (for videos), tags, notes, and rating.
    """
    try:
        metadata = metadata_service.get_metadata(metadata_id)

        if not metadata:
            raise HTTPException(
                status_code=404, detail=f"Metadata not found: {metadata_id}"
            )

        return CaptureMetadataResponse(**metadata)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/metadata/{metadata_id}", response_model=CaptureMetadataResponse)
async def update_metadata(metadata_id: int, request: MetadataUpdateRequest):
    """
    Update user-editable metadata fields.

    Can update tags, notes, rating (1-5), and favorite status.
    """
    try:
        success = metadata_service.update_metadata(
            metadata_id=metadata_id,
            tags=request.tags,
            notes=request.notes,
            rating=request.rating,
            is_favorite=request.is_favorite,
        )

        if not success:
            raise HTTPException(
                status_code=404, detail=f"Metadata not found: {metadata_id}"
            )

        # Return updated metadata
        metadata = metadata_service.get_metadata(metadata_id)
        return CaptureMetadataResponse(**metadata)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/metadata/search")
async def search_captures(request: SearchCapturesRequest):
    """
    Search captures with filters.

    Supports filtering by game, capture type, tags, favorite status,
    rating, and date range. Returns paginated results.
    """
    try:
        # Parse date strings if provided
        start_date = None
        end_date = None

        if request.start_date:
            try:
                start_date = datetime.fromisoformat(request.start_date)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="Invalid start_date format (use ISO format)"
                )

        if request.end_date:
            try:
                end_date = datetime.fromisoformat(request.end_date)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="Invalid end_date format (use ISO format)"
                )

        results = metadata_service.search_captures(
            game_id=request.game_id,
            capture_type=request.capture_type,
            tags=request.tags,
            is_favorite=request.is_favorite,
            min_rating=request.min_rating,
            start_date=start_date,
            end_date=end_date,
            limit=request.limit,
            offset=request.offset,
        )

        return {
            "results": results,
            "count": len(results),
            "limit": request.limit,
            "offset": request.offset,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to search captures: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metadata/game/{game_id}")
async def get_game_metadata(game_id: str):
    """
    Get all capture metadata for a game.

    Returns captures grouped by type (screenshots, videos, replays)
    with full metadata for each.
    """
    try:
        captures = metadata_service.get_game_captures(game_id)

        return {
            "game_id": game_id,
            "screenshots": captures["screenshots"],
            "videos": captures["videos"],
            "replays": captures["replays"],
            "total": len(captures["screenshots"])
            + len(captures["videos"])
            + len(captures["replays"]),
        }

    except Exception as e:
        logger.error(f"Failed to get game metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metadata/statistics", response_model=StatisticsResponse)
async def get_statistics():
    """
    Get overall capture statistics.

    Returns counts, storage usage, and other aggregate statistics
    across all captures.
    """
    try:
        stats = metadata_service.get_statistics()
        return StatisticsResponse(**stats)

    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/metadata/{metadata_id}")
async def delete_metadata(metadata_id: int):
    """
    Delete metadata entry.

    Note: This only deletes the metadata, not the actual file.
    """
    try:
        success = metadata_service.delete_metadata(metadata_id)

        if not success:
            raise HTTPException(
                status_code=404, detail=f"Metadata not found: {metadata_id}"
            )

        return {"message": f"Metadata deleted: {metadata_id}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))
