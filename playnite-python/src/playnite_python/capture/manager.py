"""Capture session manager orchestrating backends, storage, and hotkeys."""
import time
from typing import Dict, Optional
from pathlib import Path
from loguru import logger

from .backends.direct_capture import DirectCaptureBackend
from .storage import CaptureStorage
from .hotkeys import MultiHotkeyListener
from .instant_replay import InstantReplayBuffer
from .processors.achievement_detector import AchievementCaptureManager
from .metadata import MetadataService


class CaptureSession:
    """Represents an active capture session for a game."""

    def __init__(self, session_id: str, game_id: str, game_name: str, backend_name: str):
        self.session_id = session_id
        self.game_id = game_id
        self.game_name = game_name
        self.backend_name = backend_name
        self.backend = None
        self.storage = CaptureStorage()
        self.hotkey_listener = None
        self.instant_replay: Optional[InstantReplayBuffer] = None
        self.active = False
        self.screenshot_count = 0
        self.video_count = 0
        self.replay_count = 0
        self.started_at = time.time()

    def __repr__(self):
        return (
            f"CaptureSession(id={self.session_id}, game={self.game_name}, "
            f"backend={self.backend_name}, active={self.active})"
        )


class CaptureManager:
    """
    Manages capture sessions across multiple games.

    Handles session lifecycle, backend selection, hotkey management,
    and coordination with storage.
    """

    def __init__(self):
        self.sessions: Dict[str, CaptureSession] = {}
        self.hotkey_manager = MultiHotkeyListener()
        self.achievement_manager = AchievementCaptureManager(self)
        self.metadata_service = MetadataService()
        logger.info("Capture manager initialized")

    async def start_session(
        self,
        game_id: str,
        game_name: str,
        process_id: int,
        settings: Optional[Dict] = None,
    ) -> str:
        """
        Start a new capture session for a game.

        Args:
            game_id: Game identifier
            game_name: Game name for display
            process_id: Process ID of running game
            settings: Optional settings dict with:
                - screenshot_hotkey: Hotkey for screenshots (default: f8)
                - video_hotkey: Hotkey for video recording (default: f9)
                - backend: Backend to use (default: direct)
                - video_quality: Video quality (default: high)

        Returns:
            Session ID for the created session
        """
        settings = settings or {}

        # Generate session ID
        session_id = f"sess-{game_id}-{int(time.time())}"

        # Check if game already has active session
        for existing_session in self.sessions.values():
            if existing_session.game_id == game_id and existing_session.active:
                logger.warning(f"Game {game_name} already has active session, stopping old one")
                await self.stop_session(existing_session.session_id)

        # Select backend
        backend_name = settings.get("backend", "direct")
        session = CaptureSession(session_id, game_id, game_name, backend_name)

        # Initialize backend
        if backend_name == "direct":
            session.backend = DirectCaptureBackend()
        else:
            logger.warning(f"Unknown backend {backend_name}, using direct")
            session.backend = DirectCaptureBackend()

        # Initialize backend
        success = await session.backend.initialize(game_name, process_id)
        if not success:
            logger.error(f"Failed to initialize capture backend for {game_name}")
            return ""

        # Setup instant replay if enabled
        instant_replay_enabled = settings.get("instant_replay_enabled", True)
        if instant_replay_enabled:
            instant_replay_duration = settings.get("instant_replay_duration", 30)
            instant_replay_quality = settings.get("instant_replay_quality", "medium")
            instant_replay_fps = settings.get("instant_replay_fps", 30)

            session.instant_replay = InstantReplayBuffer(
                duration_seconds=instant_replay_duration,
                fps=instant_replay_fps,
                quality=instant_replay_quality,
            )
            session.instant_replay.start()
            logger.info(
                f"Instant replay enabled: {instant_replay_duration}s at {instant_replay_fps} FPS ({instant_replay_quality})"
            )

        # Setup achievement detection if enabled
        achievement_detection_enabled = settings.get("achievement_detection_enabled", False)
        if achievement_detection_enabled:
            check_interval = settings.get("achievement_check_interval", 0.5)
            cooldown = settings.get("achievement_cooldown", 5.0)

            self.achievement_manager.enable_for_session(
                session_id, game_id, game_name, check_interval, cooldown
            )
            logger.info(f"Achievement detection enabled (check every {check_interval}s)")

        # Setup hotkeys
        screenshot_hotkey = settings.get("screenshot_hotkey", "f8")
        video_hotkey = settings.get("video_hotkey", "f9")
        instant_replay_hotkey = settings.get("instant_replay_hotkey", "f10")

        # Add screenshot hotkey
        self.hotkey_manager.add_hotkey(
            f"{session_id}_screenshot",
            screenshot_hotkey,
            lambda: self._handle_screenshot(session_id)
        )

        # Add video hotkey
        self.hotkey_manager.add_hotkey(
            f"{session_id}_video",
            video_hotkey,
            lambda: self._handle_video_toggle(session_id)
        )

        # Add instant replay hotkey if enabled
        if instant_replay_enabled:
            self.hotkey_manager.add_hotkey(
                f"{session_id}_replay",
                instant_replay_hotkey,
                lambda: self._handle_instant_replay(session_id)
            )

        session.active = True
        self.sessions[session_id] = session

        hotkeys_desc = f"Screenshot: {screenshot_hotkey}, Video: {video_hotkey}"
        if instant_replay_enabled:
            hotkeys_desc += f", Instant Replay: {instant_replay_hotkey}"

        logger.info(
            f"Capture session started: {session_id} for {game_name} ({hotkeys_desc})"
        )

        return session_id

    def _handle_screenshot(self, session_id: str):
        """
        Handle screenshot hotkey press.

        Note: This is a synchronous callback from pynput, so we need to
        schedule the async capture_screenshot coroutine.
        """
        import asyncio

        try:
            # Get the event loop or create one
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Schedule the coroutine
            loop.create_task(self.capture_screenshot(session_id))

        except Exception as e:
            logger.error(f"Error handling screenshot hotkey: {e}")

    def _handle_video_toggle(self, session_id: str):
        """Handle video recording hotkey press."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.create_task(self.toggle_video_recording(session_id))

    def _handle_instant_replay(self, session_id: str):
        """Handle instant replay hotkey press."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.create_task(self.save_instant_replay(session_id))

    async def capture_screenshot(self, session_id: str) -> Optional[Path]:
        """
        Capture a screenshot for a session.

        Args:
            session_id: Session identifier

        Returns:
            Path to captured screenshot, or None if failed
        """
        session = self.sessions.get(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            return None

        if not session.active:
            logger.warning(f"Session not active: {session_id}")
            return None

        # Generate output path
        output_path = session.storage.get_screenshot_path(
            session.game_id, session_id
        )

        # Capture
        success = await session.backend.capture_screenshot(output_path)

        if success:
            session.screenshot_count += 1
            logger.info(
                f"Screenshot captured for {session.game_name}: {output_path.name} "
                f"(#{session.screenshot_count})"
            )

            # Create metadata entry
            metadata_id = self.metadata_service.create_metadata(
                file_path=output_path,
                game_id=session.game_id,
                game_name=session.game_name,
                session_id=session_id,
                capture_type="screenshot",
            )

            if metadata_id:
                logger.debug(f"Created metadata for screenshot (ID: {metadata_id})")

            return output_path
        else:
            logger.error(f"Failed to capture screenshot for {session.game_name}")
            return None

    async def start_video_recording(
        self, session_id: str, quality: str = "high"
    ) -> bool:
        """
        Start video recording for a session.

        Args:
            session_id: Session identifier
            quality: Video quality (low, medium, high)

        Returns:
            True if recording started successfully
        """
        session = self.sessions.get(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            return False

        if not session.active:
            logger.warning(f"Session not active: {session_id}")
            return False

        # Check if already recording
        if await session.backend.is_recording():
            logger.warning(f"Session {session_id} already recording")
            return False

        # Generate output path
        output_path = session.storage.get_video_path(session.game_id, session_id)

        # Start recording
        success = await session.backend.start_recording(output_path, quality)

        if success:
            logger.info(f"Video recording started for {session.game_name}")
            return True
        else:
            logger.error(f"Failed to start video recording for {session.game_name}")
            return False

    async def stop_video_recording(self, session_id: str) -> Optional[Path]:
        """
        Stop video recording for a session.

        Args:
            session_id: Session identifier

        Returns:
            Path to recorded video, or None if failed
        """
        session = self.sessions.get(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            return None

        # Stop recording
        video_path = await session.backend.stop_recording()

        if video_path:
            session.video_count += 1
            logger.info(
                f"Video recording stopped for {session.game_name}: {video_path.name} "
                f"(#{session.video_count})"
            )

            # Create metadata entry
            metadata_id = self.metadata_service.create_metadata(
                file_path=video_path,
                game_id=session.game_id,
                game_name=session.game_name,
                session_id=session_id,
                capture_type="video",
            )

            if metadata_id:
                logger.debug(f"Created metadata for video (ID: {metadata_id})")

            return video_path
        else:
            return None

    async def toggle_video_recording(self, session_id: str) -> bool:
        """
        Toggle video recording on/off.

        Args:
            session_id: Session identifier

        Returns:
            True if now recording, False if stopped/failed
        """
        session = self.sessions.get(session_id)
        if not session:
            return False

        is_recording = await session.backend.is_recording()

        if is_recording:
            # Stop recording
            result = await self.stop_video_recording(session_id)
            return False
        else:
            # Start recording
            result = await self.start_video_recording(session_id)
            return result

    async def save_instant_replay(self, session_id: str) -> Optional[Path]:
        """
        Save the instant replay buffer to disk.

        Args:
            session_id: Session identifier

        Returns:
            Path to saved replay, or None if failed
        """
        session = self.sessions.get(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            return None

        if not session.instant_replay:
            logger.warning(f"Instant replay not enabled for session {session_id}")
            return None

        # Generate output path
        output_path = session.storage.get_replay_path(session.game_id, session_id)

        # Save buffer
        success = session.instant_replay.save(output_path)

        if success:
            session.replay_count += 1
            logger.info(
                f"Instant replay saved for {session.game_name}: {output_path.name} "
                f"(#{session.replay_count})"
            )

            # Create metadata entry
            metadata_id = self.metadata_service.create_metadata(
                file_path=output_path,
                game_id=session.game_id,
                game_name=session.game_name,
                session_id=session_id,
                capture_type="replay",
            )

            if metadata_id:
                logger.debug(f"Created metadata for instant replay (ID: {metadata_id})")

            return output_path
        else:
            logger.error(f"Failed to save instant replay for {session.game_name}")
            return None

    def get_instant_replay_info(self, session_id: str) -> Optional[Dict]:
        """
        Get information about instant replay buffer.

        Args:
            session_id: Session identifier

        Returns:
            Buffer info dictionary, or None if not available
        """
        session = self.sessions.get(session_id)
        if not session or not session.instant_replay:
            return None

        return session.instant_replay.get_buffer_info()

    async def stop_session(self, session_id: str) -> Dict:
        """
        Stop a capture session.

        Args:
            session_id: Session identifier

        Returns:
            Dictionary with session statistics
        """
        session = self.sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}

        # Stop any active recording
        if await session.backend.is_recording():
            await session.backend.stop_recording()

        # Stop instant replay buffer
        if session.instant_replay:
            session.instant_replay.stop()

        # Stop achievement detection
        self.achievement_manager.disable_for_session(session_id)

        # Remove hotkeys
        self.hotkey_manager.remove_hotkey(f"{session_id}_screenshot")
        self.hotkey_manager.remove_hotkey(f"{session_id}_video")
        if session.instant_replay:
            self.hotkey_manager.remove_hotkey(f"{session_id}_replay")

        # Cleanup backend
        await session.backend.cleanup()

        session.active = False
        elapsed_time = time.time() - session.started_at

        result = {
            "session_id": session_id,
            "game_name": session.game_name,
            "status": "stopped",
            "duration_seconds": int(elapsed_time),
            "screenshot_count": session.screenshot_count,
            "video_count": session.video_count,
            "replay_count": session.replay_count,
        }

        # Remove from active sessions
        del self.sessions[session_id]

        logger.info(
            f"Capture session stopped: {session.game_name} "
            f"({session.screenshot_count} screenshots, {session.video_count} videos)"
        )

        return result

    def get_session(self, session_id: str) -> Optional[CaptureSession]:
        """
        Get session by ID.

        Args:
            session_id: Session identifier

        Returns:
            CaptureSession or None
        """
        return self.sessions.get(session_id)

    def list_active_sessions(self) -> list:
        """
        List all active sessions.

        Returns:
            List of session dictionaries
        """
        return [
            {
                "session_id": s.session_id,
                "game_id": s.game_id,
                "game_name": s.game_name,
                "backend": s.backend_name,
                "screenshot_count": s.screenshot_count,
                "video_count": s.video_count,
                "duration_seconds": int(time.time() - s.started_at),
            }
            for s in self.sessions.values()
            if s.active
        ]
