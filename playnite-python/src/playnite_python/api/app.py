"""FastAPI application for Playnite Python service."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
import time

from ..core.config import settings
from ..core.logging_config import setup_logging
from ..core.rate_limiter import rate_limiter
from ..core.monitoring import (
    api_requests_total,
    api_request_duration_seconds,
    api_errors_total,
    metrics_endpoint,
)
from .routes import health, recommendations, capture, feedback, editor

# Initialize logging
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("Playnite Python Service starting...")
    logger.info(f"Server will listen on {settings.host}:{settings.port}")
    logger.info(f"Database: {settings.database_url}")
    logger.info(f"Capture path: {settings.capture_base_path}")
    logger.info(f"API Key Auth: {'enabled' if settings.enable_api_key_auth else 'disabled'}")
    logger.info(f"Rate Limiting: {'enabled' if settings.rate_limit_enabled else 'disabled'}")
    logger.info(f"Metrics: {'enabled' if settings.enable_metrics else 'disabled'}")

    # Initialize database
    from ..database.connection import init_db
    init_db()
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Playnite Python Service shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Playnite Python Service",
    description="Python integration for Playnite providing game recommendations and media capture",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware (localhost only for security)
allowed_origins_list = settings.allowed_origins.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Rate-Limit-*"],
)


# Rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to requests."""
    try:
        # Check rate limit
        rate_limiter.check_rate_limit(request)

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        _, rate_info = rate_limiter.check_rate_limit(request)
        if rate_info:
            response.headers["X-Rate-Limit-Limit-Minute"] = str(
                rate_info.get("limit_per_minute", 0)
            )
            response.headers["X-Rate-Limit-Remaining-Minute"] = str(
                rate_info.get("remaining_per_minute", 0)
            )

        return response

    except Exception as e:
        # Rate limit exceptions should be handled here
        if hasattr(e, "status_code"):
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": str(e.detail)},
                headers=getattr(e, "headers", {}),
            )
        raise


# Metrics tracking middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Track metrics for requests."""
    start_time = time.time()
    method = request.method
    path = request.url.path

    try:
        response = await call_next(request)
        status_code = response.status_code

        # Record metrics
        api_requests_total.labels(
            method=method,
            endpoint=path,
            status=status_code
        ).inc()

        duration = time.time() - start_time
        api_request_duration_seconds.labels(
            method=method,
            endpoint=path
        ).observe(duration)

        # Add custom headers
        response.headers["X-Process-Time"] = str(duration)

        return response

    except Exception as e:
        # Record error
        error_type = type(e).__name__
        api_errors_total.labels(
            method=method,
            endpoint=path,
            error_type=error_type
        ).inc()

        logger.error(f"Request failed: {method} {path} - {e}")
        raise


# Security headers middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to responses."""
    response = await call_next(request)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"

    return response


# Register routers
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(
    recommendations.router, prefix="/api/v1/recommendations", tags=["Recommendations"]
)
app.include_router(capture.router, prefix="/api/v1/capture", tags=["Capture"])
app.include_router(feedback.router, prefix="/api/v1/feedback", tags=["Feedback & Learning"])
app.include_router(editor.router, prefix="/api/v1/editor", tags=["Video & Screenshot Editing"])


# Metrics endpoint
if settings.enable_metrics:
    @app.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint."""
        return await metrics_endpoint()


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Playnite Python",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }
