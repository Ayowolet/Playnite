"""Health check endpoints."""
import time
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from loguru import logger

# Track service start time
SERVICE_START_TIME = time.time()

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    version: str
    uptime_seconds: float
    timestamp: str


class ReadinessResponse(BaseModel):
    """Readiness check response model."""

    ready: bool
    checks: dict
    version: str


class LivenessResponse(BaseModel):
    """Liveness check response model."""

    alive: bool
    uptime_seconds: float


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.

    Returns service status, version, and uptime information.
    """
    uptime = time.time() - SERVICE_START_TIME

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        uptime_seconds=round(uptime, 2),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness_check():
    """
    Kubernetes readiness probe.

    Checks if the service is ready to accept traffic.
    Checks database connectivity and critical dependencies.
    """
    checks = {
        "database": False,
        "filesystem": False,
    }

    # Check database
    try:
        from ...database.connection import engine
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        checks["database"] = True
    except Exception as e:
        logger.error(f"Database readiness check failed: {e}")

    # Check filesystem (capture directory)
    try:
        from ...core.config import settings
        capture_path = settings.capture_base_path
        if capture_path and capture_path.exists():
            checks["filesystem"] = True
    except Exception as e:
        logger.error(f"Filesystem readiness check failed: {e}")

    all_ready = all(checks.values())

    if not all_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"ready": False, "checks": checks}
        )

    return ReadinessResponse(
        ready=True,
        checks=checks,
        version="1.0.0"
    )


@router.get("/health/live", response_model=LivenessResponse)
async def liveness_check():
    """
    Kubernetes liveness probe.

    Simple check that the service is alive and responding.
    Should always return 200 unless the process is deadlocked.
    """
    uptime = time.time() - SERVICE_START_TIME

    return LivenessResponse(
        alive=True,
        uptime_seconds=round(uptime, 2)
    )
