"""Security utilities for authentication and authorization."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from loguru import logger

from .config import settings

# Security schemes
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> bool:
    """
    Verify API key for authentication.

    Args:
        api_key: API key from header

    Returns:
        True if valid

    Raises:
        HTTPException: If API key is invalid or missing
    """
    if not settings.enable_api_key_auth:
        return True  # Auth disabled

    if not api_key:
        logger.warning("Missing API key in request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key != settings.api_key:
        logger.warning(f"Invalid API key attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return True


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT access token.

    Args:
        data: Data to encode in token
        expires_delta: Token expiration time

    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )

    return encoded_jwt


def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
) -> dict:
    """
    Verify JWT token.

    Args:
        credentials: Bearer token credentials

    Returns:
        Decoded token data

    Raises:
        HTTPException: If token is invalid or expired
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload

    except JWTError as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def sanitize_path(path: str, allowed_base: str) -> str:
    """
    Sanitize file path to prevent path traversal attacks.

    Args:
        path: User-provided path
        allowed_base: Base directory that paths must be within

    Returns:
        Sanitized path

    Raises:
        HTTPException: If path is invalid or outside allowed base
    """
    from pathlib import Path

    try:
        # Resolve to absolute path
        resolved_path = Path(path).resolve()
        allowed_path = Path(allowed_base).resolve()

        # Check if path is within allowed base
        if not str(resolved_path).startswith(str(allowed_path)):
            raise ValueError("Path outside allowed directory")

        return str(resolved_path)

    except (ValueError, OSError) as e:
        logger.warning(f"Path sanitization failed for {path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path"
        )
