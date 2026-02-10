"""Credential encryption for platform secrets at rest."""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path

from ..backup.encryption import encrypt_bytes, decrypt_bytes

logger = logging.getLogger(__name__)

_ENCRYPTED_PREFIX = "GLENC1:"


def _default_keyfile_path() -> Path:
    """Return the default keyfile path next to the database directory."""
    return Path.home() / ".gamelibrary" / ".cred_key"


def _get_or_create_key(keyfile_path: Path | None = None) -> str:
    """Load or generate a machine-local encryption key."""
    keyfile_path = keyfile_path or _default_keyfile_path()
    if keyfile_path.exists():
        return keyfile_path.read_text().strip()
    keyfile_path.parent.mkdir(parents=True, exist_ok=True)
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    keyfile_path.write_text(key)
    try:
        os.chmod(keyfile_path, 0o600)
    except OSError:
        pass  # Windows doesn't support chmod the same way
    logger.info("Generated new credential encryption key at %s", keyfile_path)
    return key


def encrypt_credentials(
    credentials: dict,
    password: str | None = None,
    keyfile_path: Path | None = None,
) -> str:
    """Encrypt a credentials dict to a prefixed base64 string."""
    password = password or _get_or_create_key(keyfile_path)
    plaintext = json.dumps(credentials).encode("utf-8")
    encrypted = encrypt_bytes(plaintext, password)
    return _ENCRYPTED_PREFIX + base64.b64encode(encrypted).decode("ascii")


def decrypt_credentials(
    stored_value: str,
    password: str | None = None,
    keyfile_path: Path | None = None,
) -> dict:
    """Decrypt a stored credential string.

    Falls back to plain JSON parsing for backward compatibility with
    databases that predate credential encryption.
    """
    if not stored_value:
        return {}
    if stored_value.startswith(_ENCRYPTED_PREFIX):
        password = password or _get_or_create_key(keyfile_path)
        raw = base64.b64decode(stored_value[len(_ENCRYPTED_PREFIX) :])
        plaintext = decrypt_bytes(raw, password)
        return json.loads(plaintext.decode("utf-8"))
    # Backward compatibility: treat as plain JSON
    try:
        return json.loads(stored_value)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Malformed credential data, returning empty dict")
        return {}


def is_encrypted(stored_value: str) -> bool:
    """Check whether a stored value uses the encrypted format."""
    return isinstance(stored_value, str) and stored_value.startswith(
        _ENCRYPTED_PREFIX
    )
