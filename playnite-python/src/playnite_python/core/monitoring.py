"""Monitoring and metrics collection."""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry, REGISTRY
from fastapi import Response
from loguru import logger
import time
from typing import Callable, Optional
from functools import wraps

from .config import settings

# Track created metrics to avoid duplicates
_metrics_created = {}


def _get_or_create_counter(name: str, description: str, labelnames: list) -> Counter:
    """Get existing counter or create new one."""
    if name in _metrics_created:
        return _metrics_created[name]

    try:
        metric = Counter(name, description, labelnames)
        _metrics_created[name] = metric
        return metric
    except ValueError:
        # Metric already exists in registry, retrieve it
        for collector in list(REGISTRY._collector_to_names.keys()):
            if hasattr(collector, '_name') and collector._name == name:
                _metrics_created[name] = collector
                return collector
        # Fallback - recreate
        metric = Counter(name, description, labelnames)
        _metrics_created[name] = metric
        return metric


def _get_or_create_histogram(name: str, description: str, labelnames: list) -> Histogram:
    """Get existing histogram or create new one."""
    if name in _metrics_created:
        return _metrics_created[name]

    try:
        metric = Histogram(name, description, labelnames)
        _metrics_created[name] = metric
        return metric
    except ValueError:
        # Metric already exists, retrieve it
        for collector in list(REGISTRY._collector_to_names.keys()):
            if hasattr(collector, '_name') and collector._name == name:
                _metrics_created[name] = collector
                return collector
        metric = Histogram(name, description, labelnames)
        _metrics_created[name] = metric
        return metric


def _get_or_create_gauge(name: str, description: str) -> Gauge:
    """Get existing gauge or create new one."""
    if name in _metrics_created:
        return _metrics_created[name]

    try:
        metric = Gauge(name, description)
        _metrics_created[name] = metric
        return metric
    except ValueError:
        # Metric already exists, retrieve it
        for collector in list(REGISTRY._collector_to_names.keys()):
            if hasattr(collector, '_name') and collector._name == name:
                _metrics_created[name] = collector
                return collector
        metric = Gauge(name, description)
        _metrics_created[name] = metric
        return metric


# API Metrics
api_requests_total = _get_or_create_counter(
    "api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"]
)

api_request_duration_seconds = _get_or_create_histogram(
    "api_request_duration_seconds",
    "API request duration in seconds",
    ["method", "endpoint"]
)

api_errors_total = _get_or_create_counter(
    "api_errors_total",
    "Total API errors",
    ["method", "endpoint", "error_type"]
)

# Recommendation Metrics
recommendations_generated_total = _get_or_create_counter(
    "recommendations_generated_total",
    "Total recommendations generated",
    ["user_id"]
)

recommendation_generation_duration_seconds = _get_or_create_histogram(
    "recommendation_generation_duration_seconds",
    "Time to generate recommendations",
    []
)

recommendation_feedback_total = _get_or_create_counter(
    "recommendation_feedback_total",
    "Total recommendation feedback received",
    ["feedback_type"]
)

# Capture Metrics
capture_sessions_active = _get_or_create_gauge(
    "capture_sessions_active",
    "Number of active capture sessions"
)

screenshots_captured_total = _get_or_create_counter(
    "screenshots_captured_total",
    "Total screenshots captured",
    ["game_id"]
)

videos_recorded_total = _get_or_create_counter(
    "videos_recorded_total",
    "Total videos recorded",
    ["game_id"]
)

instant_replays_saved_total = _get_or_create_counter(
    "instant_replays_saved_total",
    "Total instant replays saved",
    ["game_id"]
)

# System Metrics
active_threads = _get_or_create_gauge(
    "active_threads",
    "Number of active threads"
)

memory_usage_bytes = _get_or_create_gauge(
    "memory_usage_bytes",
    "Current memory usage in bytes"
)

# Database Metrics
database_queries_total = _get_or_create_counter(
    "database_queries_total",
    "Total database queries",
    ["operation"]
)

database_query_duration_seconds = _get_or_create_histogram(
    "database_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"]
)


def track_time(metric: Histogram):
    """Decorator to track execution time."""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                metric.observe(duration)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                metric.observe(duration)

        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def update_system_metrics():
    """Update system-level metrics."""
    import threading
    import psutil
    import os

    try:
        # Thread count
        active_threads.set(threading.active_count())

        # Memory usage
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        memory_usage_bytes.set(memory_info.rss)

    except Exception as e:
        logger.error(f"Failed to update system metrics: {e}")


async def metrics_endpoint() -> Response:
    """
    Prometheus metrics endpoint.

    Returns:
        Response with Prometheus metrics
    """
    # Update system metrics before serving
    update_system_metrics()

    # Generate and return metrics
    metrics_data = generate_latest()
    return Response(
        content=metrics_data,
        media_type=CONTENT_TYPE_LATEST
    )


def log_metric(metric_name: str, value: float, labels: dict = None):
    """
    Log a custom metric (for non-Prometheus monitoring).

    Args:
        metric_name: Name of the metric
        value: Metric value
        labels: Optional labels for the metric
    """
    labels_str = ""
    if labels:
        labels_str = " " + " ".join(f"{k}={v}" for k, v in labels.items())

    logger.info(f"METRIC {metric_name}={value}{labels_str}")
