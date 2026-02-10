"""Unit tests for security module."""
import pytest
from fastapi import HTTPException
from src.playnite_python.core.security import (
    create_access_token,
    hash_password,
    verify_password,
    sanitize_path
)


def test_create_access_token():
    """Test JWT token creation."""
    data = {"user_id": "test_user", "role": "admin"}

    token = create_access_token(data)

    assert isinstance(token, str)
    assert len(token) > 0


def test_hash_password():
    """Test password hashing."""
    password = "secure_password_123"

    hashed = hash_password(password)

    assert isinstance(hashed, str)
    assert hashed != password
    assert len(hashed) > 50  # Bcrypt hashes are long


def test_verify_password():
    """Test password verification."""
    password = "test_password"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True
    assert verify_password("wrong_password", hashed) is False


def test_sanitize_path_valid():
    """Test path sanitization with valid path."""
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        subdir = os.path.join(tmpdir, "subdir")
        os.makedirs(subdir)

        result = sanitize_path(subdir, tmpdir)

        assert result is not None
        assert tmpdir in result


def test_sanitize_path_traversal():
    """Test path sanitization blocks traversal attacks."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        malicious_path = f"{tmpdir}/../../../etc/passwd"

        with pytest.raises(HTTPException) as exc_info:
            sanitize_path(malicious_path, tmpdir)

        assert exc_info.value.status_code == 400


def test_sanitize_path_outside_base():
    """Test path sanitization blocks paths outside allowed base."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir1:
        with tempfile.TemporaryDirectory() as tmpdir2:
            with pytest.raises(HTTPException) as exc_info:
                sanitize_path(tmpdir2, tmpdir1)

            assert exc_info.value.status_code == 400
