"""
Basic media editing tools.

- Screenshots: crop, annotate, convert format, resize (via Pillow)
- Videos: trim, speed, concatenate, create montage, highlight detection,
          format conversion (via ffmpeg)
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


@dataclass
class HighlightMoment:
    """A single detected highlight moment in a video."""
    timestamp_seconds: float
    scene_score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_seconds": round(self.timestamp_seconds, 3),
            "scene_score": round(self.scene_score, 4),
        }

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


_MAX_END_SECONDS = 86_400  # 24 hours — guard against unbounded ffmpeg invocations


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


class MediaEditor:
    """
    Provides crop, annotate, trim, and montage operations for captured media.

    All methods return the output path.  Methods requiring missing
    dependencies raise a descriptive RuntimeError.
    """

    # ------------------------------------------------------------------ #
    # Screenshot editing (PIL)                                             #
    # ------------------------------------------------------------------ #

    def crop_screenshot(
        self,
        source: Path,
        dest: Path,
        region: Tuple[int, int, int, int],  # (left, top, right, bottom)
    ) -> Path:
        """Crop a screenshot to the specified pixel region."""
        if not _PIL_AVAILABLE:
            raise RuntimeError("Pillow is required for image cropping. pip install Pillow")
        img = Image.open(str(source))
        cropped = img.crop(region)
        cropped.save(str(dest))
        return dest

    def annotate_screenshot(
        self,
        source: Path,
        dest: Path,
        text: str,
        position: Tuple[int, int] = (10, 10),
        font_size: int = 20,
        color: Tuple[int, int, int] = (255, 255, 255),
        background_color: Optional[Tuple[int, int, int, int]] = (0, 0, 0, 128),
    ) -> Path:
        """Add text annotation to a screenshot."""
        if not _PIL_AVAILABLE:
            raise RuntimeError("Pillow is required for annotations. pip install Pillow")

        img = Image.open(str(source)).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Estimate text size for background box
        font: Optional[ImageFont.FreeTypeFont] = None
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
        except Exception:
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None

        if background_color:
            # Draw semi-transparent background behind text
            try:
                bbox = draw.textbbox(position, text, font=font)
                padded = (bbox[0] - 4, bbox[1] - 4, bbox[2] + 4, bbox[3] + 4)
                draw.rectangle(padded, fill=background_color)
            except Exception:
                log.debug("textbbox unavailable; skipping annotation background", exc_info=True)

        draw.text(position, text, fill=(*color, 255), font=font)
        combined = Image.alpha_composite(img, overlay).convert("RGB")
        combined.save(str(dest))
        return dest

    def resize_screenshot(
        self,
        source: Path,
        dest: Path,
        width: int,
        height: Optional[int] = None,
        maintain_aspect: bool = True,
    ) -> Path:
        """Resize a screenshot."""
        if not _PIL_AVAILABLE:
            raise RuntimeError("Pillow is required. pip install Pillow")
        img = Image.open(str(source))
        if height is None or maintain_aspect:
            ratio = width / img.width
            new_h = int(img.height * ratio) if height is None else height
        else:
            new_h = height
        resized = img.resize((width, new_h), Image.LANCZOS)
        resized.save(str(dest))
        return dest

    def convert_image(self, source: Path, dest: Path, quality: int = 95) -> Path:
        """Convert a screenshot to a different image format."""
        if not _PIL_AVAILABLE:
            raise RuntimeError("Pillow is required. pip install Pillow")
        img = Image.open(str(source))
        fmt = dest.suffix.lstrip(".").upper()
        if fmt in ("JPG", "JPEG"):
            img.convert("RGB").save(str(dest), "JPEG", quality=quality)
        else:
            img.save(str(dest))
        return dest

    # ------------------------------------------------------------------ #
    # Video editing (ffmpeg)                                               #
    # ------------------------------------------------------------------ #

    def trim_video(
        self,
        source: Path,
        dest: Path,
        start_seconds: float,
        end_seconds: float,
        re_encode: bool = False,
    ) -> Path:
        """
        Trim a video to [start_seconds, end_seconds].
        Use re_encode=True for frame-accurate cuts (slower).
        """
        if not _ffmpeg_available():
            raise RuntimeError("ffmpeg is required for video trimming. Install from https://ffmpeg.org")
        if end_seconds > _MAX_END_SECONDS:
            raise ValueError(
                f"end_seconds ({end_seconds}) exceeds maximum allowed value ({_MAX_END_SECONDS})"
            )
        duration = end_seconds - start_seconds
        if duration <= 0:
            raise ValueError(f"end_seconds ({end_seconds}) must be > start_seconds ({start_seconds})")

        cmd = ["ffmpeg", "-y", "-ss", str(start_seconds), "-i", str(source), "-t", str(duration)]
        if re_encode:
            cmd += ["-vcodec", "libx264", "-crf", "23", "-preset", "fast", "-acodec", "aac"]
        else:
            cmd += ["-c", "copy"]
        cmd.append(str(dest))

        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        return dest

    def speed_change_video(
        self, source: Path, dest: Path, speed_factor: float
    ) -> Path:
        """
        Change video playback speed.  speed_factor=2.0 doubles speed, 0.5 halves it.
        """
        if not _ffmpeg_available():
            raise RuntimeError("ffmpeg required")
        if speed_factor <= 0:
            raise ValueError("speed_factor must be positive")

        # setpts inverse for video, atempo (0.5-2.0 per filter) for audio
        vf = f"setpts={1.0 / speed_factor:.4f}*PTS"
        af = self._build_atempo(speed_factor)
        cmd = [
            "ffmpeg", "-y", "-i", str(source),
            "-vf", vf, "-af", af,
            "-vcodec", "libx264", "-crf", "23", "-preset", "fast",
            "-acodec", "aac",
            str(dest),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        return dest

    @staticmethod
    def _build_atempo(factor: float) -> str:
        """Build atempo filter chain (each stage limited to 0.5-2.0)."""
        filters = []
        while factor > 2.0:
            filters.append("atempo=2.0")
            factor /= 2.0
        while factor < 0.5:
            filters.append("atempo=0.5")
            factor *= 2.0
        filters.append(f"atempo={factor:.4f}")
        return ",".join(filters)

    def concatenate_videos(self, sources: List[Path], dest: Path) -> Path:
        """Join multiple video clips into one."""
        if not _ffmpeg_available():
            raise RuntimeError("ffmpeg required")
        if len(sources) < 2:
            raise ValueError("At least two source files are required")

        # Write concat list
        list_path = dest.parent / f".concat_{uuid.uuid4().hex[:8]}.txt"
        lines = [f"file '{s}'" for s in sources if s.exists()]
        list_path.write_text("\n".join(lines), encoding="utf-8")
        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(list_path),
                "-c", "copy",
                str(dest),
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=600)
        finally:
            list_path.unlink(missing_ok=True)
        return dest

    def create_montage(
        self,
        clips: List[Path],
        dest: Path,
        clip_duration: float = 5.0,
        transition: bool = False,
    ) -> Path:
        """
        Create a highlight montage by trimming and concatenating clips.

        Takes the first ``clip_duration`` seconds of each clip and joins them.
        """
        if not _ffmpeg_available():
            raise RuntimeError("ffmpeg required for montage creation")

        trimmed: List[Path] = []
        temp_dir = dest.parent / ".montage_temp"
        temp_dir.mkdir(exist_ok=True)

        try:
            for i, clip in enumerate(clips):
                if not clip.exists():
                    continue
                tmp = temp_dir / f"clip_{i:04d}.mp4"
                # Get actual duration to avoid over-trimming
                try:
                    duration = self._get_video_duration(clip)
                    end = min(clip_duration, duration) if duration else clip_duration
                except Exception:
                    log.warning("Could not determine duration for %s; using clip_duration", clip, exc_info=True)
                    end = clip_duration
                try:
                    self.trim_video(clip, tmp, 0, end)
                    trimmed.append(tmp)
                except Exception:
                    log.warning("Failed to trim clip %s; skipping", clip, exc_info=True)
                    continue

            if not trimmed:
                raise RuntimeError("No valid clips found for montage")

            self.concatenate_videos(trimmed, dest)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return dest

    def _get_video_duration(self, path: Path) -> Optional[float]:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return None
        try:
            result = subprocess.run(
                [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
                capture_output=True, text=True, timeout=10,
            )
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Combined conversion for sharing                                      #
    # ------------------------------------------------------------------ #

    def optimise_for_sharing(
        self, source: Path, dest: Path, max_width: int = 1280, target_mb: float = 50.0
    ) -> Path:
        """
        Re-encode a video for web sharing at a suitable file size.
        Calculates a target bitrate from target_mb and video duration.
        """
        if not _ffmpeg_available():
            raise RuntimeError("ffmpeg required")

        duration = self._get_video_duration(source) or 60.0
        target_kbps = int((target_mb * 8 * 1024) / duration)
        target_kbps = max(500, min(target_kbps, 8000))

        cmd = [
            "ffmpeg", "-y", "-i", str(source),
            "-vf", f"scale={max_width}:-2",
            "-vcodec", "libx264",
            "-b:v", f"{target_kbps}k",
            "-preset", "slow",
            "-acodec", "aac", "-b:a", "128k",
            str(dest),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
        return dest

    # ------------------------------------------------------------------ #
    # C14 — Video format conversion                                        #
    # ------------------------------------------------------------------ #

    # Map container extension → (default_video_codec, default_audio_codec)
    _CONTAINER_CODECS: Dict[str, Tuple[str, str]] = {
        "mp4":  ("libx264", "aac"),
        "mkv":  ("libx264", "aac"),
        "mov":  ("libx264", "aac"),
        "webm": ("libvpx-vp9", "libopus"),
        "avi":  ("libxvid", "mp3"),
        "ts":   ("libx264", "aac"),
    }

    def convert_video(
        self,
        source: Path,
        dest: Path,
        video_codec: Optional[str] = None,
        audio_codec: Optional[str] = None,
    ) -> Path:
        """
        Transcode a video to a different container or codec.

        The target format is inferred from ``dest``'s file extension.
        Explicit ``video_codec`` / ``audio_codec`` override the defaults.

        Supported containers: mp4, mkv, mov, webm, avi, ts.
        Example::

            editor.convert_video(Path("clip.mp4"), Path("clip.webm"))
        """
        if not _ffmpeg_available():
            raise RuntimeError(
                "ffmpeg is required for video conversion. Install from https://ffmpeg.org"
            )

        ext = dest.suffix.lower().lstrip(".")
        default_vc, default_ac = self._CONTAINER_CODECS.get(ext, ("copy", "aac"))
        vc = video_codec or default_vc
        ac = audio_codec or default_ac

        cmd = [
            "ffmpeg", "-y",
            "-i", str(source),
            "-vcodec", vc,
            "-acodec", ac,
            str(dest),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
        return dest

    # ------------------------------------------------------------------ #
    # C10 — Highlight detection                                            #
    # ------------------------------------------------------------------ #

    def detect_highlights(
        self,
        video_path: Path,
        scene_threshold: float = 0.4,
        min_gap_seconds: float = 3.0,
    ) -> List[HighlightMoment]:
        """
        Detect highlight moments using ffmpeg's scene-change filter.

        Runs ffmpeg with ``select='gt(scene,T)'`` and parses the showinfo
        output for ``pts_time`` values that exceed the threshold.

        Parameters
        ----------
        scene_threshold:
            0.0–1.0.  Higher = fewer but more visually dramatic cuts.
        min_gap_seconds:
            Minimum gap between consecutive highlights to avoid clustering.

        Returns
        -------
        List of :class:`HighlightMoment` sorted by timestamp.
        """
        if not _ffmpeg_available():
            raise RuntimeError("ffmpeg is required for highlight detection.")

        # Clamp to valid range before interpolating into the filter string
        scene_threshold = max(0.0, min(1.0, float(scene_threshold)))

        cmd = [
            "ffmpeg", "-i", str(video_path),
            "-vf", f"select='gt(scene,{scene_threshold:.4f})',showinfo",
            "-vsync", "vfr",
            "-f", "null", "-",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300
            )
            output = result.stderr
        except subprocess.TimeoutExpired:
            return []

        moments: List[HighlightMoment] = []
        last_ts = -min_gap_seconds

        for line in output.splitlines():
            ts_match = re.search(r"pts_time:(\d+\.?\d*)", line)
            if not ts_match:
                continue
            ts = float(ts_match.group(1))
            if ts - last_ts < min_gap_seconds:
                continue
            # scene_score may appear in the select filter line
            score_match = re.search(r"scene_score[=:](\d+\.?\d*)", line)
            score = float(score_match.group(1)) if score_match else scene_threshold
            moments.append(HighlightMoment(timestamp_seconds=ts, scene_score=score))
            last_ts = ts

        return moments

    def auto_montage(
        self,
        source: Path,
        dest: Path,
        scene_threshold: float = 0.4,
        clip_duration: float = 5.0,
        min_gap_seconds: float = 3.0,
    ) -> Path:
        """
        Automatically detect highlights then assemble a montage.

        If no scene changes are detected the video is split into evenly-spaced
        segments as a fallback, so the method always produces output.

        Parameters
        ----------
        scene_threshold:
            Passed to :meth:`detect_highlights`.
        clip_duration:
            Length in seconds of each highlight clip in the montage.
        min_gap_seconds:
            Minimum gap between highlights; passed to :meth:`detect_highlights`.
        """
        moments = self.detect_highlights(source, scene_threshold, min_gap_seconds)

        if not moments:
            # Fallback: evenly-spaced segments
            total_dur = self._get_video_duration(source) or 60.0
            n_segs = max(1, int(total_dur / max(clip_duration, 1)))
            step = total_dur / n_segs
            moments = [
                HighlightMoment(timestamp_seconds=i * step, scene_score=0.0)
                for i in range(n_segs)
            ]

        temp_dir = dest.parent / f".auto_montage_{uuid.uuid4().hex[:8]}"
        temp_dir.mkdir(exist_ok=True)
        clips: List[Path] = []

        try:
            total_dur = self._get_video_duration(source) or float("inf")
            for i, moment in enumerate(moments):
                half = clip_duration / 2
                start = max(0.0, moment.timestamp_seconds - half)
                end = min(total_dur, start + clip_duration)
                if end - start < 0.5:
                    continue
                tmp = temp_dir / f"hl_{i:04d}.mp4"
                try:
                    self.trim_video(source, tmp, start, end)
                    clips.append(tmp)
                except Exception:
                    log.warning("Failed to trim highlight clip at %.2fs; skipping", start, exc_info=True)
                    continue

            if not clips:
                raise RuntimeError("No highlight clips could be extracted")

            self.concatenate_videos(clips, dest)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return dest
