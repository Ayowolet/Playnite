"""Pytest configuration and fixtures."""
import pytest
from prometheus_client import REGISTRY


@pytest.fixture(scope="session", autouse=True)
def clear_prometheus_registry():
    """Clear Prometheus registry before tests to avoid duplicate metric errors."""
    # Clear all collectors
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass

    yield

    # Optional: Clean up after all tests
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass
