"""Achievement detection for auto-capture."""
import threading
import time
from typing import Optional, Callable, List, Dict
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
import numpy as np
import cv2
import mss
from loguru import logger


@dataclass
class AchievementDetection:
    """Represents a detected achievement."""

    timestamp: datetime
    game_id: str
    game_name: str
    screenshot_path: Optional[Path] = None
    confidence: float = 0.0
    region: Optional[tuple] = None  # (x, y, width, height)
    text: Optional[str] = None  # OCR text if available


class AchievementDetector:
    """
    Detects achievement notifications on screen.

    Uses computer vision techniques to detect achievement popups:
    - Template matching for known achievement UI patterns
    - Motion detection for popup animations
    - Color pattern recognition for achievement badges/icons
    - OCR for achievement text (optional)
    """

    def __init__(
        self,
        check_interval: float = 0.5,
        cooldown_seconds: float = 5.0,
    ):
        """
        Initialize achievement detector.

        Args:
            check_interval: How often to check screen (seconds)
            cooldown_seconds: Minimum time between detections (prevent duplicates)
        """
        self.check_interval = check_interval
        self.cooldown_seconds = cooldown_seconds

        # Detection state
        self.is_monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.last_detection_time = 0.0
        self.previous_frame: Optional[np.ndarray] = None

        # Callbacks
        self.on_achievement_detected: Optional[Callable[[AchievementDetection], None]] = None

        # Detection templates (achievement UI patterns)
        self.templates: List[np.ndarray] = []
        self.template_threshold = 0.7  # Match confidence threshold

        # Detection statistics
        self.detections_count = 0
        self.false_positives_count = 0

        # Screen capture
        self.sct = mss.mss()

        # Motion detection settings
        self.motion_threshold = 30  # Pixel difference threshold
        self.motion_area_threshold = 5000  # Minimum changed area (pixels)

    def add_template(self, template_path: Path):
        """
        Add achievement UI template for matching.

        Args:
            template_path: Path to template image (achievement popup screenshot)
        """
        try:
            template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
            if template is not None:
                self.templates.append(template)
                logger.info(f"Added achievement template: {template_path.name}")
            else:
                logger.error(f"Failed to load template: {template_path}")
        except Exception as e:
            logger.error(f"Error loading template: {e}")

    def start_monitoring(
        self,
        game_id: str,
        game_name: str,
        on_achievement_detected: Optional[Callable[[AchievementDetection], None]] = None,
    ):
        """
        Start monitoring for achievements.

        Args:
            game_id: Game identifier
            game_name: Game name
            on_achievement_detected: Callback when achievement is detected
        """
        if self.is_monitoring:
            logger.warning("Achievement detection already monitoring")
            return

        self.on_achievement_detected = on_achievement_detected
        self.is_monitoring = True

        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(game_id, game_name),
            daemon=True,
            name="AchievementDetector",
        )
        self.monitor_thread.start()

        logger.info(f"Started achievement detection for {game_name}")

    def stop_monitoring(self):
        """Stop monitoring for achievements."""
        if not self.is_monitoring:
            return

        logger.info("Stopping achievement detection...")
        self.is_monitoring = False

        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)

        logger.info(
            f"Stopped achievement detection. Detected: {self.detections_count}, "
            f"False positives: {self.false_positives_count}"
        )

    def _monitor_loop(self, game_id: str, game_name: str):
        """Main monitoring loop running in background thread."""
        while self.is_monitoring:
            try:
                # Check cooldown
                current_time = time.time()
                if current_time - self.last_detection_time < self.cooldown_seconds:
                    time.sleep(self.check_interval)
                    continue

                # Capture screen
                monitor = self.sct.monitors[1]  # Primary monitor
                screenshot = self.sct.grab(monitor)
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                # Detect achievement
                detected = self._detect_achievement(frame)

                if detected:
                    # Create detection object
                    detection = AchievementDetection(
                        timestamp=datetime.now(timezone.utc),
                        game_id=game_id,
                        game_name=game_name,
                        confidence=detected["confidence"],
                        region=detected.get("region"),
                    )

                    self.detections_count += 1
                    self.last_detection_time = current_time

                    logger.info(
                        f"Achievement detected for {game_name}! "
                        f"(confidence: {detected['confidence']:.2f})"
                    )

                    # Trigger callback
                    if self.on_achievement_detected:
                        self.on_achievement_detected(detection)

                # Store frame for next comparison
                self.previous_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                time.sleep(self.check_interval)

            except Exception as e:
                logger.error(f"Error in achievement detection loop: {e}")
                time.sleep(self.check_interval)

    def _detect_achievement(self, frame: np.ndarray) -> Optional[Dict]:
        """
        Detect achievement in current frame.

        Uses multiple detection methods:
        1. Motion detection (popup animation)
        2. Template matching (known UI patterns)
        3. Color pattern detection (achievement badges)

        Args:
            frame: Current screen frame (BGR)

        Returns:
            Detection info dict if achievement detected, None otherwise
        """
        # Convert to grayscale for processing
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Method 1: Motion detection
        motion_detected = self._detect_motion(gray)

        if motion_detected:
            # Method 2: Template matching
            if self.templates:
                template_match = self._match_templates(gray)
                if template_match:
                    return {
                        "confidence": template_match["confidence"],
                        "region": template_match["region"],
                        "method": "template",
                    }

            # Method 3: Color/pattern detection
            pattern_match = self._detect_achievement_pattern(frame)
            if pattern_match:
                return {
                    "confidence": pattern_match["confidence"],
                    "region": pattern_match["region"],
                    "method": "pattern",
                }

        return None

    def _detect_motion(self, current_gray: np.ndarray) -> bool:
        """
        Detect motion that might indicate achievement popup.

        Args:
            current_gray: Current frame (grayscale)

        Returns:
            True if significant motion detected
        """
        if self.previous_frame is None:
            return False

        # Calculate frame difference
        diff = cv2.absdiff(self.previous_frame, current_gray)

        # Threshold to get binary image
        _, thresh = cv2.threshold(diff, self.motion_threshold, 255, cv2.THRESH_BINARY)

        # Count changed pixels
        changed_pixels = cv2.countNonZero(thresh)

        return changed_pixels > self.motion_area_threshold

    def _match_templates(self, gray: np.ndarray) -> Optional[Dict]:
        """
        Match achievement templates against current frame.

        Args:
            gray: Current frame (grayscale)

        Returns:
            Match info if template matched, None otherwise
        """
        for template in self.templates:
            # Perform template matching
            result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            # Check if match exceeds threshold
            if max_val >= self.template_threshold:
                h, w = template.shape
                return {
                    "confidence": float(max_val),
                    "region": (max_loc[0], max_loc[1], w, h),
                }

        return None

    def _detect_achievement_pattern(self, frame: np.ndarray) -> Optional[Dict]:
        """
        Detect achievement patterns (colors, shapes, etc.).

        Looks for common achievement notification characteristics:
        - Gold/yellow colors (common in achievement badges)
        - Specific rectangular regions (popup boxes)
        - High contrast areas (notification overlays)

        Args:
            frame: Current frame (BGR)

        Returns:
            Detection info if pattern found, None otherwise
        """
        # Convert to HSV for color detection
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Define gold/yellow color range (common in achievements)
        lower_gold = np.array([15, 100, 100])
        upper_gold = np.array([35, 255, 255])

        # Create mask for gold colors
        mask = cv2.inRange(hsv, lower_gold, upper_gold)

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Check for achievement-sized regions
        for contour in contours:
            area = cv2.contourArea(contour)

            # Achievement popups typically 200-1000 pixels
            if 200 < area < 10000:
                x, y, w, h = cv2.boundingRect(contour)

                # Check aspect ratio (achievements often wide rectangles)
                aspect_ratio = w / h if h > 0 else 0

                if 1.5 < aspect_ratio < 6.0:
                    # Likely achievement popup
                    confidence = min(0.8, area / 10000)  # Higher area = higher confidence

                    return {"confidence": confidence, "region": (x, y, w, h)}

        return None

    def get_statistics(self) -> Dict:
        """
        Get detection statistics.

        Returns:
            Dictionary with detection stats
        """
        return {
            "is_monitoring": self.is_monitoring,
            "detections_count": self.detections_count,
            "false_positives_count": self.false_positives_count,
            "templates_loaded": len(self.templates),
            "check_interval": self.check_interval,
            "cooldown_seconds": self.cooldown_seconds,
        }


class AchievementCaptureManager:
    """
    Manages achievement detection and auto-capture for game sessions.

    Coordinates between achievement detector and capture manager.
    """

    def __init__(self, capture_manager):
        """
        Initialize achievement capture manager.

        Args:
            capture_manager: CaptureManager instance for triggering screenshots
        """
        self.capture_manager = capture_manager
        self.detectors: Dict[str, AchievementDetector] = {}
        self.achievement_log: List[AchievementDetection] = []

    def enable_for_session(
        self,
        session_id: str,
        game_id: str,
        game_name: str,
        check_interval: float = 0.5,
        cooldown_seconds: float = 5.0,
    ) -> bool:
        """
        Enable achievement detection for a capture session.

        Args:
            session_id: Capture session ID
            game_id: Game identifier
            game_name: Game name
            check_interval: Detection check interval
            cooldown_seconds: Cooldown between detections

        Returns:
            True if enabled successfully
        """
        if session_id in self.detectors:
            logger.warning(f"Achievement detection already enabled for session {session_id}")
            return False

        try:
            # Create detector
            detector = AchievementDetector(
                check_interval=check_interval, cooldown_seconds=cooldown_seconds
            )

            # Set up callback to auto-capture
            def on_achievement(detection: AchievementDetection):
                self._handle_achievement_detected(session_id, detection)

            # Start monitoring
            detector.start_monitoring(game_id, game_name, on_achievement)

            self.detectors[session_id] = detector

            logger.info(f"Achievement detection enabled for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to enable achievement detection: {e}")
            return False

    def disable_for_session(self, session_id: str):
        """
        Disable achievement detection for a session.

        Args:
            session_id: Capture session ID
        """
        detector = self.detectors.pop(session_id, None)
        if detector:
            detector.stop_monitoring()
            logger.info(f"Achievement detection disabled for session {session_id}")

    def _handle_achievement_detected(
        self, session_id: str, detection: AchievementDetection
    ):
        """
        Handle achievement detection event.

        Args:
            session_id: Capture session ID
            detection: Achievement detection info
        """
        # Auto-capture screenshot
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Capture screenshot
        screenshot_path = loop.run_until_complete(
            self.capture_manager.capture_screenshot(session_id)
        )

        if screenshot_path:
            detection.screenshot_path = screenshot_path
            logger.info(f"Auto-captured achievement screenshot: {screenshot_path.name}")

        # Log detection
        self.achievement_log.append(detection)

    def get_session_achievements(self, session_id: str) -> List[AchievementDetection]:
        """
        Get all detected achievements for a session.

        Args:
            session_id: Capture session ID

        Returns:
            List of achievement detections
        """
        # Filter log by session (match game_id from session)
        session = self.capture_manager.get_session(session_id)
        if not session:
            return []

        return [
            detection
            for detection in self.achievement_log
            if detection.game_id == session.game_id
        ]

    def get_all_achievements(self) -> List[AchievementDetection]:
        """Get all detected achievements across all sessions."""
        return self.achievement_log.copy()
