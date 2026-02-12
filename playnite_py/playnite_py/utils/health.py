"""
Health check and graceful shutdown utilities for Playnite-Py.

Provides health status reporting and signal handling for graceful shutdown.

Example:
    >>> from playnite_py.utils.health import HealthChecker, GracefulShutdown
    >>> health = HealthChecker()
    >>> status = health.check_all()
    >>> print(status.healthy)
"""

from __future__ import annotations

import atexit
import logging
import signal
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health check status values."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status for a single component."""
    name: str
    status: HealthStatus
    message: str = ""
    latency_ms: Optional[float] = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class OverallHealth:
    """Overall system health status."""
    status: HealthStatus
    components: list[ComponentHealth]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def healthy(self) -> bool:
        """Check if overall status is healthy."""
        return self.status == HealthStatus.HEALTHY

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "healthy": self.healthy,
            "timestamp": self.timestamp.isoformat(),
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "latency_ms": c.latency_ms,
                    "details": c.details,
                }
                for c in self.components
            ],
        }


class HealthChecker:
    """
    Performs health checks on system components.

    Checks database connectivity, filesystem access, and other
    critical components to determine overall system health.

    Example:
        >>> checker = HealthChecker()
        >>> checker.register_check("custom", my_check_function)
        >>> health = checker.check_all()
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = data_dir
        self._checks: dict[str, Callable[[], ComponentHealth]] = {}
        self._register_default_checks()

    def _register_default_checks(self) -> None:
        """Register default health checks."""
        self.register_check("filesystem", self._check_filesystem)
        self.register_check("python", self._check_python)

    def register_check(
        self,
        name: str,
        check_func: Callable[[], ComponentHealth],
    ) -> None:
        """
        Register a custom health check.

        Args:
            name: Check name
            check_func: Function that returns ComponentHealth
        """
        self._checks[name] = check_func

    def check(self, name: str) -> ComponentHealth:
        """
        Run a specific health check.

        Args:
            name: Check name

        Returns:
            Component health status
        """
        if name not in self._checks:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNKNOWN,
                message=f"Check '{name}' not found",
            )

        try:
            import time
            start = time.perf_counter()
            result = self._checks[name]()
            result.latency_ms = (time.perf_counter() - start) * 1000
            return result
        except Exception as e:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )

    def check_all(self) -> OverallHealth:
        """
        Run all health checks.

        Returns:
            Overall health status with all component results
        """
        components = [self.check(name) for name in self._checks]

        # Determine overall status
        if all(c.status == HealthStatus.HEALTHY for c in components):
            overall = HealthStatus.HEALTHY
        elif any(c.status == HealthStatus.UNHEALTHY for c in components):
            overall = HealthStatus.UNHEALTHY
        else:
            overall = HealthStatus.DEGRADED

        return OverallHealth(
            status=overall,
            components=components,
        )

    def _check_filesystem(self) -> ComponentHealth:
        """Check filesystem access."""
        if self.data_dir is None:
            return ComponentHealth(
                name="filesystem",
                status=HealthStatus.HEALTHY,
                message="No data directory configured",
            )

        try:
            # Check if data dir exists and is writable
            if not self.data_dir.exists():
                return ComponentHealth(
                    name="filesystem",
                    status=HealthStatus.DEGRADED,
                    message="Data directory does not exist",
                    details={"path": str(self.data_dir)},
                )

            # Try to write a test file
            test_file = self.data_dir / ".health_check"
            test_file.write_text("health check")
            test_file.unlink()

            return ComponentHealth(
                name="filesystem",
                status=HealthStatus.HEALTHY,
                message="Filesystem accessible",
                details={"path": str(self.data_dir)},
            )
        except PermissionError:
            return ComponentHealth(
                name="filesystem",
                status=HealthStatus.UNHEALTHY,
                message="Permission denied",
                details={"path": str(self.data_dir)},
            )
        except Exception as e:
            return ComponentHealth(
                name="filesystem",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )

    def _check_python(self) -> ComponentHealth:
        """Check Python environment."""
        import platform
        return ComponentHealth(
            name="python",
            status=HealthStatus.HEALTHY,
            message="Python runtime healthy",
            details={
                "version": platform.python_version(),
                "platform": platform.platform(),
            },
        )


class GracefulShutdown:
    """
    Handles graceful shutdown with cleanup callbacks.

    Registers signal handlers for SIGINT and SIGTERM to perform
    cleanup operations before exiting.

    Example:
        >>> shutdown = GracefulShutdown()
        >>> shutdown.register_callback(cleanup_database)
        >>> shutdown.register_callback(save_state)
        >>> # Application runs...
        >>> # On SIGINT/SIGTERM, callbacks are executed in reverse order
    """

    def __init__(self) -> None:
        self._callbacks: list[Callable[[], None]] = []
        self._shutdown_requested = threading.Event()
        self._shutdown_complete = threading.Event()
        self._installed = False

    def install(self) -> None:
        """Install signal handlers."""
        if self._installed:
            return

        # Register signal handlers
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, self._handle_signal)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, self._handle_signal)

        # Register atexit handler
        atexit.register(self._run_callbacks)

        self._installed = True
        logger.debug("Graceful shutdown handlers installed")

    def register_callback(self, callback: Callable[[], None]) -> None:
        """
        Register a cleanup callback.

        Callbacks are executed in reverse order (LIFO) during shutdown.

        Args:
            callback: Function to call during shutdown
        """
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[], None]) -> None:
        """
        Unregister a cleanup callback.

        Args:
            callback: Function to remove
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_requested.is_set()

    def wait_for_shutdown(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for shutdown to be requested.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if shutdown was requested, False if timeout
        """
        return self._shutdown_requested.wait(timeout=timeout)

    def request_shutdown(self) -> None:
        """Request a graceful shutdown."""
        logger.info("Shutdown requested")
        self._shutdown_requested.set()
        self._run_callbacks()

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Handle shutdown signal."""
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name}, initiating graceful shutdown")
        self._shutdown_requested.set()
        self._run_callbacks()
        sys.exit(0)

    def _run_callbacks(self) -> None:
        """Run all registered callbacks."""
        if self._shutdown_complete.is_set():
            return

        logger.debug(f"Running {len(self._callbacks)} shutdown callbacks")

        # Run callbacks in reverse order
        for callback in reversed(self._callbacks):
            try:
                callback()
            except Exception as e:
                logger.error(f"Shutdown callback error: {e}")

        self._shutdown_complete.set()
        logger.debug("Shutdown callbacks completed")


# Global shutdown handler
_shutdown_handler: Optional[GracefulShutdown] = None


def get_shutdown_handler() -> GracefulShutdown:
    """Get the global shutdown handler."""
    global _shutdown_handler
    if _shutdown_handler is None:
        _shutdown_handler = GracefulShutdown()
        _shutdown_handler.install()
    return _shutdown_handler
