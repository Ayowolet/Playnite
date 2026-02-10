"""
Structural Protocols for the capture subsystem.

Defining explicit contracts via ``typing.Protocol`` allows static
type-checkers to verify that VideoRecorder, ReplayBuffer, and
ScreenshotCapture implement a declared API rather than relying on
implicit duck-typing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class VideoRecorderProtocol(Protocol):
    """Contract for objects that record screen video."""

    def start_recording(
        self,
        game_name: Optional[str] = None,
        game_id: Optional[str] = None,
        output_path: Optional[Path] = None,
        duration_limit: Optional[int] = None,
        simulate: bool = False,
    ) -> Any: ...

    def stop_recording(self) -> Optional[Any]: ...

    def is_recording(self) -> bool: ...

    def status(self) -> Dict[str, Any]: ...


@runtime_checkable
class ReplayBufferProtocol(Protocol):
    """Contract for objects that maintain a rolling replay buffer."""

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def is_buffering(self) -> bool: ...

    def save_replay(
        self,
        game_name: Optional[str] = None,
        game_id: Optional[str] = None,
        output_path: Optional[Path] = None,
        last_n_seconds: Optional[int] = None,
    ) -> Optional[Path]: ...

    def status(self) -> Dict[str, Any]: ...


@runtime_checkable
class ScreenshotCaptureProtocol(Protocol):
    """Contract for objects that capture screenshots."""

    def capture(
        self,
        game_name: Optional[str] = None,
        game_id: Optional[str] = None,
        monitor: int = 1,
    ) -> Any: ...
