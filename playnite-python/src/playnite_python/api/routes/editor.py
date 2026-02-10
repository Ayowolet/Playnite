"""API routes for video/screenshot editing."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Tuple
from pathlib import Path
from loguru import logger

from ...capture.processors.video_editor import VideoEditor, ScreenshotEditor

router = APIRouter()
video_editor = VideoEditor()
screenshot_editor = ScreenshotEditor()


class TrimRequest(BaseModel):
    """Request to trim a video."""

    input_path: str = Field(..., description="Path to input video")
    output_path: str = Field(..., description="Path to output video")
    start_time: float = Field(..., description="Start time in seconds")
    end_time: Optional[float] = Field(None, description="End time in seconds")
    duration: Optional[float] = Field(None, description="Duration in seconds")


class CropVideoRequest(BaseModel):
    """Request to crop a video."""

    input_path: str
    output_path: str
    x: int = Field(..., description="Top-left X coordinate")
    y: int = Field(..., description="Top-left Y coordinate")
    width: int = Field(..., description="Crop width")
    height: int = Field(..., description="Crop height")


class TextOverlayRequest(BaseModel):
    """Request to add text overlay to video."""

    input_path: str
    output_path: str
    text: str = Field(..., description="Text to display")
    position: Tuple[int, int] = Field((10, 10), description="(x, y) position")
    font_size: int = Field(48, description="Font size in pixels")
    color: Tuple[int, int, int] = Field((255, 255, 255), description="RGB color")
    duration: Optional[float] = Field(None, description="Duration to show text")


class ConcatenateRequest(BaseModel):
    """Request to concatenate videos."""

    input_paths: List[str] = Field(..., description="List of input video paths")
    output_path: str = Field(..., description="Path to output video")
    transition: str = Field("none", description="Transition type")


class ConvertRequest(BaseModel):
    """Request to convert video format."""

    input_path: str
    output_path: str
    codec: str = Field("libx264", description="Video codec")


class ExtractFrameRequest(BaseModel):
    """Request to extract frame from video."""

    video_path: str
    output_path: str
    timestamp: float = Field(..., description="Time in seconds")


class ThumbnailRequest(BaseModel):
    """Request to create thumbnail."""

    video_path: str
    output_path: str
    width: int = Field(320, description="Thumbnail width")


class AnnotateScreenshotRequest(BaseModel):
    """Request to annotate screenshot."""

    input_path: str
    output_path: str
    text: str
    position: Tuple[int, int] = Field((10, 10))
    font_size: int = Field(24)
    color: Tuple[int, int, int] = Field((255, 255, 255))
    background: bool = Field(True)


class CropScreenshotRequest(BaseModel):
    """Request to crop screenshot."""

    input_path: str
    output_path: str
    x: int
    y: int
    width: int
    height: int


class ResizeScreenshotRequest(BaseModel):
    """Request to resize screenshot."""

    input_path: str
    output_path: str
    width: Optional[int] = None
    height: Optional[int] = None


@router.post("/video/trim")
async def trim_video(request: TrimRequest):
    """
    Trim video to specific time range.

    Cuts the video from start_time to end_time (or for duration).
    """
    try:
        success = video_editor.trim(
            input_path=Path(request.input_path),
            output_path=Path(request.output_path),
            start_time=request.start_time,
            end_time=request.end_time,
            duration=request.duration,
        )

        if success:
            return {"status": "success", "output_path": request.output_path}
        else:
            raise HTTPException(status_code=500, detail="Failed to trim video")

    except Exception as e:
        logger.error(f"Video trim failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/video/crop")
async def crop_video(request: CropVideoRequest):
    """
    Crop video to specific region.

    Extracts a rectangular region from the video.
    """
    try:
        success = video_editor.crop(
            input_path=Path(request.input_path),
            output_path=Path(request.output_path),
            x=request.x,
            y=request.y,
            width=request.width,
            height=request.height,
        )

        if success:
            return {"status": "success", "output_path": request.output_path}
        else:
            raise HTTPException(status_code=500, detail="Failed to crop video")

    except Exception as e:
        logger.error(f"Video crop failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/video/text-overlay")
async def add_text_overlay(request: TextOverlayRequest):
    """
    Add text overlay to video.

    Displays text at specified position for the entire video or specific duration.
    """
    try:
        success = video_editor.add_text_overlay(
            input_path=Path(request.input_path),
            output_path=Path(request.output_path),
            text=request.text,
            position=request.position,
            font_size=request.font_size,
            color=request.color,
            duration=request.duration,
        )

        if success:
            return {"status": "success", "output_path": request.output_path}
        else:
            raise HTTPException(status_code=500, detail="Failed to add text overlay")

    except Exception as e:
        logger.error(f"Text overlay failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/video/concatenate")
async def concatenate_videos(request: ConcatenateRequest):
    """
    Concatenate multiple video clips.

    Joins videos in the order provided.
    """
    try:
        input_paths = [Path(p) for p in request.input_paths]

        success = video_editor.concatenate(
            input_paths=input_paths,
            output_path=Path(request.output_path),
            transition=request.transition,
        )

        if success:
            return {"status": "success", "output_path": request.output_path}
        else:
            raise HTTPException(status_code=500, detail="Failed to concatenate videos")

    except Exception as e:
        logger.error(f"Video concatenation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/video/convert")
async def convert_video(request: ConvertRequest):
    """
    Convert video format/codec.

    Transcode video to different format.
    """
    try:
        success = video_editor.convert_format(
            input_path=Path(request.input_path),
            output_path=Path(request.output_path),
            codec=request.codec,
        )

        if success:
            return {"status": "success", "output_path": request.output_path}
        else:
            raise HTTPException(status_code=500, detail="Failed to convert video")

    except Exception as e:
        logger.error(f"Video conversion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/video/info")
async def get_video_info(video_path: str):
    """
    Get video metadata.

    Returns duration, resolution, fps, codec, etc.
    """
    try:
        info = video_editor.get_video_info(Path(video_path))

        if info:
            return info
        else:
            raise HTTPException(status_code=404, detail="Video not found or invalid")

    except Exception as e:
        logger.error(f"Failed to get video info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/video/extract-frame")
async def extract_frame(request: ExtractFrameRequest):
    """
    Extract single frame from video.

    Saves frame at specified timestamp as image.
    """
    try:
        success = video_editor.extract_frame(
            video_path=Path(request.video_path),
            output_path=Path(request.output_path),
            timestamp=request.timestamp,
        )

        if success:
            return {"status": "success", "output_path": request.output_path}
        else:
            raise HTTPException(status_code=500, detail="Failed to extract frame")

    except Exception as e:
        logger.error(f"Frame extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/video/thumbnail")
async def create_thumbnail(request: ThumbnailRequest):
    """
    Create thumbnail from video.

    Extracts first frame and resizes to thumbnail.
    """
    try:
        success = video_editor.create_thumbnail(
            video_path=Path(request.video_path),
            output_path=Path(request.output_path),
            width=request.width,
        )

        if success:
            return {"status": "success", "output_path": request.output_path}
        else:
            raise HTTPException(status_code=500, detail="Failed to create thumbnail")

    except Exception as e:
        logger.error(f"Thumbnail creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/screenshot/annotate")
async def annotate_screenshot(request: AnnotateScreenshotRequest):
    """
    Add text annotation to screenshot.

    Adds text with optional background box.
    """
    try:
        success = screenshot_editor.add_text_annotation(
            input_path=Path(request.input_path),
            output_path=Path(request.output_path),
            text=request.text,
            position=request.position,
            font_size=request.font_size,
            color=request.color,
            background=request.background,
        )

        if success:
            return {"status": "success", "output_path": request.output_path}
        else:
            raise HTTPException(status_code=500, detail="Failed to annotate screenshot")

    except Exception as e:
        logger.error(f"Screenshot annotation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/screenshot/crop")
async def crop_screenshot(request: CropScreenshotRequest):
    """
    Crop screenshot to specific region.

    Extracts rectangular region from image.
    """
    try:
        success = screenshot_editor.crop_screenshot(
            input_path=Path(request.input_path),
            output_path=Path(request.output_path),
            x=request.x,
            y=request.y,
            width=request.width,
            height=request.height,
        )

        if success:
            return {"status": "success", "output_path": request.output_path}
        else:
            raise HTTPException(status_code=500, detail="Failed to crop screenshot")

    except Exception as e:
        logger.error(f"Screenshot crop failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/screenshot/resize")
async def resize_screenshot(request: ResizeScreenshotRequest):
    """
    Resize screenshot maintaining aspect ratio.

    Specify either width or height, the other dimension is calculated automatically.
    """
    try:
        success = screenshot_editor.resize_screenshot(
            input_path=Path(request.input_path),
            output_path=Path(request.output_path),
            width=request.width,
            height=request.height,
        )

        if success:
            return {"status": "success", "output_path": request.output_path}
        else:
            raise HTTPException(status_code=500, detail="Failed to resize screenshot")

    except Exception as e:
        logger.error(f"Screenshot resize failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
