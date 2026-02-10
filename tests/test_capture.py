"""
Unit and integration tests for the screenshot and video capture system.

Run with:
    pytest tests/test_capture.py -v

Tests cover:
- Screenshot capture (mock backend, no display required)
- Video recorder (simulate mode, no ffmpeg required)
- Replay buffer (simulate mode)
- Game detector (simulation mode, no psutil required for basic tests)
- Media organizer
- Media editor (mocked operations)
- Media uploader (local_copy and simulated backends)
- Full capture pipeline integration
- CLI capture commands
"""

from __future__ import annotations

import json
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pytest

from playnite_py.capture.achievement import AchievementDetector, AchievementCapture
from playnite_py.capture.detector import GameDetector, RunningGame
from playnite_py.capture.editor import MediaEditor, HighlightMoment
from playnite_py.capture.hotkeys import HotkeyListener, _normalise_key
from playnite_py.capture.organizer import MediaOrganizer, _safe_dirname
from playnite_py.capture.overlay import CaptureOverlay
from playnite_py.capture.screenshot import ScreenshotCapture, ScreenshotResult
from playnite_py.capture.uploader import MediaUploader
from playnite_py.capture.video import VideoRecorder
from playnite_py.capture.buffer import ReplayBuffer
from playnite_py.config import AppConfig


# ================================================================== #
# Fixtures                                                             #
# ================================================================== #

@pytest.fixture
def tmp_captures(tmp_path: Path) -> Path:
    d = tmp_path / "captures"
    d.mkdir()
    return d


@pytest.fixture
def screenshot_capture(tmp_captures: Path) -> ScreenshotCapture:
    return ScreenshotCapture(output_dir=tmp_captures, fmt="png", backend="mock")


@pytest.fixture
def video_recorder(tmp_captures: Path) -> VideoRecorder:
    return VideoRecorder(output_dir=tmp_captures / "videos")


@pytest.fixture
def replay_buffer(tmp_captures: Path) -> ReplayBuffer:
    return ReplayBuffer(
        buffer_seconds=30,
        output_dir=tmp_captures / "replays",
        simulate=True,
    )


@pytest.fixture
def organizer(tmp_captures: Path) -> MediaOrganizer:
    return MediaOrganizer(captures_root=tmp_captures)


@pytest.fixture
def editor(tmp_captures: Path) -> MediaEditor:
    return MediaEditor()


# ================================================================== #
# Game Detector                                                        #
# ================================================================== #

class TestGameDetector:

    def test_simulate_game_start(self):
        detector = GameDetector()
        game = detector.simulate_game_start("Hollow Knight", game_id="hk001", pid=12345)

        assert game.game_name == "Hollow Knight"
        assert game.game_id == "hk001"
        assert game.process_id == 12345

        running = detector.get_running_games()
        assert any(g.process_id == 12345 for g in running)

    def test_simulate_game_stop(self):
        detector = GameDetector()
        detector.simulate_game_start("Test Game", pid=99998)
        detector.simulate_game_stop(pid=99998)

        running = detector.get_running_games()
        assert not any(g.process_id == 99998 for g in running)

    def test_callbacks_fired(self):
        started = []
        stopped = []

        detector = GameDetector()
        detector.on_game_start(lambda g: started.append(g.game_name))
        detector.on_game_stop(lambda g: stopped.append(g.game_name))

        detector.simulate_game_start("MyGame", pid=11111)
        assert "MyGame" in started

        detector.simulate_game_stop(pid=11111)
        assert "MyGame" in stopped

    def test_status_not_monitoring_by_default(self):
        detector = GameDetector()
        status = detector.status()
        assert status["monitoring"] is False

    def test_start_stop_monitoring(self):
        detector = GameDetector(poll_interval=100)  # Very long interval, won't tick
        detector.start()
        assert detector.is_running()
        detector.stop()
        assert not detector.is_running()

    def test_detect_returns_list(self):
        detector = GameDetector()
        # Without psutil, should return whatever is in _running dict (empty)
        result = detector.detect_running_games()
        assert isinstance(result, list)

    def test_running_game_uptime(self):
        game = RunningGame(
            process_id=1,
            executable="test.exe",
            started_at=time.time() - 10,
        )
        assert game.uptime_seconds >= 10

    def test_multiple_simulated_games(self):
        detector = GameDetector()
        detector.simulate_game_start("Game A", pid=1001)
        detector.simulate_game_start("Game B", pid=1002)
        running = detector.get_running_games()
        assert len(running) >= 2

    def test_add_known_patterns(self):
        detector = GameDetector()
        detector.add_known_patterns([r"my_special_game"])
        # Patterns are stored
        assert len(detector._patterns) > 0

    def test_register_game(self):
        detector = GameDetector()
        detector.register_game("my_game\\.exe", "My Special Game")
        # Pattern is stored as-is; verify lookup works via the regex match
        name = detector._lookup_game_name("my_game.exe")
        assert name == "My Special Game"


# ================================================================== #
# Screenshot Capture                                                   #
# ================================================================== #

class TestScreenshotCapture:

    def test_capture_creates_file(self, screenshot_capture: ScreenshotCapture, tmp_captures: Path):
        result = screenshot_capture.capture(game_name="Test Game", game_id="game1")
        assert result.file_path.exists(), f"Screenshot file not created at {result.file_path}"
        assert result.file_size_bytes >= 0

    def test_capture_creates_sidecar(self, screenshot_capture: ScreenshotCapture):
        result = screenshot_capture.capture(game_name="Test Game")
        assert result.sidecar_path.exists(), "Sidecar JSON not created"
        meta = json.loads(result.sidecar_path.read_text())
        assert meta["capture_type"] == "screenshot"
        assert meta["game_name"] == "Test Game"

    def test_capture_result_fields(self, screenshot_capture: ScreenshotCapture):
        result = screenshot_capture.capture(game_name="My Game", game_id="g42")
        assert result.id
        assert result.game_name == "My Game"
        assert result.game_id == "g42"
        assert result.backend == "mock"
        assert isinstance(result.captured_at, datetime)

    def test_capture_to_dict(self, screenshot_capture: ScreenshotCapture):
        result = screenshot_capture.capture()
        d = result.to_dict()
        assert "id" in d
        assert "file_path" in d
        assert "width" in d
        assert "backend" in d

    def test_available_backends_includes_mock(self, screenshot_capture: ScreenshotCapture):
        backends = screenshot_capture.get_available_backends()
        assert "mock" in backends

    def test_backend_detection(self):
        cap = ScreenshotCapture(backend="mock")
        assert cap.backend == "mock"

    def test_multiple_screenshots(self, screenshot_capture: ScreenshotCapture, tmp_captures: Path):
        results = [screenshot_capture.capture(game_name=f"Game {i}") for i in range(3)]
        paths = {r.file_path for r in results}
        assert len(paths) == 3, "Each screenshot should have a unique path"

    def test_sidecar_contains_resolution(self, screenshot_capture: ScreenshotCapture):
        result = screenshot_capture.capture()
        meta = json.loads(result.sidecar_path.read_text())
        assert "resolution" in meta

    def test_capture_without_game_name(self, screenshot_capture: ScreenshotCapture):
        result = screenshot_capture.capture()
        assert result.file_path.exists()
        assert result.game_name is None

    def test_minimal_png_bytes_valid(self):
        data = ScreenshotCapture._minimal_png_bytes()
        assert data[:4] == b'\x89PNG'


# ================================================================== #
# Video Recorder                                                       #
# ================================================================== #

class TestVideoRecorder:

    def test_start_and_stop_simulate(self, video_recorder: VideoRecorder):
        session = video_recorder.start_recording(
            game_name="Test Game", simulate=True
        )
        assert session is not None
        assert session.id
        assert video_recorder.is_recording()

        result = video_recorder.stop_recording()
        assert result is not None
        assert result.game_name == "Test Game"

    def test_stop_without_start_returns_none(self, video_recorder: VideoRecorder):
        result = video_recorder.stop_recording()
        assert result is None

    def test_double_start_raises(self, video_recorder: VideoRecorder):
        video_recorder.start_recording(simulate=True)
        with pytest.raises(RuntimeError, match="already in progress"):
            video_recorder.start_recording(simulate=True)
        video_recorder.stop_recording()

    def test_result_fields(self, video_recorder: VideoRecorder):
        video_recorder.start_recording(game_name="My Game", game_id="g1", simulate=True)
        result = video_recorder.stop_recording()
        assert result is not None
        assert result.game_name == "My Game"
        assert result.game_id == "g1"
        assert isinstance(result.started_at, datetime)
        assert isinstance(result.ended_at, datetime)
        assert result.duration_seconds >= 0

    def test_result_to_dict(self, video_recorder: VideoRecorder):
        video_recorder.start_recording(simulate=True)
        result = video_recorder.stop_recording()
        assert result is not None
        d = result.to_dict()
        assert "file_path" in d
        assert "duration_seconds" in d
        assert "codec" in d

    def test_sidecar_created(self, video_recorder: VideoRecorder):
        video_recorder.start_recording(game_name="Sidecar Test", simulate=True)
        result = video_recorder.stop_recording()
        assert result is not None
        # Sidecar should exist
        assert result.sidecar_path.exists() or not result.file_path.exists()

    def test_ffmpeg_availability_check(self):
        from playnite_py.capture.video import _ffmpeg_available
        # Should return bool without crashing
        available = _ffmpeg_available()
        assert isinstance(available, bool)

    def test_build_ffmpeg_command(self, video_recorder: VideoRecorder, tmp_captures: Path):
        cmd = video_recorder._build_ffmpeg_command(tmp_captures / "test.mp4")
        assert "ffmpeg" in cmd
        assert str(tmp_captures / "test.mp4") in cmd


# ================================================================== #
# Replay Buffer                                                        #
# ================================================================== #

class TestReplayBuffer:

    def test_start_and_stop(self, replay_buffer: ReplayBuffer):
        replay_buffer.start()
        assert replay_buffer.is_buffering()
        replay_buffer.stop()
        assert not replay_buffer.is_buffering()

    def test_save_replay_after_buffering(self, replay_buffer: ReplayBuffer, tmp_captures: Path):
        replay_buffer.start()
        time.sleep(0.2)  # Allow a simulated segment to be written
        result = replay_buffer.save_replay(game_name="Test Game")
        replay_buffer.stop()
        # May or may not have segments yet due to timing, but should not raise
        # If a result was saved, the file should exist
        if result is not None:
            assert result.exists()  # simulated replay writes actual bytes to disk

    def test_save_replay_without_buffer_returns_none(self, tmp_captures: Path):
        buf = ReplayBuffer(buffer_seconds=30, output_dir=tmp_captures, simulate=True)
        # Don't start, so no segments
        result = buf.save_replay()
        assert result is None

    def test_status_fields(self, replay_buffer: ReplayBuffer):
        status = replay_buffer.status()
        assert "buffering" in status
        assert "segments_buffered" in status
        assert "buffer_duration_seconds" in status
        assert "configured_buffer_seconds" in status

    def test_buffer_segment_count(self, replay_buffer: ReplayBuffer):
        replay_buffer.start()
        # Simulated segments are created every SEGMENT_DURATION seconds
        # With simulate=True and SEGMENT_DURATION=10, we need to wait
        # Just check status returns without crashing
        status = replay_buffer.status()
        assert status["configured_buffer_seconds"] == 30
        replay_buffer.stop()

    def test_double_start_is_idempotent(self, replay_buffer: ReplayBuffer):
        replay_buffer.start()
        replay_buffer.start()  # Should not raise
        assert replay_buffer.is_buffering()
        replay_buffer.stop()


# ================================================================== #
# Media Organizer                                                      #
# ================================================================== #

class TestMediaOrganizer:

    def test_safe_dirname(self):
        assert _safe_dirname("Hollow Knight") == "Hollow_Knight"
        assert _safe_dirname("The Witcher 3: Wild Hunt") == "The_Witcher_3_Wild_Hunt"
        assert _safe_dirname('Game/With\\Special<>Chars') == "GameWithSpecialChars"
        assert _safe_dirname("") == "UnknownGame"

    def test_get_game_dir(self, organizer: MediaOrganizer):
        d = organizer.get_game_dir("Celeste")
        assert d == organizer.root / "Celeste"

    def test_get_capture_dir_creates_dir(self, organizer: MediaOrganizer):
        d = organizer.get_capture_dir("Hollow Knight", "screenshots")
        assert d.exists()
        assert "Hollow_Knight" in str(d)
        assert "screenshots" in str(d)

    def test_organise_screenshot(self, organizer: MediaOrganizer, tmp_captures: Path):
        # Create a fake screenshot
        fake_screenshot = tmp_captures / "fake_screenshot.png"
        fake_screenshot.write_bytes(ScreenshotCapture._minimal_png_bytes())

        dest = organizer.organise_screenshot(fake_screenshot, "Test Game")
        assert dest.exists()
        assert "Test_Game" in str(dest)

    def test_list_captures_empty(self, organizer: MediaOrganizer):
        captures = organizer.list_captures()
        assert isinstance(captures, list)

    def test_list_captures_after_organise(self, organizer: MediaOrganizer, tmp_captures: Path):
        for i in range(3):
            fake = tmp_captures / f"shot_{i}.png"
            fake.write_bytes(ScreenshotCapture._minimal_png_bytes())
            organizer.organise_screenshot(fake, "My Game")

        captures = organizer.list_captures(game_name="My Game")
        assert len(captures) == 3

    def test_storage_usage(self, organizer: MediaOrganizer, tmp_captures: Path):
        fake = tmp_captures / "shot.png"
        fake.write_bytes(b"x" * 1024)
        organizer.organise_screenshot(fake, "Big Game")

        usage = organizer.get_storage_usage()
        assert "total_bytes" in usage
        assert "total_gb" in usage
        assert usage["total_bytes"] >= 0

    def test_cleanup_dry_run(self, organizer: MediaOrganizer, tmp_captures: Path):
        fake = tmp_captures / "old_shot.png"
        fake.write_bytes(b"old_data")
        organizer.organise_screenshot(fake, "Test Game")

        result = organizer.cleanup_old_captures(max_age_days=0, dry_run=True)
        assert result["dry_run"] is True
        assert isinstance(result["deleted_count"], int)

    def test_cleanup_removes_old_files(self, organizer: MediaOrganizer, tmp_captures: Path):
        import os
        fake = tmp_captures / "old_shot.png"
        fake.write_bytes(b"old_data")
        dest = organizer.organise_screenshot(fake, "Test Game")

        # Backdate the file so cleanup_old_captures definitively considers it expired
        ancient = time.time() - 86400 * 10  # 10 days ago
        os.utime(dest, (ancient, ancient))

        result = organizer.cleanup_old_captures(max_age_days=5, dry_run=False)
        assert result["deleted_count"] >= 1
        assert not dest.exists()

    def test_html_gallery_created(self, organizer: MediaOrganizer, tmp_captures: Path):
        for i in range(2):
            fake = tmp_captures / f"shot_{i}.png"
            fake.write_bytes(ScreenshotCapture._minimal_png_bytes())
            organizer.organise_screenshot(fake, "Gallery Game")

        gallery_path = organizer.create_html_gallery("Gallery Game")
        assert gallery_path.exists()
        content = gallery_path.read_text()
        assert "Gallery Game" in content

    def test_list_game_names(self, organizer: MediaOrganizer, tmp_captures: Path):
        for game in ["Game Alpha", "Game Beta"]:
            fake = tmp_captures / f"{game.replace(' ', '_')}.png"
            fake.write_bytes(b"data")
            organizer.organise_screenshot(fake, game)

        names = organizer.list_game_names()
        assert len(names) >= 2


# ================================================================== #
# Media Editor                                                         #
# ================================================================== #

class TestMediaEditor:

    def test_trim_requires_ffmpeg(self, tmp_path: Path):
        """trim_video should raise RuntimeError if ffmpeg not available."""
        from unittest.mock import patch
        editor = MediaEditor()
        src = tmp_path / "src.mp4"
        dst = tmp_path / "dst.mp4"
        src.write_bytes(b"fake video")

        with patch("playnite_py.capture.editor._ffmpeg_available", return_value=False):
            with pytest.raises(RuntimeError, match="ffmpeg"):
                editor.trim_video(src, dst, 0, 5)

    def test_crop_screenshot_requires_pil(self, tmp_path: Path):
        """crop_screenshot should raise if PIL not available."""
        from unittest.mock import patch
        editor = MediaEditor()
        src = tmp_path / "src.png"
        dst = tmp_path / "dst.png"
        src.write_bytes(ScreenshotCapture._minimal_png_bytes())

        with patch("playnite_py.capture.editor._PIL_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="Pillow"):
                editor.crop_screenshot(src, dst, (0, 0, 1, 1))

    def test_build_atempo_simple(self):
        result = MediaEditor._build_atempo(2.0)
        assert "atempo=2.0" in result

    def test_build_atempo_fast(self):
        result = MediaEditor._build_atempo(4.0)
        # Should chain multiple atempo filters
        assert result.count("atempo") >= 2

    def test_build_atempo_slow(self):
        result = MediaEditor._build_atempo(0.25)
        assert result.count("atempo") >= 2

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("PIL"),
        reason="Pillow not installed"
    )
    def test_crop_screenshot_with_pil(self, tmp_path: Path):
        from PIL import Image
        img = Image.new("RGB", (100, 100), color=(128, 64, 32))
        src = tmp_path / "src.png"
        dst = tmp_path / "dst.png"
        img.save(str(src))

        editor = MediaEditor()
        result = editor.crop_screenshot(src, dst, (10, 10, 50, 50))
        assert result.exists()
        cropped = Image.open(str(result))
        assert cropped.size == (40, 40)

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("PIL"),
        reason="Pillow not installed"
    )
    def test_resize_screenshot(self, tmp_path: Path):
        from PIL import Image
        img = Image.new("RGB", (400, 225), color=(100, 100, 200))
        src = tmp_path / "src.png"
        dst = tmp_path / "dst.png"
        img.save(str(src))

        editor = MediaEditor()
        result = editor.resize_screenshot(src, dst, width=200)
        assert result.exists()
        resized = Image.open(str(result))
        assert resized.width == 200

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("PIL"),
        reason="Pillow not installed"
    )
    def test_annotate_screenshot(self, tmp_path: Path):
        from PIL import Image
        img = Image.new("RGB", (400, 300), color=(50, 50, 50))
        src = tmp_path / "src.png"
        dst = tmp_path / "dst.png"
        img.save(str(src))

        editor = MediaEditor()
        result = editor.annotate_screenshot(src, dst, "Hello World!")
        assert result.exists()


# ================================================================== #
# Media Uploader                                                       #
# ================================================================== #

class TestMediaUploader:

    def test_simulated_upload(self, tmp_path: Path):
        uploader = MediaUploader({"type": "simulated"})
        fake = tmp_path / "shot.png"
        fake.write_bytes(b"fake_image_data")

        result = uploader.upload(fake, game_name="Test Game")
        assert result.success
        assert "simulated://" in result.destination
        assert result.bytes_transferred >= 0

    def test_local_copy_upload(self, tmp_path: Path):
        dest_dir = tmp_path / "uploads"
        uploader = MediaUploader({"type": "local_copy", "dest_dir": str(dest_dir)})
        fake = tmp_path / "shot.png"
        fake.write_bytes(b"fake_image_data_for_upload")

        result = uploader.upload(fake, game_name="Game A")
        assert result.success
        assert dest_dir.exists()
        assert result.bytes_transferred > 0

    def test_local_copy_nonexistent_file(self, tmp_path: Path):
        dest_dir = tmp_path / "uploads"
        uploader = MediaUploader({"type": "local_copy", "dest_dir": str(dest_dir)})
        fake = tmp_path / "nonexistent.png"

        # Should succeed but with 0 bytes transferred (no file to copy)
        result = uploader.upload(fake, game_name="Game A")
        # File doesn't exist, copy may fail gracefully
        assert result.upload_type == "local_copy"

    def test_upload_too_large_file(self, tmp_path: Path):
        uploader = MediaUploader({"type": "simulated", "max_size_mb": 0.000001})
        fake = tmp_path / "big.png"
        fake.write_bytes(b"x" * 10000)  # 10KB, > 0.000001 MB

        result = uploader.upload(fake)
        assert not result.success
        assert "exceeds" in (result.error_message or "")

    def test_batch_upload(self, tmp_path: Path):
        uploader = MediaUploader({"type": "simulated"})
        files = []
        for i in range(3):
            f = tmp_path / f"shot_{i}.png"
            f.write_bytes(b"data")
            files.append(f)

        results = uploader.upload_batch(files, game_name="Batch Game")
        assert len(results) == 3
        assert all(r.success for r in results)

    def test_upload_result_to_dict(self, tmp_path: Path):
        uploader = MediaUploader({"type": "simulated"})
        fake = tmp_path / "shot.png"
        fake.write_bytes(b"data")
        result = uploader.upload(fake)
        d = result.to_dict()
        assert "success" in d
        assert "destination" in d
        assert "upload_type" in d

    def test_share_gallery(self, tmp_path: Path):
        uploader = MediaUploader({"type": "simulated"})
        files = [tmp_path / f"shot_{i}.png" for i in range(3)]
        for f in files:
            f.write_bytes(b"data")

        summary = uploader.share_gallery("Game X", files)
        assert summary["total"] == 3
        assert summary["success"] == 3


# ================================================================== #
# Full capture pipeline integration                                    #
# ================================================================== #

class TestCapturePipeline:

    def test_screenshot_capture_and_organise(self, tmp_path: Path):
        """End-to-end: capture screenshot → organise → list."""
        captures_root = tmp_path / "captures"
        cap = ScreenshotCapture(output_dir=tmp_path / "temp", backend="mock")
        organiser = MediaOrganizer(captures_root)

        result = cap.capture(game_name="Hollow Knight", game_id="hk001")
        dest = organiser.organise_screenshot(result.file_path, "Hollow Knight", "hk001")

        captures = organiser.list_captures(game_name="Hollow Knight")
        assert len(captures) == 1
        assert Path(captures[0]["file_path"]).name == dest.name

    def test_simulate_game_then_capture(self, tmp_path: Path):
        """Simulate a game running, then capture screenshot."""
        detector = GameDetector()
        detector.simulate_game_start("Celeste", game_id="cel001")

        running = detector.get_running_games()
        assert len(running) == 1
        game = running[0]

        cap = ScreenshotCapture(output_dir=tmp_path, backend="mock")
        result = cap.capture(game_name=game.game_name, game_id=game.game_id)
        assert result.game_name == "Celeste"
        assert result.file_path.exists()

    def test_video_record_then_upload(self, tmp_path: Path):
        """Simulate video recording followed by upload."""
        rec = VideoRecorder(output_dir=tmp_path / "videos")
        rec.start_recording(game_name="Elden Ring", simulate=True)
        result = rec.stop_recording()
        assert result is not None

        uploader = MediaUploader({"type": "simulated"})
        upload_result = uploader.upload(result.file_path, game_name="Elden Ring")
        assert upload_result.success

    def test_replay_buffer_pipeline(self, tmp_path: Path):
        """Start buffer, wait, save replay."""
        buf = ReplayBuffer(
            buffer_seconds=10,
            output_dir=tmp_path / "replays",
            simulate=True,
        )
        buf.start()
        time.sleep(0.1)  # Let the sim thread tick

        status = buf.status()
        assert status["buffering"] is True

        # Try saving even without segments (should handle gracefully)
        replay = buf.save_replay(game_name="Test")
        buf.stop()
        # replay may be None if no segments yet

    def test_full_library_then_capture(self, tmp_path: Path):
        """Create library, import games, then capture for a specific game."""
        from playnite_py.library.manager import LibraryManager
        from playnite_py.models.game import Game

        cfg = AppConfig()
        cfg.data_dir = str(tmp_path / "data")
        cfg.ensure_dirs()

        mgr = LibraryManager(cfg)
        game = Game(id="cel1", name="Celeste", genres=["Platformer"],
                    is_owned=True, playtime_seconds=1800, play_count=1)
        mgr.add_game(game)

        cap = ScreenshotCapture(output_dir=tmp_path / "caps", backend="mock")
        result = cap.capture(game_name="Celeste", game_id="cel1")

        found_game = mgr.get_game("cel1")
        assert found_game is not None
        assert result.file_path.exists()


# ================================================================== #
# CLI capture tests                                                    #
# ================================================================== #

class TestCaptureCLI:

    def test_capture_screenshot_json(self, tmp_path: Path):
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "capture", "screenshot",
            "--backend", "mock",
            "--game", "Test Game",
            "--no-auto-organise",
        ])
        assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"
        data = json.loads(result.output)
        assert "file_path" in data

    def test_capture_detect_json(self, tmp_path: Path):
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "capture", "detect",
            "--simulate", "Hollow Knight",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["name"] == "Hollow Knight"

    def test_capture_storage_json(self, tmp_path: Path):
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "capture", "storage",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total_bytes" in data

    def test_capture_cleanup_dry_run_json(self, tmp_path: Path):
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "capture", "cleanup",
            "--max-age-days", "90",
            "--dry-run",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["dry_run"] is True

    def test_capture_list_json(self, tmp_path: Path):
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "capture", "list",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_capture_buffer_status_json(self, tmp_path: Path):
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "capture", "buffer-status",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "buffering" in data

    def test_capture_start_recording_simulate(self, tmp_path: Path):
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "capture", "start-recording",
            "--game", "Test Game",
            "--simulate",
        ])
        assert result.exit_code == 0, f"Failed: {result.output}"
        data = json.loads(result.output)
        assert "session_id" in data


# ================================================================== #
# C14 — Video format conversion tests                                  #
# ================================================================== #

class TestVideoConversion:

    def test_convert_video_no_ffmpeg(self, tmp_path: Path):
        """convert_video raises RuntimeError when ffmpeg is absent."""
        import unittest.mock as mock
        editor = MediaEditor()
        src = tmp_path / "clip.mp4"
        src.write_bytes(b"")
        dest = tmp_path / "clip.webm"
        with mock.patch("playnite_py.capture.editor.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="ffmpeg"):
                editor.convert_video(src, dest)

    def test_convert_video_codec_map_mp4(self):
        """MP4 container maps to libx264 + aac by default."""
        editor = MediaEditor()
        vc, ac = editor._CONTAINER_CODECS["mp4"]
        assert vc == "libx264"
        assert ac == "aac"

    def test_convert_video_codec_map_webm(self):
        """WebM container maps to libvpx-vp9 + libopus."""
        editor = MediaEditor()
        vc, ac = editor._CONTAINER_CODECS["webm"]
        assert vc == "libvpx-vp9"
        assert ac == "libopus"

    def test_convert_video_codec_override(self, tmp_path: Path):
        """Explicit codec override is respected."""
        import unittest.mock as mock
        editor = MediaEditor()
        src = tmp_path / "a.mp4"
        src.write_bytes(b"")
        dest = tmp_path / "b.mp4"
        captured_cmd = []

        def fake_run(cmd, **kw):
            captured_cmd.extend(cmd)
            class R:
                returncode = 0
            return R()

        with mock.patch("playnite_py.capture.editor.subprocess.run", side_effect=fake_run):
            with mock.patch("playnite_py.capture.editor.shutil.which", return_value="/usr/bin/ffmpeg"):
                editor.convert_video(src, dest, video_codec="libx265", audio_codec="aac")

        assert "libx265" in captured_cmd

    def test_convert_video_unknown_extension_uses_copy(self):
        """Unknown container extension falls back to 'copy' for video codec."""
        editor = MediaEditor()
        vc, ac = editor._CONTAINER_CODECS.get("xyz", ("copy", "aac"))
        assert vc == "copy"


# ================================================================== #
# C10 — Highlight detection tests                                      #
# ================================================================== #

class TestHighlightDetection:

    def test_highlight_moment_to_dict(self):
        m = HighlightMoment(timestamp_seconds=12.345, scene_score=0.62)
        d = m.to_dict()
        assert d["timestamp_seconds"] == 12.345
        assert d["scene_score"] == 0.62

    def test_detect_highlights_no_ffmpeg(self, tmp_path: Path):
        import unittest.mock as mock
        editor = MediaEditor()
        src = tmp_path / "v.mp4"
        src.write_bytes(b"")
        with mock.patch("playnite_py.capture.editor.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="ffmpeg"):
                editor.detect_highlights(src)

    def test_detect_highlights_parses_pts_time(self, tmp_path: Path):
        """Parses pts_time entries from ffmpeg stderr output."""
        import unittest.mock as mock
        editor = MediaEditor()
        src = tmp_path / "v.mp4"
        src.write_bytes(b"")

        fake_stderr = (
            "some line\n"
            "[Parsed_showinfo] n:0 pts:0 pts_time:0.000 pos:0 fmt:yuv420p sar:1/1\n"
            "other line\n"
            "[Parsed_showinfo] n:1 pts:300 pts_time:10.000 pos:0 fmt:yuv420p\n"
            "[Parsed_showinfo] n:2 pts:600 pts_time:20.500 pos:0 fmt:yuv420p\n"
        )

        class FakeResult:
            stderr = fake_stderr
            stdout = ""

        with mock.patch("playnite_py.capture.editor.subprocess.run", return_value=FakeResult()):
            with mock.patch("playnite_py.capture.editor.shutil.which", return_value="/usr/bin/ffmpeg"):
                moments = editor.detect_highlights(src, scene_threshold=0.4, min_gap_seconds=3.0)

        # Should detect timestamps, respecting min_gap
        assert len(moments) >= 1
        for m in moments:
            assert isinstance(m, HighlightMoment)
            assert m.timestamp_seconds >= 0

    def test_detect_highlights_respects_min_gap(self, tmp_path: Path):
        """Timestamps closer than min_gap_seconds are skipped."""
        import unittest.mock as mock
        editor = MediaEditor()
        src = tmp_path / "v.mp4"
        src.write_bytes(b"")

        # Two timestamps 1 second apart — should only yield one with gap=5
        fake_stderr = (
            "[Parsed_showinfo] n:0 pts:0 pts_time:5.000\n"
            "[Parsed_showinfo] n:1 pts:30 pts_time:6.000\n"
        )

        class FakeResult:
            stderr = fake_stderr

        with mock.patch("playnite_py.capture.editor.subprocess.run", return_value=FakeResult()):
            with mock.patch("playnite_py.capture.editor.shutil.which", return_value="/usr/bin/ffmpeg"):
                moments = editor.detect_highlights(src, min_gap_seconds=5.0)

        assert len(moments) == 1

    def test_detect_highlights_timeout_returns_empty(self, tmp_path: Path):
        """TimeoutExpired returns empty list rather than raising."""
        import subprocess
        import unittest.mock as mock
        editor = MediaEditor()
        src = tmp_path / "v.mp4"
        src.write_bytes(b"")
        with mock.patch(
            "playnite_py.capture.editor.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=300)
        ):
            with mock.patch("playnite_py.capture.editor.shutil.which", return_value="/usr/bin/ffmpeg"):
                moments = editor.detect_highlights(src)
        assert moments == []

    def test_auto_montage_fallback_evenly_spaced(self, tmp_path: Path):
        """auto_montage falls back to evenly-spaced clips when no highlights found."""
        import unittest.mock as mock
        editor = MediaEditor()
        src = tmp_path / "v.mp4"
        src.write_bytes(b"fake")
        dest = tmp_path / "out.mp4"

        trimmed_calls = []
        concat_calls = []

        def fake_trim(s, d, start, end, **kw):
            d.write_bytes(b"clip")
            trimmed_calls.append((start, end))
            return d

        def fake_concat(sources, dest_path):
            dest_path.write_bytes(b"montage")
            concat_calls.append(len(sources))
            return dest_path

        def fake_duration(p):
            return 30.0

        with mock.patch.object(editor, "detect_highlights", return_value=[]):
            with mock.patch.object(editor, "trim_video", side_effect=fake_trim):
                with mock.patch.object(editor, "concatenate_videos", side_effect=fake_concat):
                    with mock.patch.object(editor, "_get_video_duration", return_value=30.0):
                        result = editor.auto_montage(src, dest, clip_duration=5.0)

        assert result == dest
        assert len(trimmed_calls) >= 1


# ================================================================== #
# C5 — Achievement capture tests                                       #
# ================================================================== #

class TestAchievementDetector:

    def test_manual_trigger_creates_capture(self, tmp_captures: Path):
        """trigger_capture returns an AchievementCapture with correct metadata."""
        det = AchievementDetector(output_dir=tmp_captures / "achievements")
        result = det.trigger_capture(
            game_name="Hollow Knight",
            achievement_name="True Ending",
        )
        assert isinstance(result, AchievementCapture)
        assert result.game_name == "Hollow Knight"
        assert result.achievement_name == "True Ending"
        assert result.detection_method == "manual"
        assert result.file_path.exists()

    def test_trigger_creates_sidecar(self, tmp_captures: Path):
        """trigger_capture writes a JSON sidecar with 'achievement' tag."""
        det = AchievementDetector(output_dir=tmp_captures / "ach")
        cap = det.trigger_capture(game_name="Celeste", achievement_name="Chapter 1")
        sidecar = cap.sidecar_path
        assert sidecar.exists()
        meta = json.loads(sidecar.read_text())
        assert "achievement" in meta.get("tags", [])
        assert meta["game_name"] == "Celeste"

    def test_custom_tags_appended(self, tmp_captures: Path):
        """Custom tags are merged with the 'achievement' tag in the sidecar."""
        det = AchievementDetector(output_dir=tmp_captures / "ach")
        cap = det.trigger_capture(
            game_name="Hades",
            achievement_name="Clear",
            tags=["boss_kill", "first_run"],
        )
        meta = json.loads(cap.sidecar_path.read_text())
        assert "achievement" in meta["tags"]
        assert "boss_kill" in meta["tags"]

    def test_get_captures_returns_history(self, tmp_captures: Path):
        """get_captures returns all triggered captures this session."""
        det = AchievementDetector(output_dir=tmp_captures / "ach")
        det.trigger_capture(game_name="A", achievement_name="x")
        det.trigger_capture(game_name="A", achievement_name="y")
        assert len(det.get_captures()) == 2

    def test_callback_fired_on_trigger(self, tmp_captures: Path):
        """on_achievement callback is invoked synchronously on manual trigger."""
        fired = []
        det = AchievementDetector(output_dir=tmp_captures / "ach")
        det.on_achievement(lambda c: fired.append(c.achievement_name))
        det.trigger_capture(game_name="G", achievement_name="Trophy")
        assert fired == ["Trophy"]

    def test_status_dict(self, tmp_captures: Path):
        det = AchievementDetector(output_dir=tmp_captures / "ach")
        st = det.status()
        assert "monitoring" in st
        assert "captures_count" in st
        assert isinstance(st["templates_registered"], list)

    def test_to_dict_serialisable(self, tmp_captures: Path):
        """AchievementCapture.to_dict() produces JSON-serialisable output."""
        det = AchievementDetector(output_dir=tmp_captures / "ach")
        cap = det.trigger_capture(game_name="G", achievement_name="A")
        d = cap.to_dict()
        json.dumps(d)   # must not raise
        assert d["detection_method"] == "manual"

    def test_monitoring_starts_and_stops(self, tmp_captures: Path):
        """start_monitoring / stop_monitoring cycle without error."""
        det = AchievementDetector(output_dir=tmp_captures / "ach")
        det.start_monitoring(game_name="TestGame", interval_seconds=0.1)
        assert det.is_monitoring is True
        det.stop_monitoring()
        assert det.is_monitoring is False

    def test_register_template_requires_pil(self, tmp_captures: Path, tmp_path: Path):
        """register_template raises RuntimeError when PIL is unavailable."""
        import unittest.mock as mock
        det = AchievementDetector(output_dir=tmp_captures / "ach")
        fake_png = tmp_path / "t.png"
        fake_png.write_bytes(b"")
        with mock.patch("playnite_py.capture.achievement._PIL_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="Pillow"):
                det.register_template("steam", fake_png)

    def test_correlate_returns_zero_without_numpy(self):
        """_correlate returns 0.0 when numpy is unavailable."""
        import unittest.mock as mock
        with mock.patch("playnite_py.capture.achievement._NUMPY_AVAILABLE", False):
            score = AchievementDetector._correlate(object(), object())  # type: ignore
        assert score == 0.0


# ================================================================== #
# C15 — Overlay tests                                                  #
# ================================================================== #

class TestCaptureOverlay:

    def test_status_keys_present(self):
        ov = CaptureOverlay()
        st = ov.status()
        assert "available" in st
        assert "visible" in st
        assert "recording" in st
        assert "buffering" in st
        assert "game_name" in st

    def test_set_recording_updates_status(self):
        ov = CaptureOverlay()
        ov.set_recording(True, game_name="Hades")
        assert ov.status()["recording"] is True
        assert ov.status()["game_name"] == "Hades"

    def test_set_buffering_updates_status(self):
        ov = CaptureOverlay()
        ov.set_buffering(True)
        assert ov.status()["buffering"] is True

    def test_hide_when_not_visible_is_noop(self):
        """hide() on a never-shown overlay should not raise."""
        ov = CaptureOverlay()
        ov.hide()  # must not raise

    def test_opacity_clamped(self):
        ov_low = CaptureOverlay(opacity=-5.0)
        assert ov_low.opacity >= 0.1
        ov_high = CaptureOverlay(opacity=100.0)
        assert ov_high.opacity <= 1.0

    def test_headless_is_not_available(self):
        """_has_display returns False when neither DISPLAY nor WAYLAND_DISPLAY is set."""
        import sys
        import unittest.mock as mock
        # Only test on Linux where the env var check matters
        if sys.platform in ("darwin", "win32"):
            pytest.skip("Display check only relevant on Linux")
        with mock.patch.dict("os.environ", {}, clear=True):
            assert CaptureOverlay._has_display() is False

    def test_show_noop_when_not_available(self):
        """show() silently does nothing when display is unavailable."""
        import unittest.mock as mock
        ov = CaptureOverlay()
        with mock.patch.object(ov, "_available", False):
            ov.show()
        assert ov._visible is False


# ================================================================== #
# New CLI commands — convert, highlights, achievement, overlay         #
# ================================================================== #

class TestNewCaptureCLICommands:

    def setup_method(self):
        """Reset shared instance dict before each test to prevent state leakage."""
        import playnite_py.cli.capture_commands as cc
        for k in cc._instances:
            cc._instances[k] = None


    def test_cap_convert_no_ffmpeg(self, tmp_path: Path):
        """cap convert exits non-zero and shows error when ffmpeg is absent."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli
        import unittest.mock as mock

        src = tmp_path / "input.mp4"
        src.write_bytes(b"")

        runner = CliRunner()
        with mock.patch("playnite_py.capture.editor.shutil.which", return_value=None):
            result = runner.invoke(cli, [
                "--data-dir", str(tmp_path),
                "capture", "convert",
                str(src), str(tmp_path / "out.webm"),
            ])
        assert result.exit_code != 0 or "ffmpeg" in result.output.lower()

    def test_cap_highlights_detect_only_json(self, tmp_path: Path):
        """highlights --detect-only returns JSON with 'highlights' key."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli
        import unittest.mock as mock

        src = tmp_path / "v.mp4"
        src.write_bytes(b"")

        fake_moments = [HighlightMoment(timestamp_seconds=5.0, scene_score=0.5)]

        runner = CliRunner()
        with mock.patch(
            "playnite_py.capture.editor.MediaEditor.detect_highlights",
            return_value=fake_moments,
        ):
            with mock.patch("playnite_py.capture.editor.shutil.which", return_value="/usr/bin/ffmpeg"):
                result = runner.invoke(cli, [
                    "--data-dir", str(tmp_path),
                    "--format", "json",
                    "capture", "highlights",
                    str(src),
                    "--detect-only",
                ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        data = json.loads(result.output)
        assert "highlights" in data
        assert len(data["highlights"]) == 1

    def test_cap_achievement_manual_trigger_json(self, tmp_path: Path):
        """capture achievement outputs JSON with file_path on manual trigger."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "capture", "achievement",
            "--game", "TestGame",
            "--name", "WinBig",
        ])
        assert result.exit_code == 0, f"Failed: {result.output}"
        data = json.loads(result.output)
        assert "file_path" in data
        assert data["game_name"] == "TestGame"
        assert data["achievement_name"] == "WinBig"

    def test_cap_overlay_status_json(self, tmp_path: Path):
        """capture overlay --status returns JSON status dict."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "capture", "overlay",
            "--status",
        ])
        assert result.exit_code == 0, f"Failed: {result.output}"
        data = json.loads(result.output)
        assert "available" in data
        assert "recording" in data


# ================================================================== #
# C2 — Hotkey listener tests                                           #
# ================================================================== #

class TestHotkeyListener:

    def test_normalise_key_function_key(self):
        """Function keys are wrapped in angle brackets."""
        assert _normalise_key("f12") == "<f12>"
        assert _normalise_key("f9") == "<f9>"

    def test_normalise_key_already_bracketed(self):
        """Keys already in angle-bracket form are not double-wrapped."""
        result = _normalise_key("<ctrl>+f12")
        assert result == "<ctrl>+<f12>"

    def test_normalise_key_letter(self):
        """Plain letters pass through unchanged."""
        assert _normalise_key("s") == "s"

    def test_status_keys(self):
        """status() returns required keys."""
        hl = HotkeyListener()
        st = hl.status()
        assert "running" in st
        assert "pynput_available" in st
        assert "screenshot_key" in st
        assert "record_key" in st
        assert "replay_key" in st

    def test_not_running_initially(self):
        hl = HotkeyListener()
        assert hl.is_running is False

    def test_stop_when_not_started_is_noop(self):
        """stop() on a never-started listener should not raise."""
        hl = HotkeyListener()
        hl.stop()  # must not raise

    def test_start_without_pynput_returns_false(self):
        """Returns False gracefully when pynput is unavailable."""
        import unittest.mock as mock
        fired = []
        hl = HotkeyListener(on_screenshot=lambda: fired.append(1))
        with mock.patch("playnite_py.capture.hotkeys._PYNPUT_AVAILABLE", False):
            result = hl.start()
        assert result is False

    def test_update_keys_changes_binding(self):
        """update_keys changes the stored key strings."""
        hl = HotkeyListener(screenshot_key="f12", record_key="f9")
        hl.update_keys(screenshot_key="f11")
        assert hl.screenshot_key == "f11"
        assert hl.record_key == "f9"  # unchanged

    def test_no_bindings_start_returns_false(self):
        """start() returns False when no action callbacks are registered."""
        import unittest.mock as mock
        hl = HotkeyListener()  # no callbacks
        with mock.patch("playnite_py.capture.hotkeys._PYNPUT_AVAILABLE", True):
            result = hl.start()
        assert result is False

    def test_cap_hotkeys_status_json(self, tmp_path: Path):
        """capture hotkeys --status returns JSON with binding info."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "capture", "hotkeys",
            "--status",
        ])
        assert result.exit_code == 0, f"Failed: {result.output}"
        data = json.loads(result.output)
        assert "running" in data
        assert "screenshot_key" in data
        assert "pynput_available" in data

    def test_cap_hotkeys_start_no_pynput(self, tmp_path: Path):
        """capture hotkeys --start with pynput unavailable exits gracefully."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli
        import unittest.mock as mock

        runner = CliRunner()
        with mock.patch("playnite_py.capture.hotkeys._PYNPUT_AVAILABLE", False):
            result = runner.invoke(cli, [
                "--data-dir", str(tmp_path),
                "--format", "json",
                "capture", "hotkeys",
                "--start",
            ])
        assert result.exit_code == 0, f"Failed: {result.output}"
        data = json.loads(result.output)
        assert data["running"] is False


# ================================================================== #
# Negative-path tests — MediaEditor / VideoRecorder                   #
# ================================================================== #

class TestVideoRecorderNegativePaths:

    def test_trim_video_no_ffmpeg_raises(self, tmp_path: Path):
        """trim_video raises RuntimeError when ffmpeg is not installed."""
        import unittest.mock as mock
        editor = MediaEditor()
        src = tmp_path / "v.mp4"
        src.write_bytes(b"data")
        with mock.patch("playnite_py.capture.editor.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="ffmpeg"):
                editor.trim_video(src, tmp_path / "out.mp4", 0, 5)

    def test_trim_video_inverted_range_raises(self, tmp_path: Path):
        """trim_video raises ValueError when end <= start."""
        import unittest.mock as mock
        editor = MediaEditor()
        src = tmp_path / "v.mp4"
        src.write_bytes(b"data")
        with mock.patch("playnite_py.capture.editor.shutil.which", return_value="/usr/bin/ffmpeg"):
            with pytest.raises(ValueError, match="end_seconds"):
                editor.trim_video(src, tmp_path / "out.mp4", 10, 5)

    def test_trim_video_exceeds_max_raises(self, tmp_path: Path):
        """trim_video raises ValueError when end_seconds exceeds _MAX_END_SECONDS."""
        import unittest.mock as mock
        from playnite_py.capture.editor import _MAX_END_SECONDS
        editor = MediaEditor()
        src = tmp_path / "v.mp4"
        src.write_bytes(b"data")
        with mock.patch("playnite_py.capture.editor.shutil.which", return_value="/usr/bin/ffmpeg"):
            with pytest.raises(ValueError, match="exceeds maximum"):
                editor.trim_video(src, tmp_path / "out.mp4", 0, _MAX_END_SECONDS + 1)

    def test_trim_video_ffmpeg_nonzero_raises(self, tmp_path: Path):
        """trim_video propagates CalledProcessError when ffmpeg exits non-zero."""
        import subprocess
        import unittest.mock as mock
        editor = MediaEditor()
        src = tmp_path / "v.mp4"
        src.write_bytes(b"data")
        with mock.patch("playnite_py.capture.editor.shutil.which", return_value="/usr/bin/ffmpeg"):
            with mock.patch(
                "playnite_py.capture.editor.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "ffmpeg"),
            ):
                with pytest.raises(subprocess.CalledProcessError):
                    editor.trim_video(src, tmp_path / "out.mp4", 0, 10)


# ================================================================== #
# Negative-path tests — sidecar JSON handling                         #
# ================================================================== #

class TestSidecarNegativePaths:

    def test_list_captures_corrupted_sidecar_returns_empty_meta(self, tmp_captures: Path):
        """list_captures gracefully handles a corrupted sidecar JSON file."""
        organizer = MediaOrganizer(captures_root=tmp_captures)
        game_dir = organizer.get_capture_dir("TestGame", "screenshots")
        img = game_dir / "shot.png"
        img.write_bytes(b"PNGDATA")
        sidecar = img.with_suffix(".json")
        sidecar.write_text("{not valid json!!!}", encoding="utf-8")

        captures = organizer.list_captures(game_name="TestGame")
        assert len(captures) == 1
        assert captures[0]["metadata"] == {}  # fallback on parse error

    def test_tag_capture_corrupted_sidecar_overwrites(self, tmp_captures: Path):
        """tag_capture does not crash on a corrupted sidecar — it overwrites it."""
        organizer = MediaOrganizer(captures_root=tmp_captures)
        img = tmp_captures / "shot.png"
        img.write_bytes(b"PNGDATA")
        sidecar = img.with_suffix(".json")
        sidecar.write_text("GARBAGE", encoding="utf-8")

        organizer.tag_capture(img, ["highlight"])
        # Should not raise; sidecar should now contain the tag
        meta = json.loads(sidecar.read_text())
        assert "highlight" in meta.get("tags", [])


# ================================================================== #
# AppConfig.validate() — full rule coverage                           #
# ================================================================== #

class TestAppConfigValidate:
    """Tests for all 11 validation rules in AppConfig.validate()."""

    def _cfg(self) -> AppConfig:
        """Return a fresh default (valid) config."""
        return AppConfig()

    def test_valid_defaults_pass(self):
        self._cfg().validate()  # Should not raise

    def test_screenshot_quality_too_low_raises(self):
        cfg = self._cfg()
        cfg.capture.screenshot_quality = 0
        with pytest.raises(ValueError, match="screenshot_quality"):
            cfg.validate()

    def test_screenshot_quality_too_high_raises(self):
        cfg = self._cfg()
        cfg.capture.screenshot_quality = 101
        with pytest.raises(ValueError, match="screenshot_quality"):
            cfg.validate()

    def test_video_crf_too_high_raises(self):
        cfg = self._cfg()
        cfg.capture.video_crf = 52
        with pytest.raises(ValueError, match="video_crf"):
            cfg.validate()

    def test_video_fps_zero_raises(self):
        cfg = self._cfg()
        cfg.capture.video_fps = 0
        with pytest.raises(ValueError, match="video_fps"):
            cfg.validate()

    def test_buffer_duration_zero_raises(self):
        cfg = self._cfg()
        cfg.capture.buffer_duration_seconds = 0
        with pytest.raises(ValueError, match="buffer_duration_seconds"):
            cfg.validate()

    def test_max_storage_gb_zero_raises(self):
        cfg = self._cfg()
        cfg.capture.max_storage_gb = 0.0
        with pytest.raises(ValueError, match="max_storage_gb"):
            cfg.validate()

    def test_overlay_opacity_zero_raises(self):
        cfg = self._cfg()
        cfg.capture.overlay_opacity = 0.0
        with pytest.raises(ValueError, match="overlay_opacity"):
            cfg.validate()

    def test_recommendation_weights_not_summing_raises(self):
        cfg = self._cfg()
        cfg.recommendations.content_weight = 0.9
        cfg.recommendations.collaborative_weight = 0.9
        # Sum = 0.9+0.9+0.10+0.05 = 1.95 — well outside [0.9, 1.1]
        with pytest.raises(ValueError, match="weights"):
            cfg.validate()

    def test_min_score_threshold_ge_one_raises(self):
        cfg = self._cfg()
        cfg.recommendations.min_score_threshold = 1.0
        with pytest.raises(ValueError, match="min_score_threshold"):
            cfg.validate()

    def test_max_recommendations_zero_raises(self):
        cfg = self._cfg()
        cfg.recommendations.max_recommendations = 0
        with pytest.raises(ValueError, match="max_recommendations"):
            cfg.validate()

    def test_invalid_output_format_raises(self):
        cfg = self._cfg()
        cfg.default_output_format = "xml"
        with pytest.raises(ValueError, match="default_output_format"):
            cfg.validate()

    def test_invalid_log_level_raises(self):
        cfg = self._cfg()
        cfg.log_level = "VERBOSE"
        with pytest.raises(ValueError, match="log_level"):
            cfg.validate()


# ================================================================== #
# organise_replay() — previously zero coverage                        #
# ================================================================== #

class TestOrganiseReplay:
    """Tests for MediaOrganizer.organise_replay()."""

    def test_organise_replay_moves_file(self, tmp_captures: Path):
        organizer = MediaOrganizer(captures_root=tmp_captures)
        src = tmp_captures / "replay_test.mp4"
        src.write_bytes(b"REPLAY_DATA")

        dest = organizer.organise_replay(src, "Test Game")

        assert dest.exists()
        assert dest.suffix == ".mp4"
        assert "replays" in str(dest)
        assert not src.exists()

    def test_organise_replay_creates_sidecar(self, tmp_captures: Path):
        organizer = MediaOrganizer(captures_root=tmp_captures)
        src = tmp_captures / "replay_test.mp4"
        src.write_bytes(b"REPLAY_DATA")

        dest = organizer.organise_replay(src, "Test Game", game_id="game-42")

        sidecar = dest.with_suffix(".json")
        assert sidecar.exists()
        meta = json.loads(sidecar.read_text())
        assert meta["capture_type"] == "replay"
        assert meta["game_id"] == "game-42"

    def test_organise_replay_moves_existing_sidecar(self, tmp_captures: Path):
        organizer = MediaOrganizer(captures_root=tmp_captures)
        src = tmp_captures / "replay_test.mp4"
        src.write_bytes(b"REPLAY_DATA")
        sidecar_src = src.with_suffix(".json")
        sidecar_src.write_text('{"capture_type": "replay", "tags": ["epic"]}', encoding="utf-8")

        dest = organizer.organise_replay(src, "Test Game")

        sidecar_dest = dest.with_suffix(".json")
        assert sidecar_dest.exists()
        meta = json.loads(sidecar_dest.read_text())
        assert meta.get("tags") == ["epic"]

    @pytest.mark.skipif(
        __import__("sys").platform == "win32",
        reason="Symlinks require elevated privileges on Windows",
    )
    def test_organise_replay_symlink_traversal_raises(self, tmp_captures: Path, tmp_path: Path):
        """A symlink whose target resolves outside all allowed roots raises ValueError."""
        organizer = MediaOrganizer(captures_root=tmp_captures)
        external = tmp_path / "external_dir" / "target.mp4"
        external.parent.mkdir(parents=True, exist_ok=True)
        external.write_bytes(b"external_data")

        link_dir = tmp_captures / "link_dir"
        link_dir.mkdir()
        link = link_dir / "replay.mp4"
        link.symlink_to(external)

        with pytest.raises(ValueError):
            organizer.organise_replay(link, "Test Game")


# ================================================================== #
# _assert_source_safe() — direct unit tests                           #
# ================================================================== #

class TestAssertSourceSafe:
    """Direct tests for the _assert_source_safe path-traversal guard."""

    def test_regular_file_within_parent_is_safe(self, tmp_path: Path):
        from playnite_py.capture.organizer import _assert_source_safe
        src = tmp_path / "video.mp4"
        src.write_bytes(b"data")
        _assert_source_safe(src)  # Must not raise

    def test_extra_root_allows_file(self, tmp_path: Path):
        from playnite_py.capture.organizer import _assert_source_safe
        root_a = tmp_path / "root_a"
        root_a.mkdir()
        src = root_a / "video.mp4"
        src.write_bytes(b"data")
        root_b = tmp_path / "root_b"
        root_b.mkdir()
        # src is under root_a (its own parent), so extra_roots=(root_b,) still passes
        _assert_source_safe(src, extra_roots=(root_b,))  # Must not raise

    @pytest.mark.skipif(
        __import__("sys").platform == "win32",
        reason="Symlinks require elevated privileges on Windows",
    )
    def test_symlink_resolving_outside_all_roots_raises(self, tmp_path: Path):
        from playnite_py.capture.organizer import _assert_source_safe
        # target is in a completely separate directory
        target_dir = tmp_path / "external"
        target_dir.mkdir()
        target = target_dir / "secret.mp4"
        target.write_bytes(b"secret")

        safe_dir = tmp_path / "safe"
        safe_dir.mkdir()
        link = safe_dir / "video.mp4"
        link.symlink_to(target)

        extra_root = tmp_path / "other_root"
        extra_root.mkdir()

        # Allowed roots: extra_root, safe_dir — but resolved target is in external/
        with pytest.raises(ValueError):
            _assert_source_safe(link, extra_roots=(extra_root,))


# ================================================================== #
# Database error paths                                                 #
# ================================================================== #

class TestDatabaseErrorPaths:
    """Tests for GameDatabase error and edge-case paths."""

    def test_get_game_nonexistent_returns_none(self, tmp_path: Path):
        from playnite_py.database.db import GameDatabase
        db = GameDatabase(tmp_path / "test.db")
        result = db.get_game("nonexistent-id-xyz")
        db.close()
        assert result is None

    def test_upsert_and_get_game_round_trip(self, tmp_path: Path):
        from playnite_py.database.db import GameDatabase
        from playnite_py.models.game import Game
        db = GameDatabase(tmp_path / "test.db")
        game = Game(id="g-rt-1", name="RoundTrip Game", source="steam")
        db.upsert_game(game)
        fetched = db.get_game("g-rt-1")
        db.close()
        assert fetched is not None
        assert fetched.name == "RoundTrip Game"

    def test_list_capture_records_empty(self, tmp_path: Path):
        from playnite_py.database.db import GameDatabase
        db = GameDatabase(tmp_path / "test.db")
        records = db.list_capture_records()
        db.close()
        assert isinstance(records, list)
        assert len(records) == 0

    def test_save_and_list_capture_record_round_trip(self, tmp_path: Path):
        from playnite_py.database.db import GameDatabase
        from datetime import datetime
        db = GameDatabase(tmp_path / "test.db")
        db.save_capture_record(
            record_id="r-rt-1",
            game_id=None,
            game_name="RoundTrip Game",
            capture_type="screenshot",
            file_path=str(tmp_path / "shot.png"),
            file_size_bytes=1024,
            captured_at=datetime.utcnow(),
        )
        records = db.list_capture_records()
        db.close()
        assert len(records) == 1
        assert records[0]["capture_type"] == "screenshot"
        assert records[0]["game_name"] == "RoundTrip Game"

    def test_parse_dt_invalid_string_returns_none(self):
        from playnite_py.database.db import _parse_dt
        result = _parse_dt("not-a-valid-datetime-string!!!")
        assert result is None


# ================================================================== #
# Extended playnite status — live capture state                       #
# ================================================================== #

class TestCaptureCLIStatus:
    """Tests that `playnite status` JSON output includes live capture state keys."""

    def test_status_includes_all_capture_keys(self, tmp_path: Path):
        from click.testing import CliRunner
        from playnite_py.cli.main import cli
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "status",
        ])
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        data = json.loads(result.output)
        checks = data["checks"]
        assert "recorder" in checks
        assert "buffer" in checks
        assert "hotkeys" in checks
        assert "overlay" in checks

    def test_status_capture_state_idle_when_not_active(self, tmp_path: Path):
        from click.testing import CliRunner
        from playnite_py.cli.main import cli
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "status",
        ])
        assert result.exit_code == 0
        checks = json.loads(result.output)["checks"]
        # With no active captures, all should report ok=True and active=False
        assert checks["recorder"]["ok"] is True
        assert checks["recorder"]["active"] is False
        assert checks["buffer"]["ok"] is True
        assert checks["buffer"]["active"] is False


# ================================================================== #
# view-metadata CLI command                                            #
# ================================================================== #

class TestViewMetadataCommand:
    """Tests for `capture view-metadata <file>` CLI subcommand."""

    def test_view_metadata_screenshot(self, tmp_path: Path):
        """view-metadata shows game name and timestamp from sidecar."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        # Create a fake capture file + sidecar
        cap_file = tmp_path / "shot.png"
        cap_file.write_bytes(b"PNG")
        meta = {
            "id": "abc123",
            "capture_type": "screenshot",
            "game_name": "Hollow Knight",
            "game_id": "hk1",
            "captured_at": "2026-01-15T12:00:00",
            "resolution": "1920x1080",
            "format": "png",
            "backend": "mock",
        }
        cap_file.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "capture", "view-metadata", str(cap_file),
        ])
        assert result.exit_code == 0, result.output
        assert "Hollow Knight" in result.output
        assert "2026-01-15" in result.output

    def test_view_metadata_json_output(self, tmp_path: Path):
        """view-metadata --format json returns parseable JSON with all sidecar fields."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        cap_file = tmp_path / "vid.mp4"
        cap_file.write_bytes(b"MP4")
        meta = {
            "id": "vid001",
            "capture_type": "video",
            "game_name": "Celeste",
            "game_id": "cel1",
            "started_at": "2026-01-15T10:00:00",
            "ended_at": "2026-01-15T10:05:00",
            "duration_seconds": 300.0,
            "resolution": "1920x1080",
            "fps": 60,
            "codec": "libx264",
            "file_size_bytes": 50000000,
        }
        cap_file.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "--format", "json",
            "capture", "view-metadata", str(cap_file),
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["game_name"] == "Celeste"
        assert data["duration_seconds"] == 300.0
        assert data["codec"] == "libx264"

    def test_view_metadata_missing_sidecar(self, tmp_path: Path):
        """view-metadata prints a warning when no sidecar exists; exits cleanly."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        cap_file = tmp_path / "nosidecar.png"
        cap_file.write_bytes(b"PNG")
        # No .json sidecar created

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "capture", "view-metadata", str(cap_file),
        ])
        assert result.exit_code == 0
        assert "No metadata" in result.output or "sidecar" in result.output.lower()


# ================================================================== #
# tag CLI command                                                      #
# ================================================================== #

class TestTagCommand:
    """Tests for `capture tag <file> --add <tag> --remove <tag>` CLI subcommand."""

    def _make_capture_with_sidecar(self, tmp_path: Path, tags: list) -> Path:
        """Create a fake capture file + sidecar with given tags."""
        cap_file = tmp_path / "shot.png"
        cap_file.write_bytes(b"PNG")
        meta = {
            "id": str(uuid.uuid4()),
            "capture_type": "screenshot",
            "game_name": "Test Game",
            "game_id": "g1",
            "captured_at": "2026-01-15T12:00:00",
            "tags": tags,
        }
        cap_file.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
        return cap_file

    def test_tag_add_tags_to_capture(self, tmp_path: Path):
        """capture tag --add boss writes the tag to the sidecar."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        cap_file = self._make_capture_with_sidecar(tmp_path, [])

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "capture", "tag", str(cap_file),
            "--add", "boss",
        ])
        assert result.exit_code == 0, result.output
        updated = json.loads(cap_file.with_suffix(".json").read_text())
        assert "boss" in updated["tags"]

    def test_tag_remove_tags_from_capture(self, tmp_path: Path):
        """capture tag --add epic --remove highlight works correctly."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        cap_file = self._make_capture_with_sidecar(tmp_path, ["highlight", "old"])

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "capture", "tag", str(cap_file),
            "--add", "epic",
            "--remove", "highlight",
        ])
        assert result.exit_code == 0, result.output
        updated = json.loads(cap_file.with_suffix(".json").read_text())
        assert "epic" in updated["tags"]
        assert "highlight" not in updated["tags"]
        assert "old" in updated["tags"]  # untouched

    def test_tag_idempotent_add(self, tmp_path: Path):
        """Adding the same tag twice does not duplicate it."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        cap_file = self._make_capture_with_sidecar(tmp_path, ["boss"])

        runner = CliRunner()
        runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "capture", "tag", str(cap_file), "--add", "boss",
        ])
        updated = json.loads(cap_file.with_suffix(".json").read_text())
        assert updated["tags"].count("boss") == 1

    def test_tag_shows_updated_tags(self, tmp_path: Path):
        """CLI output lists the current tags after the operation."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        cap_file = self._make_capture_with_sidecar(tmp_path, [])

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path),
            "capture", "tag", str(cap_file),
            "--add", "highlight",
        ])
        assert result.exit_code == 0, result.output
        assert "highlight" in result.output


# ================================================================== #
# Extended list filtering                                              #
# ================================================================== #

class TestListFilteringExtended:
    """Tests for --tag, --since, --until filters on `capture list`."""

    def _make_organised_capture(
        self,
        captures_root: Path,
        game: str,
        ctype: str,
        date_str: str,
        tags: list,
        captured_at: str,
    ) -> Path:
        """Plant a fake organised capture file with sidecar at the correct path."""
        safe = game.replace(" ", "_")
        day = date_str  # e.g. "2024-06-01"
        cdir = captures_root / safe / f"{ctype}s" / day
        cdir.mkdir(parents=True, exist_ok=True)
        cap_file = cdir / f"shot_{uuid.uuid4().hex[:8]}.png"
        cap_file.write_bytes(b"PNG")
        meta = {
            "id": str(uuid.uuid4()),
            "capture_type": ctype,
            "game_name": game,
            "game_id": "g1",
            "captured_at": captured_at,
            "tags": tags,
        }
        cap_file.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
        return cap_file

    def test_list_filter_by_tag(self, tmp_path: Path):
        """capture list --tag boss only returns captures tagged 'boss'."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        cap_dir = tmp_path / "captures"
        self._make_organised_capture(cap_dir, "Game A", "screenshot",
                                     "2026-01-01", ["boss"], "2026-01-01T10:00:00")
        self._make_organised_capture(cap_dir, "Game B", "screenshot",
                                     "2026-01-01", ["casual"], "2026-01-01T11:00:00")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path), "--format", "json",
            "capture", "list", "--tag", "boss",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["tags"] == ["boss"]

    def test_list_since_filter(self, tmp_path: Path):
        """capture list --since 2025-01-01 excludes captures before that date."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        cap_dir = tmp_path / "captures"
        self._make_organised_capture(cap_dir, "Old Game", "screenshot",
                                     "2024-01-01", [], "2024-01-01T10:00:00")
        self._make_organised_capture(cap_dir, "New Game", "screenshot",
                                     "2026-01-01", [], "2026-01-01T10:00:00")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path), "--format", "json",
            "capture", "list", "--since", "2025-01-01",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        names = [d.get("game_name") for d in data]
        assert "New Game" in names
        assert "Old Game" not in names

    def test_list_until_filter(self, tmp_path: Path):
        """capture list --until 2024-12-31 excludes captures after that date."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        cap_dir = tmp_path / "captures"
        self._make_organised_capture(cap_dir, "Old Game", "screenshot",
                                     "2024-01-01", [], "2024-01-01T10:00:00")
        self._make_organised_capture(cap_dir, "New Game", "screenshot",
                                     "2026-01-01", [], "2026-01-01T10:00:00")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path), "--format", "json",
            "capture", "list", "--until", "2024-12-31",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        names = [d.get("game_name") for d in data]
        assert "Old Game" in names
        assert "New Game" not in names

    def test_list_date_range_combined(self, tmp_path: Path):
        """--since and --until together return only captures within the range."""
        from click.testing import CliRunner
        from playnite_py.cli.main import cli

        cap_dir = tmp_path / "captures"
        self._make_organised_capture(cap_dir, "Before", "screenshot",
                                     "2023-06-01", [], "2023-06-01T10:00:00")
        self._make_organised_capture(cap_dir, "InRange", "screenshot",
                                     "2024-06-01", [], "2024-06-01T10:00:00")
        self._make_organised_capture(cap_dir, "After", "screenshot",
                                     "2025-06-01", [], "2025-06-01T10:00:00")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--data-dir", str(tmp_path), "--format", "json",
            "capture", "list", "--since", "2024-01-01", "--until", "2024-12-31",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        names = [d.get("game_name") for d in data]
        assert "InRange" in names
        assert "Before" not in names
        assert "After" not in names


# ================================================================== #
# Session info tagging                                                 #
# ================================================================== #

class TestSessionInfoTagging:
    """Tests that session_id is stored in screenshot sidecars when provided."""

    def test_screenshot_sidecar_includes_session_id(self, tmp_path: Path):
        """ScreenshotCapture.capture(session_id=...) writes session_id to sidecar."""
        sc = ScreenshotCapture(output_dir=tmp_path, fmt="png", backend="mock")
        result = sc.capture(game_name="Test Game", game_id="g1", session_id="sess-abc")

        assert result.session_id == "sess-abc"
        sidecar_meta = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
        assert sidecar_meta.get("session_id") == "sess-abc"

    def test_screenshot_sidecar_no_session_id_when_not_provided(self, tmp_path: Path):
        """ScreenshotCapture.capture() without session_id omits it from the sidecar."""
        sc = ScreenshotCapture(output_dir=tmp_path, fmt="png", backend="mock")
        result = sc.capture(game_name="Test Game", game_id="g1")

        assert result.session_id is None
        sidecar_meta = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
        assert "session_id" not in sidecar_meta
