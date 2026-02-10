"""Basic video editing tools for gameplay captures."""
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple
from loguru import logger
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


class VideoEditor:
    """
    Basic video editing operations for gameplay captures.

    Supports:
    - Trimming (cut start/end)
    - Cropping (select region)
    - Text annotations (add overlays)
    - Concatenation (join multiple clips)
    - Format conversion
    """

    def __init__(self):
        self.ffmpeg_available = self._check_ffmpeg()

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available."""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("ffmpeg not found - some features may be unavailable")
            return False

    def trim(
        self,
        input_path: Path,
        output_path: Path,
        start_time: float,
        end_time: Optional[float] = None,
        duration: Optional[float] = None,
    ) -> bool:
        """
        Trim video to specific time range.

        Args:
            input_path: Input video file
            output_path: Output video file
            start_time: Start time in seconds
            end_time: End time in seconds (optional, use duration instead)
            duration: Duration in seconds (optional, use end_time instead)

        Returns:
            True if successful, False otherwise
        """
        if not self.ffmpeg_available:
            logger.error("ffmpeg not available for trimming")
            return False

        try:
            # Build ffmpeg command
            cmd = ["ffmpeg", "-y", "-i", str(input_path), "-ss", str(start_time)]

            if duration is not None:
                cmd.extend(["-t", str(duration)])
            elif end_time is not None:
                cmd.extend(["-to", str(end_time)])

            # Copy codec for speed (no re-encoding)
            cmd.extend(["-c", "copy", str(output_path)])

            logger.info(f"Trimming video: {start_time}s to {end_time or duration}s")

            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
            )

            if output_path.exists():
                logger.info(f"✓ Video trimmed: {output_path}")
                return True
            else:
                return False

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to trim video: {e.stderr.decode()}")
            return False

    def crop(
        self,
        input_path: Path,
        output_path: Path,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> bool:
        """
        Crop video to specific region.

        Args:
            input_path: Input video file
            output_path: Output video file
            x: Top-left X coordinate
            y: Top-left Y coordinate
            width: Crop width
            height: Crop height

        Returns:
            True if successful, False otherwise
        """
        if not self.ffmpeg_available:
            logger.error("ffmpeg not available for cropping")
            return False

        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-filter:v",
                f"crop={width}:{height}:{x}:{y}",
                str(output_path),
            ]

            logger.info(f"Cropping video to {width}x{height} at ({x}, {y})")

            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            if output_path.exists():
                logger.info(f"✓ Video cropped: {output_path}")
                return True
            else:
                return False

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to crop video: {e.stderr.decode()}")
            return False

    def add_text_overlay(
        self,
        input_path: Path,
        output_path: Path,
        text: str,
        position: Tuple[int, int] = (10, 10),
        font_size: int = 48,
        color: Tuple[int, int, int] = (255, 255, 255),
        duration: Optional[float] = None,
    ) -> bool:
        """
        Add text overlay to video.

        Args:
            input_path: Input video file
            output_path: Output video file
            text: Text to display
            position: (x, y) position of text
            font_size: Font size in pixels
            color: RGB color tuple
            duration: How long to show text (None = entire video)

        Returns:
            True if successful, False otherwise
        """
        if not self.ffmpeg_available:
            logger.error("ffmpeg not available for text overlay")
            return False

        try:
            x, y = position
            r, g, b = color

            # Build drawtext filter
            drawtext = (
                f"drawtext=text='{text}':"
                f"x={x}:y={y}:"
                f"fontsize={font_size}:"
                f"fontcolor=white@0.8:"
                f"box=1:boxcolor=black@0.5:boxborderw=5"
            )

            if duration is not None:
                drawtext += f":enable='between(t,0,{duration})'"

            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-vf",
                drawtext,
                "-codec:a",
                "copy",
                str(output_path),
            ]

            logger.info(f"Adding text overlay: '{text}'")

            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            if output_path.exists():
                logger.info(f"✓ Text overlay added: {output_path}")
                return True
            else:
                return False

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to add text overlay: {e.stderr.decode()}")
            return False

    def concatenate(
        self, input_paths: List[Path], output_path: Path, transition: str = "none"
    ) -> bool:
        """
        Concatenate multiple video clips.

        Args:
            input_paths: List of input video files
            output_path: Output video file
            transition: Transition type (none, fade, etc.)

        Returns:
            True if successful, False otherwise
        """
        if not self.ffmpeg_available:
            logger.error("ffmpeg not available for concatenation")
            return False

        if len(input_paths) < 2:
            logger.error("Need at least 2 videos to concatenate")
            return False

        try:
            # Create temporary file list
            filelist_path = output_path.parent / "filelist.txt"

            with open(filelist_path, "w") as f:
                for path in input_paths:
                    f.write(f"file '{path.absolute()}'\n")

            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(filelist_path),
                "-c",
                "copy",
                str(output_path),
            ]

            logger.info(f"Concatenating {len(input_paths)} videos")

            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            # Cleanup
            filelist_path.unlink()

            if output_path.exists():
                logger.info(f"✓ Videos concatenated: {output_path}")
                return True
            else:
                return False

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to concatenate videos: {e.stderr.decode()}")
            return False
        except Exception as e:
            logger.error(f"Error during concatenation: {e}")
            return False

    def convert_format(
        self, input_path: Path, output_path: Path, codec: str = "libx264"
    ) -> bool:
        """
        Convert video to different format/codec.

        Args:
            input_path: Input video file
            output_path: Output video file
            codec: Video codec (libx264, libx265, etc.)

        Returns:
            True if successful, False otherwise
        """
        if not self.ffmpeg_available:
            logger.error("ffmpeg not available for conversion")
            return False

        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-c:v",
                codec,
                "-preset",
                "medium",
                "-crf",
                "23",
                "-c:a",
                "aac",
                str(output_path),
            ]

            logger.info(f"Converting video to {codec}")

            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            if output_path.exists():
                logger.info(f"✓ Video converted: {output_path}")
                return True
            else:
                return False

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to convert video: {e.stderr.decode()}")
            return False

    def get_video_info(self, video_path: Path) -> Optional[dict]:
        """
        Get video metadata (duration, resolution, fps, etc.).

        Args:
            video_path: Path to video file

        Returns:
            Dictionary with video information, or None if failed
        """
        try:
            cap = cv2.VideoCapture(str(video_path))

            if not cap.isOpened():
                logger.error(f"Failed to open video: {video_path}")
                return None

            info = {
                "path": str(video_path),
                "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": cap.get(cv2.CAP_PROP_FPS),
                "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                "codec": int(cap.get(cv2.CAP_PROP_FOURCC)),
                "size_bytes": video_path.stat().st_size,
            }

            # Calculate duration
            if info["fps"] > 0:
                info["duration_seconds"] = info["frame_count"] / info["fps"]
            else:
                info["duration_seconds"] = 0

            cap.release()

            return info

        except Exception as e:
            logger.error(f"Failed to get video info: {e}")
            return None

    def extract_frame(
        self, video_path: Path, output_path: Path, timestamp: float
    ) -> bool:
        """
        Extract a single frame from video at timestamp.

        Args:
            video_path: Input video file
            output_path: Output image file
            timestamp: Time in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            cap = cv2.VideoCapture(str(video_path))

            if not cap.isOpened():
                logger.error(f"Failed to open video: {video_path}")
                return False

            # Seek to timestamp
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_number = int(timestamp * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

            # Read frame
            ret, frame = cap.read()
            cap.release()

            if not ret:
                logger.error(f"Failed to read frame at {timestamp}s")
                return False

            # Save frame
            cv2.imwrite(str(output_path), frame)

            logger.info(f"✓ Frame extracted at {timestamp}s: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to extract frame: {e}")
            return False

    def create_thumbnail(
        self, video_path: Path, output_path: Path, width: int = 320
    ) -> bool:
        """
        Create thumbnail from video (first frame).

        Args:
            video_path: Input video file
            output_path: Output image file
            width: Thumbnail width (height auto-calculated)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Extract first frame
            temp_frame = output_path.parent / "temp_frame.png"
            if not self.extract_frame(video_path, temp_frame, 0.1):
                return False

            # Resize to thumbnail
            img = Image.open(temp_frame)
            aspect_ratio = img.height / img.width
            height = int(width * aspect_ratio)
            img_resized = img.resize((width, height), Image.Resampling.LANCZOS)
            img_resized.save(output_path)

            # Cleanup
            temp_frame.unlink()

            logger.info(f"✓ Thumbnail created: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to create thumbnail: {e}")
            return False


class ScreenshotEditor:
    """Basic screenshot editing operations."""

    def add_text_annotation(
        self,
        input_path: Path,
        output_path: Path,
        text: str,
        position: Tuple[int, int] = (10, 10),
        font_size: int = 24,
        color: Tuple[int, int, int] = (255, 255, 255),
        background: bool = True,
    ) -> bool:
        """
        Add text annotation to screenshot.

        Args:
            input_path: Input image file
            output_path: Output image file
            text: Text to add
            position: (x, y) position
            font_size: Font size in pixels
            color: RGB color tuple
            background: Whether to add background box

        Returns:
            True if successful, False otherwise
        """
        try:
            img = Image.open(input_path)
            draw = ImageDraw.Draw(img)

            # Try to use a nice font, fallback to default
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except:
                font = ImageFont.load_default()

            # Get text bounding box
            bbox = draw.textbbox(position, text, font=font)

            # Draw background if requested
            if background:
                padding = 5
                draw.rectangle(
                    [
                        bbox[0] - padding,
                        bbox[1] - padding,
                        bbox[2] + padding,
                        bbox[3] + padding,
                    ],
                    fill=(0, 0, 0, 180),
                )

            # Draw text
            draw.text(position, text, fill=color, font=font)

            img.save(output_path)

            logger.info(f"✓ Text annotation added: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to add text annotation: {e}")
            return False

    def crop_screenshot(
        self, input_path: Path, output_path: Path, x: int, y: int, width: int, height: int
    ) -> bool:
        """
        Crop screenshot to specific region.

        Args:
            input_path: Input image file
            output_path: Output image file
            x: Top-left X coordinate
            y: Top-left Y coordinate
            width: Crop width
            height: Crop height

        Returns:
            True if successful, False otherwise
        """
        try:
            img = Image.open(input_path)
            cropped = img.crop((x, y, x + width, y + height))
            cropped.save(output_path)

            logger.info(f"✓ Screenshot cropped: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to crop screenshot: {e}")
            return False

    def resize_screenshot(
        self, input_path: Path, output_path: Path, width: Optional[int] = None, height: Optional[int] = None
    ) -> bool:
        """
        Resize screenshot maintaining aspect ratio.

        Args:
            input_path: Input image file
            output_path: Output image file
            width: Target width (if None, calculated from height)
            height: Target height (if None, calculated from width)

        Returns:
            True if successful, False otherwise
        """
        try:
            img = Image.open(input_path)

            if width and not height:
                aspect_ratio = img.height / img.width
                height = int(width * aspect_ratio)
            elif height and not width:
                aspect_ratio = img.width / img.height
                width = int(height * aspect_ratio)
            elif not width and not height:
                logger.error("Must specify either width or height")
                return False

            resized = img.resize((width, height), Image.Resampling.LANCZOS)
            resized.save(output_path)

            logger.info(f"✓ Screenshot resized to {width}x{height}: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to resize screenshot: {e}")
            return False
