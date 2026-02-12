"""
Logging utilities for Playnite-Py.

This module provides logging configuration, structured logging,
and observability utilities.
"""

import json
import logging
import time
import threading
import functools
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar
from uuid import uuid4


T = TypeVar("T")

# Thread-local storage for operation context
_context = threading.local()


@dataclass
class OperationMetrics:
    """Metrics collected during an operation."""
    operation_id: str
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    success: bool = True
    error_message: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        if self.end_time is None:
            return (time.perf_counter() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "operation_id": self.operation_id,
            "operation_name": self.operation_name,
            "duration_ms": round(self.duration_ms, 2),
            "success": self.success,
            "error_message": self.error_message,
            **self.metadata,
        }


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter for observability."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add operation context if available
        if hasattr(_context, "operation_id"):
            log_data["operation_id"] = _context.operation_id

        # Add extra fields
        if hasattr(record, "extra_data") and record.extra_data:
            log_data.update(record.extra_data)

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class MetricsCollector:
    """Collects and aggregates operation metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._operations: list[OperationMetrics] = []
        self._max_history = 1000

    def record(self, metrics: OperationMetrics) -> None:
        """Record an operation's metrics."""
        with self._lock:
            self._operations.append(metrics)
            # Prevent unbounded growth
            if len(self._operations) > self._max_history:
                self._operations = self._operations[-self._max_history:]

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics."""
        with self._lock:
            if not self._operations:
                return {"total_operations": 0}

            durations = [op.duration_ms for op in self._operations]
            successes = sum(1 for op in self._operations if op.success)
            failures = len(self._operations) - successes

            return {
                "total_operations": len(self._operations),
                "success_count": successes,
                "failure_count": failures,
                "success_rate": round(successes / len(self._operations) * 100, 2),
                "avg_duration_ms": round(sum(durations) / len(durations), 2),
                "max_duration_ms": round(max(durations), 2),
                "min_duration_ms": round(min(durations), 2),
            }

    def clear(self) -> None:
        """Clear collected metrics."""
        with self._lock:
            self._operations.clear()


# Global metrics collector
_metrics_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector."""
    return _metrics_collector


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    format_string: Optional[str] = None,
    structured: bool = False,
) -> None:
    """
    Configure logging for the application.

    Args:
        level: Logging level
        log_file: Optional file to write logs to
        format_string: Custom format string (ignored if structured=True)
        structured: Use JSON structured logging

    Example:
        >>> setup_logging(level=logging.DEBUG, log_file=Path("app.log"))
        >>> setup_logging(structured=True)  # JSON format for observability
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    if structured:
        formatter = StructuredFormatter()
    else:
        if format_string is None:
            format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        formatter = logging.Formatter(format_string)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


@contextmanager
def operation_context(operation_name: str, **metadata):
    """
    Context manager for tracking operation metrics.

    Args:
        operation_name: Name of the operation being tracked
        **metadata: Additional metadata to include

    Yields:
        OperationMetrics instance for the operation

    Example:
        >>> with operation_context("launch_game", game_id="abc123") as op:
        ...     # do work
        ...     op.metadata["extra"] = "value"
    """
    operation_id = str(uuid4())[:8]
    _context.operation_id = operation_id

    metrics = OperationMetrics(
        operation_id=operation_id,
        operation_name=operation_name,
        start_time=time.perf_counter(),
        metadata=metadata,
    )

    logger = get_logger("playnite_py.operations")
    logger.info(f"Starting operation: {operation_name}", extra={"extra_data": metrics.to_dict()})

    try:
        yield metrics
    except Exception as e:
        metrics.success = False
        metrics.error_message = str(e)
        raise
    finally:
        metrics.end_time = time.perf_counter()
        _metrics_collector.record(metrics)
        logger.info(
            f"Completed operation: {operation_name} ({metrics.duration_ms:.2f}ms)",
            extra={"extra_data": metrics.to_dict()}
        )
        del _context.operation_id


def track_operation(operation_name: str = None):
    """
    Decorator to track function execution as an operation.

    Args:
        operation_name: Name for the operation (defaults to function name)

    Example:
        >>> @track_operation("game_launch")
        ... def launch_game(game_id: str):
        ...     pass
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        name = operation_name or func.__name__

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            with operation_context(name):
                return func(*args, **kwargs)

        return wrapper
    return decorator
