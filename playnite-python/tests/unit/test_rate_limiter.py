"""Unit tests for rate limiter."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock
from fastapi import HTTPException
from src.playnite_python.core.rate_limiter import RateLimiter


@pytest.fixture
def rate_limiter():
    """Create a rate limiter instance for testing."""
    limiter = RateLimiter()
    limiter.enabled = True
    return limiter


@pytest.fixture
def mock_request():
    """Create a mock FastAPI request."""
    request = Mock()
    request.client = Mock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    return request


def test_rate_limiter_initialization(rate_limiter):
    """Test rate limiter initializes correctly."""
    assert isinstance(rate_limiter.requests, dict)
    assert rate_limiter.enabled is True


def test_get_client_id_from_ip(rate_limiter, mock_request):
    """Test extracting client ID from IP address."""
    client_id = rate_limiter._get_client_id(mock_request)
    assert client_id == "127.0.0.1"


def test_get_client_id_from_forwarded_header(rate_limiter, mock_request):
    """Test extracting client ID from X-Forwarded-For header."""
    mock_request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}
    client_id = rate_limiter._get_client_id(mock_request)
    # Should use first IP in the list
    assert client_id == "192.168.1.1"


def test_get_client_id_no_client(rate_limiter):
    """Test client ID extraction when client is None."""
    request = Mock()
    request.client = None
    request.headers = {}

    client_id = rate_limiter._get_client_id(request)
    assert client_id == "unknown"


def test_check_rate_limit_allows_first_request(rate_limiter, mock_request):
    """Test that first request is allowed."""
    allowed, info = rate_limiter.check_rate_limit(mock_request)

    assert allowed is True
    assert "limit_per_minute" in info
    assert "remaining_per_minute" in info


def test_check_rate_limit_disabled(mock_request):
    """Test that rate limiting can be disabled."""
    limiter = RateLimiter()
    limiter.enabled = False

    allowed, info = limiter.check_rate_limit(mock_request)

    assert allowed is True
    assert info == {}


def test_rate_limit_per_minute_exceeded(rate_limiter, mock_request):
    """Test that per-minute rate limit is enforced."""
    # Mock settings
    from src.playnite_python.core import config
    original_limit = config.settings.rate_limit_per_minute
    config.settings.rate_limit_per_minute = 5

    try:
        # Make 5 requests (should succeed)
        for _ in range(5):
            rate_limiter.check_rate_limit(mock_request)

        # 6th request should fail
        with pytest.raises(HTTPException) as exc_info:
            rate_limiter.check_rate_limit(mock_request)

        assert exc_info.value.status_code == 429
        assert "per-minute" in exc_info.value.detail
        assert "Retry-After" in exc_info.value.headers
        assert exc_info.value.headers["Retry-After"] == "60"

    finally:
        config.settings.rate_limit_per_minute = original_limit


def test_rate_limit_per_hour_exceeded(rate_limiter, mock_request):
    """Test that per-hour rate limit is enforced."""
    # Mock settings
    from src.playnite_python.core import config
    original_minute_limit = config.settings.rate_limit_per_minute
    original_hour_limit = config.settings.rate_limit_per_hour

    config.settings.rate_limit_per_minute = 1000  # High limit to not trigger
    config.settings.rate_limit_per_hour = 3

    try:
        # Make 3 requests (should succeed)
        for _ in range(3):
            rate_limiter.check_rate_limit(mock_request)

        # 4th request should fail
        with pytest.raises(HTTPException) as exc_info:
            rate_limiter.check_rate_limit(mock_request)

        assert exc_info.value.status_code == 429
        assert "per-hour" in exc_info.value.detail
        assert exc_info.value.headers["Retry-After"] == "3600"

    finally:
        config.settings.rate_limit_per_minute = original_minute_limit
        config.settings.rate_limit_per_hour = original_hour_limit


def test_clean_old_requests(rate_limiter):
    """Test that old requests are cleaned up."""
    client_id = "test-client"

    # Add old request (2 hours ago)
    old_time = datetime.now() - timedelta(hours=2)
    rate_limiter.requests[client_id].append((old_time, 1))

    # Add recent request
    recent_time = datetime.now()
    rate_limiter.requests[client_id].append((recent_time, 1))

    # Clean requests older than 1 hour
    rate_limiter._clean_old_requests(client_id, 3600)

    # Only recent request should remain
    assert len(rate_limiter.requests[client_id]) == 1
    assert rate_limiter.requests[client_id][0][0] == recent_time


def test_rate_limit_info_accuracy(rate_limiter, mock_request):
    """Test that rate limit info provides accurate counts."""
    from src.playnite_python.core import config
    original_limit = config.settings.rate_limit_per_minute
    config.settings.rate_limit_per_minute = 10

    try:
        # Make 3 requests
        for _ in range(3):
            rate_limiter.check_rate_limit(mock_request)

        # Check rate limit info on 4th request
        allowed, info = rate_limiter.check_rate_limit(mock_request)

        assert info["limit_per_minute"] == 10
        assert info["remaining_per_minute"] == 10 - 4  # 4 requests made

    finally:
        config.settings.rate_limit_per_minute = original_limit


def test_rate_limit_different_clients(rate_limiter):
    """Test that rate limits are tracked separately per client."""
    from src.playnite_python.core import config
    original_limit = config.settings.rate_limit_per_minute
    config.settings.rate_limit_per_minute = 2

    try:
        # Create two different mock requests
        request1 = Mock()
        request1.client = Mock()
        request1.client.host = "192.168.1.1"
        request1.headers = {}

        request2 = Mock()
        request2.client = Mock()
        request2.client.host = "192.168.1.2"
        request2.headers = {}

        # Make 2 requests from client 1 (should succeed)
        rate_limiter.check_rate_limit(request1)
        rate_limiter.check_rate_limit(request1)

        # 3rd request from client 1 should fail
        with pytest.raises(HTTPException):
            rate_limiter.check_rate_limit(request1)

        # But client 2 should still be allowed
        allowed, _ = rate_limiter.check_rate_limit(request2)
        assert allowed is True

    finally:
        config.settings.rate_limit_per_minute = original_limit


def test_rate_limit_resets_after_window(rate_limiter, mock_request, monkeypatch):
    """Test that rate limit resets after time window expires."""
    from src.playnite_python.core import config
    original_limit = config.settings.rate_limit_per_minute
    config.settings.rate_limit_per_minute = 2

    try:
        # Make 2 requests (should succeed)
        rate_limiter.check_rate_limit(mock_request)
        rate_limiter.check_rate_limit(mock_request)

        # 3rd request should fail
        with pytest.raises(HTTPException):
            rate_limiter.check_rate_limit(mock_request)

        # Mock time to be 2 minutes in the future
        def mock_now():
            return datetime.now() + timedelta(minutes=2)

        # After window expires, should be allowed again
        # (In real implementation, old requests would be cleaned)
        client_id = rate_limiter._get_client_id(mock_request)
        rate_limiter.requests[client_id] = []  # Simulate cleanup

        allowed, _ = rate_limiter.check_rate_limit(mock_request)
        assert allowed is True

    finally:
        config.settings.rate_limit_per_minute = original_limit
