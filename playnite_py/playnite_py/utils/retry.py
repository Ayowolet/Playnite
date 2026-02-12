"""
Retry and rate limiting utilities for Playnite-Py.

Provides decorators and utilities for handling transient failures
and rate limiting external API calls.

Example:
    >>> @retry(max_attempts=3, delay=1.0)
    ... def fetch_data():
    ...     # May fail transiently
    ...     pass
"""

from __future__ import annotations

import functools
import logging
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying a function on failure.

    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exception types to retry on
        on_retry: Callback function called on each retry

    Returns:
        Decorated function with retry logic

    Example:
        >>> @retry(max_attempts=3, delay=0.5)
        ... def unreliable_api():
        ...     pass
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        logger.warning(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise

                    logger.debug(
                        f"{func.__name__} attempt {attempt} failed: {e}, "
                        f"retrying in {current_delay:.1f}s"
                    )

                    if on_retry:
                        on_retry(e, attempt)

                    time.sleep(current_delay)
                    current_delay *= backoff

            # Should never reach here
            raise last_exception  # type: ignore

        return wrapper
    return decorator


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    calls_per_second: float = 10.0
    burst_size: int = 10


class RateLimiter:
    """
    Token bucket rate limiter.

    Limits the rate of operations using a token bucket algorithm.
    Supports burst capacity for handling temporary spikes.

    Attributes:
        calls_per_second: Rate of token regeneration
        burst_size: Maximum tokens available
    """

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        config = config or RateLimitConfig()
        self.calls_per_second = config.calls_per_second
        self.burst_size = config.burst_size
        self._tokens = float(config.burst_size)
        self._last_update = time.monotonic()
        self._lock = Lock()

    def acquire(self, timeout: float | None = None) -> bool:
        """
        Acquire a token, blocking if necessary.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if token acquired, False if timeout expired
        """
        start_time = time.monotonic()

        while True:
            with self._lock:
                self._refill()

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True

            # Calculate wait time
            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    return False

            # Wait for token regeneration
            wait_time = 1.0 / self.calls_per_second
            if timeout is not None:
                wait_time = min(wait_time, timeout - elapsed)

            time.sleep(wait_time)

    def try_acquire(self) -> bool:
        """
        Try to acquire a token without blocking.

        Returns:
            True if token acquired, False otherwise
        """
        with self._lock:
            self._refill()

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True

            return False

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_update
        self._last_update = now

        new_tokens = elapsed * self.calls_per_second
        self._tokens = min(self.burst_size, self._tokens + new_tokens)


def rate_limited(
    limiter: RateLimiter,
    timeout: float | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for rate limiting function calls.

    Args:
        limiter: RateLimiter instance to use
        timeout: Maximum time to wait for rate limit

    Returns:
        Decorated function with rate limiting

    Raises:
        RuntimeError: If rate limit timeout exceeded

    Example:
        >>> limiter = RateLimiter(RateLimitConfig(calls_per_second=1.0))
        >>> @rate_limited(limiter)
        ... def api_call():
        ...     pass
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            if not limiter.acquire(timeout=timeout):
                raise RuntimeError(f"Rate limit exceeded for {func.__name__}")
            return func(*args, **kwargs)

        return wrapper
    return decorator


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.

    Prevents cascading failures by temporarily blocking calls
    to a failing service.

    States:
        - CLOSED: Normal operation, calls pass through
        - OPEN: Calls fail immediately
        - HALF_OPEN: Limited calls to test recovery
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_calls: int = 3,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_calls = half_open_calls

        self._failures = 0
        self._state = "CLOSED"
        self._last_failure_time = 0.0
        self._half_open_successes = 0
        self._lock = Lock()

    @property
    def state(self) -> str:
        """Get current circuit breaker state."""
        with self._lock:
            if self._state == "OPEN":
                # Check if recovery timeout has passed
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    self._state = "HALF_OPEN"
                    self._half_open_successes = 0
            return self._state

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute a function through the circuit breaker.

        Args:
            func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            RuntimeError: If circuit is open
        """
        state = self.state

        if state == "OPEN":
            raise RuntimeError("Circuit breaker is open")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """Handle successful call."""
        with self._lock:
            if self._state == "HALF_OPEN":
                self._half_open_successes += 1
                if self._half_open_successes >= self.half_open_calls:
                    self._state = "CLOSED"
                    self._failures = 0
                    logger.info("Circuit breaker closed after recovery")
            else:
                self._failures = 0

    def _on_failure(self) -> None:
        """Handle failed call."""
        with self._lock:
            self._failures += 1
            self._last_failure_time = time.monotonic()

            if self._state == "HALF_OPEN":
                self._state = "OPEN"
                logger.warning("Circuit breaker reopened after failure in half-open")
            elif self._failures >= self.failure_threshold:
                self._state = "OPEN"
                logger.warning(
                    f"Circuit breaker opened after {self._failures} failures"
                )

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        with self._lock:
            self._state = "CLOSED"
            self._failures = 0
            self._half_open_successes = 0
