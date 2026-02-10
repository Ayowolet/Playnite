"""
Instant replay buffer — continuously captures video in a rolling circular
buffer so users can "save the last N seconds" on demand.

Strategy
--------
Instead of keeping raw frames in memory (extremely RAM-heavy), the buffer
continuously writes short fixed-duration video *segments* to disk using
ffmpeg's segment muxer, keeping only the most recent N segments.
When the user triggers a save, the relevant segments are concatenated into
a final replay clip.
"""

from __future__ import annotations

import atexit
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

log = logging.getLogger(__name__)


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


@dataclass
class BufferSegment:
    """Metadata for a single buffered video segment."""
    id: str
    file_path: Path
    created_at: float = field(default_factory=time.time)
    duration_seconds: float = 0.0

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


class ReplayBuffer:
    """
    Rolling video buffer for instant-replay capture.

    Usage
    -----
        buf = ReplayBuffer(buffer_seconds=60, output_dir=Path("captures"))
        buf.start()
        # ... game plays ...
        save_path = buf.save_replay(game_name="Hollow Knight")
        buf.stop()
    """

    SEGMENT_DURATION = 10   # Each segment is 10 seconds

    def __init__(
        self,
        buffer_seconds: int = 60,
        output_dir: Optional[Path] = None,
        fps: int = 30,
        crf: int = 28,
        codec: str = "libx264",
        simulate: bool = False,
    ) -> None:
        self.buffer_seconds = buffer_seconds
        self.output_dir = output_dir or Path.home() / "Videos" / "PlayniteBuffer"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.fps = fps
        self.crf = crf
        self.codec = codec
        self.simulate = simulate

        max_segments = max(1, (buffer_seconds // self.SEGMENT_DURATION) + 2)
        self._segments: Deque[BufferSegment] = deque(maxlen=max_segments)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._buffering = False

        # Temp directory for segment files — use mkdtemp so multiple instances
        # don't collide and cleanup is unambiguous.
        self._temp_dir = Path(
            tempfile.mkdtemp(prefix="playnite_buf_", dir=self.output_dir)
        )
        atexit.register(self._atexit_stop)

    # ------------------------------------------------------------------ #
    # Start / stop                                                         #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Begin background buffering."""
        if self._buffering:
            return
        self._stop_event.clear()
        self._buffering = True

        if self.simulate or not _ffmpeg_available():
            self._thread = threading.Thread(
                target=self._simulate_loop, daemon=True, name="ReplayBuffer"
            )
        else:
            self._thread = threading.Thread(
                target=self._record_loop, daemon=True, name="ReplayBuffer"
            )
        self._thread.start()

    def stop(self) -> None:
        """Stop buffering and clean up temp segments."""
        self._stop_event.set()
        self._buffering = False
        if self._process and self._process.poll() is None:
            try:
                self._process.stdin.write(b"q")  # type: ignore[union-attr]
                self._process.stdin.flush()  # type: ignore[union-attr]
                self._process.wait(timeout=5)
            except Exception:
                log.warning("Graceful ffmpeg stop failed; terminating process", exc_info=True)
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except Exception:
                    self._process.kill()
        if self._thread:
            self._thread.join(timeout=15)
            self._thread = None
        self._cleanup_temp()

    def is_buffering(self) -> bool:
        return self._buffering

    # ------------------------------------------------------------------ #
    # Save replay                                                          #
    # ------------------------------------------------------------------ #

    def save_replay(
        self,
        game_name: Optional[str] = None,
        game_id: Optional[str] = None,
        output_path: Optional[Path] = None,
        last_n_seconds: Optional[int] = None,
    ) -> Optional[Path]:
        """
        Save the last N seconds of buffered footage to a clip.

        Returns the path to the saved clip, or None if no buffer data exists.
        """
        with self._lock:
            segments = list(self._segments)

        if not segments:
            return None

        cutoff = last_n_seconds or self.buffer_seconds
        selected = [s for s in segments if s.age_seconds <= cutoff]
        if not selected:
            selected = segments[-1:]  # At least the most recent segment

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        rid = str(uuid.uuid4())[:8]
        safe_name = (game_name or "unknown").replace(" ", "_").replace("/", "_")
        out = output_path or (self.output_dir / f"replay_{safe_name}_{ts}_{rid}.mp4")

        if self.simulate or not _ffmpeg_available():
            return self._save_simulated_replay(out, game_name, game_id)

        return self._concatenate_segments(selected, out)

    def _save_simulated_replay(
        self, out: Path, game_name: Optional[str], game_id: Optional[str]
    ) -> Optional[Path]:
        """Write a fake replay file for testing."""
        out.write_bytes(b"SIMULATED_REPLAY")
        self._write_replay_sidecar(out, game_name, game_id, duration=float(min(len(self._segments) * self.SEGMENT_DURATION, self.buffer_seconds)))
        return out

    def _concatenate_segments(
        self, segments: List[BufferSegment], output: Path
    ) -> Optional[Path]:
        """Use ffmpeg concat demuxer to join segment files."""
        # Write concat list file
        list_path = self._temp_dir / "concat_list.txt"
        valid_segments = [s for s in segments if s.file_path.exists() and s.file_path.stat().st_size > 0]
        if not valid_segments:
            return None

        lines = [f"file '{s.file_path}'" for s in valid_segments]
        list_path.write_text("\n".join(lines), encoding="utf-8")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_path),
            "-c", "copy",
            str(output),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            return output
        except Exception:
            log.error("ffmpeg concat failed for replay output %s", output, exc_info=True)
            return None

    # ------------------------------------------------------------------ #
    # Recording loops                                                      #
    # ------------------------------------------------------------------ #

    def _record_loop(self) -> None:
        """
        Continuously record segments using ffmpeg's segment muxer.
        """
        import platform
        os_name = platform.system().lower()

        segment_pattern = str(self._temp_dir / "seg_%05d.mp4")
        cmd = ["ffmpeg", "-y"]

        # Screen input
        if os_name == "darwin":
            cmd += ["-f", "avfoundation", "-framerate", str(self.fps), "-i", "1:0"]
        elif os_name == "windows":
            cmd += ["-f", "gdigrab", "-framerate", str(self.fps), "-i", "desktop"]
        else:
            cmd += ["-f", "x11grab", "-framerate", str(self.fps), "-i", ":0.0"]

        cmd += [
            "-vcodec", self.codec,
            "-crf", str(self.crf),
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-f", "segment",
            "-segment_time", str(self.SEGMENT_DURATION),
            "-segment_format", "mp4",
            "-reset_timestamps", "1",
            segment_pattern,
        ]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            log.error("Failed to start ffmpeg recording process", exc_info=True)
            self._buffering = False
            return

        last_check = time.time()
        heartbeat_count = 0
        while not self._stop_event.is_set() and self._process.poll() is None:
            # Poll for new segment files every SEGMENT_DURATION / 2
            time.sleep(self.SEGMENT_DURATION / 2)
            if time.time() - last_check >= self.SEGMENT_DURATION / 2:
                self._scan_new_segments()
                last_check = time.time()
                heartbeat_count += 1
                log.debug(
                    "ReplayBuffer heartbeat #%d: %d segment(s) buffered",
                    heartbeat_count,
                    len(self._segments),
                )

    def _scan_new_segments(self) -> None:
        """Pick up any newly-written segment files from temp dir."""
        for path in sorted(self._temp_dir.glob("seg_*.mp4")):
            try:
                if path.stat().st_size == 0:
                    continue
            except FileNotFoundError:
                continue
            with self._lock:
                # Duplicate check and append must both happen under the lock
                if any(s.file_path == path for s in self._segments):
                    continue
                seg = BufferSegment(
                    id=str(uuid.uuid4()),
                    file_path=path,
                    duration_seconds=float(self.SEGMENT_DURATION),
                )
                # deque maxlen handles eviction; delete evicted file
                if len(self._segments) == self._segments.maxlen:
                    evicted = self._segments[0]
                    try:
                        evicted.file_path.unlink(missing_ok=True)
                    except Exception:
                        log.debug("Could not delete evicted buffer segment %s", evicted.file_path)
                self._segments.append(seg)

    def _simulate_loop(self) -> None:
        """Simulate buffering by appending fake segment entries every SEGMENT_DURATION."""
        seg_idx = 0
        while not self._stop_event.is_set():
            fake_path = self._temp_dir / f"sim_seg_{seg_idx:05d}.mp4"
            # Write a tiny placeholder
            fake_path.write_bytes(b"SIM")
            seg = BufferSegment(
                id=str(uuid.uuid4()),
                file_path=fake_path,
                duration_seconds=float(self.SEGMENT_DURATION),
            )
            with self._lock:
                self._segments.append(seg)
            seg_idx += 1
            self._stop_event.wait(self.SEGMENT_DURATION)

    # ------------------------------------------------------------------ #
    # Cleanup                                                              #
    # ------------------------------------------------------------------ #

    def _atexit_stop(self) -> None:
        """Best-effort stop invoked by atexit on abnormal interpreter shutdown."""
        if self._buffering:
            try:
                self.stop()
            except Exception:
                log.debug("atexit stop raised", exc_info=True)

    def _cleanup_temp(self) -> None:
        try:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        except Exception:
            pass

    def _write_replay_sidecar(
        self, path: Path, game_name: Optional[str], game_id: Optional[str], duration: float
    ) -> None:
        import json
        sidecar = path.with_suffix(".json")
        meta = {
            "capture_type": "replay",
            "game_name": game_name,
            "game_id": game_id,
            "saved_at": datetime.utcnow().isoformat(),
            "duration_seconds": duration,
        }
        sidecar.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------ #
    # Status                                                               #
    # ------------------------------------------------------------------ #

    def status(self) -> Dict[str, Any]:
        with self._lock:
            n = len(self._segments)
            total_dur = n * self.SEGMENT_DURATION
        return {
            "buffering": self._buffering,
            "segments_buffered": n,
            "buffer_duration_seconds": min(total_dur, self.buffer_seconds),
            "configured_buffer_seconds": self.buffer_seconds,
            "simulate": self.simulate,
            "ffmpeg_available": _ffmpeg_available(),
        }
