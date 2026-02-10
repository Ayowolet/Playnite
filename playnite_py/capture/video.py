"""
Video recording via ffmpeg subprocess.

Requires ffmpeg to be installed on the system PATH.
Falls back gracefully when ffmpeg is unavailable (useful for testing).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


@dataclass
class VideoRecordingResult:
    """Metadata about a completed video recording."""
    id: str
    file_path: Path
    sidecar_path: Path
    duration_seconds: float
    file_size_bytes: int
    width: int
    height: int
    fps: int
    codec: str
    started_at: datetime
    ended_at: datetime
    game_name: Optional[str]
    game_id: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "file_path": str(self.file_path),
            "duration_seconds": round(self.duration_seconds, 2),
            "file_size_bytes": self.file_size_bytes,
            "resolution": f"{self.width}x{self.height}",
            "fps": self.fps,
            "codec": self.codec,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "game_name": self.game_name,
            "game_id": self.game_id,
        }


@dataclass
class RecordingSession:
    """Tracks an in-progress recording."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    process: Optional[subprocess.Popen] = field(default=None, repr=False)
    output_path: Optional[Path] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    game_name: Optional[str] = None
    game_id: Optional[str] = None
    width: int = 1920
    height: int = 1080
    fps: int = 30
    codec: str = "libx264"
    _thread: Optional[threading.Thread] = field(default=None, repr=False)

    @property
    def is_recording(self) -> bool:
        return self.process is not None and self.process.poll() is None


class VideoRecorder:
    """
    Record gameplay video using ffmpeg.

    The recorder captures the desktop/screen at the specified settings.
    For cross-platform compatibility it uses:
    - macOS:   avfoundation input (screen capture)
    - Windows: gdigrab input
    - Linux:   x11grab input

    Usage
    -----
        rec = VideoRecorder(output_dir=Path("captures"))
        rec.start_recording(game_name="Hollow Knight")
        # ... game plays ...
        result = rec.stop_recording()
        print(result.file_path)
    """

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        codec: str = "libx264",
        crf: int = 23,
        fps: int = 30,
        resolution: Optional[str] = None,  # e.g. "1920x1080"
        audio: bool = True,
        audio_codec: str = "aac",
    ) -> None:
        self.output_dir = output_dir or Path.home() / "Videos" / "PlayniteCaptures"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.codec = codec
        self.crf = crf
        self.fps = fps
        self.resolution = resolution
        self.audio = audio
        self.audio_codec = audio_codec
        self._session: Optional[RecordingSession] = None

    # ------------------------------------------------------------------ #
    # Start / stop                                                         #
    # ------------------------------------------------------------------ #

    def start_recording(
        self,
        game_name: Optional[str] = None,
        game_id: Optional[str] = None,
        output_path: Optional[Path] = None,
        duration_limit: Optional[int] = None,
        simulate: bool = False,
    ) -> RecordingSession:
        """
        Begin a recording session.

        Parameters
        ----------
        simulate:
            Skip actual ffmpeg call (for unit tests).
        duration_limit:
            Maximum recording duration in seconds (None = unlimited).
        """
        if self.is_recording():
            raise RuntimeError("A recording is already in progress")

        session_id = str(uuid.uuid4())
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        fname = output_path or self.output_dir / f"recording_{ts}_{session_id[:8]}.mp4"

        width, height = 1920, 1080
        if self.resolution:
            try:
                w, h = self.resolution.split("x")
                width, height = int(w), int(h)
            except ValueError:
                pass

        session = RecordingSession(
            id=session_id,
            output_path=fname,
            started_at=datetime.utcnow(),
            game_name=game_name,
            game_id=game_id,
            width=width,
            height=height,
            fps=self.fps,
            codec=self.codec,
        )

        if simulate or not _ffmpeg_available():
            # Write an empty placeholder for testing
            fname.write_bytes(b"")
        else:
            cmd = self._build_ffmpeg_command(fname, duration_limit)
            try:
                session.process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as exc:
                raise RuntimeError(f"Failed to start ffmpeg: {exc}") from exc

        self._session = session
        return session

    def stop_recording(self) -> Optional[VideoRecordingResult]:
        """Stop the current recording and return the result."""
        if not self._session:
            return None

        session = self._session
        ended_at = datetime.utcnow()

        if session.process and session.process.poll() is None:
            try:
                # Send 'q' to ffmpeg stdin to gracefully stop
                session.process.stdin.write(b"q")  # type: ignore[union-attr]
                session.process.stdin.flush()  # type: ignore[union-attr]
                session.process.wait(timeout=10)
            except Exception:
                session.process.terminate()
                try:
                    session.process.wait(timeout=5)
                except Exception:
                    session.process.kill()

        self._session = None

        output_path = session.output_path
        if not output_path:
            return None

        duration = (ended_at - session.started_at).total_seconds()
        file_size = output_path.stat().st_size if output_path.exists() else 0

        sidecar = self._write_sidecar(output_path, session, ended_at, duration, file_size)

        return VideoRecordingResult(
            id=session.id,
            file_path=output_path,
            sidecar_path=sidecar,
            duration_seconds=duration,
            file_size_bytes=file_size,
            width=session.width,
            height=session.height,
            fps=session.fps,
            codec=session.codec,
            started_at=session.started_at,
            ended_at=ended_at,
            game_name=session.game_name,
            game_id=session.game_id,
        )

    def is_recording(self) -> bool:
        if self._session is None:
            return False
        if self._session.process is not None:
            return self._session.process.poll() is None
        # Simulated session (no real process) — still considered active
        return self._session.output_path is not None

    def get_session(self) -> Optional[RecordingSession]:
        return self._session

    # ------------------------------------------------------------------ #
    # ffmpeg command builder                                               #
    # ------------------------------------------------------------------ #

    def _build_ffmpeg_command(
        self, output: Path, duration_limit: Optional[int] = None
    ) -> List[str]:
        import platform
        os_name = platform.system().lower()

        cmd = ["ffmpeg", "-y"]

        # Input flags per platform
        if os_name == "darwin":
            cmd += ["-f", "avfoundation", "-framerate", str(self.fps), "-i", "1:0"]
        elif os_name == "windows":
            cmd += ["-f", "gdigrab", "-framerate", str(self.fps), "-i", "desktop"]
        else:  # Linux
            cmd += ["-f", "x11grab", "-framerate", str(self.fps), "-i", ":0.0"]

        if self.audio:
            if os_name == "darwin":
                # Already included :0 above; add separate audio if needed
                pass
            elif os_name == "windows":
                cmd += ["-f", "dshow", "-i", "audio=Stereo Mix"]
            else:
                cmd += ["-f", "pulse", "-i", "default"]

        if self.resolution:
            cmd += ["-s", self.resolution]

        # Encode flags
        cmd += [
            "-vcodec", self.codec,
            "-crf", str(self.crf),
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
        ]

        if self.audio:
            cmd += ["-acodec", self.audio_codec]

        if duration_limit:
            cmd += ["-t", str(duration_limit)]

        cmd.append(str(output))
        return cmd

    # ------------------------------------------------------------------ #
    # Video editing helpers (via ffmpeg)                                  #
    # ------------------------------------------------------------------ #

    def trim(
        self, source: Path, dest: Path, start_seconds: float, end_seconds: float
    ) -> Path:
        """Trim a video clip to [start, end] seconds."""
        if not _ffmpeg_available():
            raise RuntimeError("ffmpeg is required for trimming")
        duration = end_seconds - start_seconds
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_seconds),
            "-i", str(source),
            "-t", str(duration),
            "-c", "copy",
            str(dest),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return dest

    def convert(self, source: Path, dest: Path, fmt: str = "mp4") -> Path:
        """Convert a video to a different container format."""
        if not _ffmpeg_available():
            raise RuntimeError("ffmpeg is required for conversion")
        cmd = ["ffmpeg", "-y", "-i", str(source), str(dest)]
        subprocess.run(cmd, check=True, capture_output=True)
        return dest

    def get_duration(self, video_path: Path) -> Optional[float]:
        """Return duration in seconds using ffprobe."""
        ffprobe = shutil.which("ffprobe")
        if not ffprobe or not video_path.exists():
            return None
        try:
            result = subprocess.run(
                [
                    ffprobe, "-v", "quiet",
                    "-print_format", "json",
                    "-show_format", str(video_path),
                ],
                capture_output=True, text=True, timeout=10,
            )
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Sidecar                                                              #
    # ------------------------------------------------------------------ #

    def _write_sidecar(
        self,
        video_path: Path,
        session: RecordingSession,
        ended_at: datetime,
        duration: float,
        file_size: int,
    ) -> Path:
        sidecar = video_path.with_suffix(".json")
        meta = {
            "id": session.id,
            "capture_type": "video",
            "game_name": session.game_name,
            "game_id": session.game_id,
            "started_at": session.started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "duration_seconds": round(duration, 2),
            "resolution": f"{session.width}x{session.height}",
            "fps": session.fps,
            "codec": session.codec,
            "file_size_bytes": file_size,
        }
        sidecar.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return sidecar

    @staticmethod
    def ffmpeg_available() -> bool:
        return _ffmpeg_available()
