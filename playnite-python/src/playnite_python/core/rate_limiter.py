"""Rate limiting middleware."""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Tuple
from fastapi import HTTPException, Request, status
from loguru import logger

from .config import settings


class RateLimiter:
    """
    Simple in-memory rate limiter.

    In production, use Redis-backed rate limiting (e.g., slowapi with Redis).
    This is a basic implementation for development/small deployments.
    """

    def __init__(self):
        # Store: {client_id: [(timestamp, count)]}
        self.requests: Dict[str, list] = defaultdict(list)
        self.enabled = settings.rate_limit_enabled

    def _get_client_id(self, request: Request) -> str:
        """Get client identifier from request."""
        # Use X-Forwarded-For if behind proxy, otherwise use client IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _clean_old_requests(self, client_id: str, window_seconds: int):
        """Remove requests outside the time window."""
        cutoff = datetime.now() - timedelta(seconds=window_seconds)
        self.requests[client_id] = [
            (ts, count) for ts, count in self.requests[client_id]
            if ts > cutoff
        ]

    def check_rate_limit(self, request: Request) -> Tuple[bool, dict]:
        """
        Check if request exceeds rate limits.

        Args:
            request: FastAPI request object

        Returns:
            Tuple of (is_allowed, rate_limit_info)

        Raises:
            HTTPException: If rate limit exceeded
        """
        if not self.enabled:
            return True, {}

        client_id = self._get_client_id(request)
        now = datetime.now()

        # Clean old entries
        self._clean_old_requests(client_id, 3600)  # Keep 1 hour window

        # Count requests in last minute
        minute_ago = now - timedelta(minutes=1)
        requests_last_minute = sum(
            count for ts, count in self.requests[client_id]
            if ts > minute_ago
        )

        # Count requests in last hour
        hour_ago = now - timedelta(hours=1)
        requests_last_hour = sum(
            count for ts, count in self.requests[client_id]
            if ts > hour_ago
        )

        # Check limits
        per_minute_exceeded = requests_last_minute >= settings.rate_limit_per_minute
        per_hour_exceeded = requests_last_hour >= settings.rate_limit_per_hour

        if per_minute_exceeded or per_hour_exceeded:
            logger.warning(
                f"Rate limit exceeded for {client_id}: "
                f"{requests_last_minute}/min, {requests_last_hour}/hour"
            )

            # Calculate retry-after time
            if per_minute_exceeded:
                retry_after = 60
                limit_type = "per-minute"
            else:
                retry_after = 3600
                limit_type = "per-hour"

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded ({limit_type})",
                headers={"Retry-After": str(retry_after)},
            )

        # Record this request
        self.requests[client_id].append((now, 1))

        # Return rate limit info
        rate_limit_info = {
            "limit_per_minute": settings.rate_limit_per_minute,
            "remaining_per_minute": settings.rate_limit_per_minute - requests_last_minute - 1,
            "limit_per_hour": settings.rate_limit_per_hour,
            "remaining_per_hour": settings.rate_limit_per_hour - requests_last_hour - 1,
        }

        return True, rate_limit_info


# Global rate limiter instance
rate_limiter = RateLimiter()
