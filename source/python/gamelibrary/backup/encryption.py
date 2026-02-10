"""AES-256 encryption for backup files."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

logger = logging.getLogger(__name__)

SALT_SIZE = 16
NONCE_SIZE = 12
KEY_SIZE = 32  # 256 bits
ITERATIONS = 600_000
CHUNK_SIZE = 64 * 1024  # 64KB chunks
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB warning threshold


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from a password using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=salt,
        iterations=ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt_file(input_path: str | Path, output_path: str | Path, password: str):
    """Encrypt a file using AES-256-GCM.

    File format: [salt(16)] [nonce(12)] [ciphertext+tag]
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    file_size = input_path.stat().st_size
    if file_size > MAX_FILE_SIZE:
        logger.warning(
            "Encrypting large file (%d MB): %s. This loads the entire file into memory.",
            file_size // (1024 * 1024),
            input_path,
        )

    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)

    plaintext = input_path.read_bytes()
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    with open(output_path, "wb") as f:
        f.write(salt)
        f.write(nonce)
        f.write(ciphertext)
    logger.info("Encrypted %s -> %s (%d bytes)", input_path.name, output_path.name, len(ciphertext))


def decrypt_file(input_path: str | Path, output_path: str | Path, password: str):
    """Decrypt a file encrypted with AES-256-GCM."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    file_size = input_path.stat().st_size
    if file_size > MAX_FILE_SIZE:
        logger.warning(
            "Decrypting large file (%d MB): %s. This loads the entire file into memory.",
            file_size // (1024 * 1024),
            input_path,
        )

    with open(input_path, "rb") as f:
        salt = f.read(SALT_SIZE)
        nonce = f.read(NONCE_SIZE)
        ciphertext = f.read()

    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    output_path.write_bytes(plaintext)
    logger.info("Decrypted %s -> %s (%d bytes)", input_path.name, output_path.name, len(plaintext))


def encrypt_bytes(data: bytes, password: str) -> bytes:
    """Encrypt bytes in memory. Returns salt + nonce + ciphertext."""
    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return salt + nonce + ciphertext


def decrypt_bytes(data: bytes, password: str) -> bytes:
    """Decrypt bytes encrypted with encrypt_bytes."""
    salt = data[:SALT_SIZE]
    nonce = data[SALT_SIZE:SALT_SIZE + NONCE_SIZE]
    ciphertext = data[SALT_SIZE + NONCE_SIZE:]
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)
