"""Tests for backup encryption (AES-256-GCM)."""

import os

import pytest
from cryptography.exceptions import InvalidTag

from gamelibrary.backup.encryption import (
    derive_key,
    encrypt_file,
    decrypt_file,
    encrypt_bytes,
    decrypt_bytes,
    SALT_SIZE,
)


class TestEncryptDecryptFile:
    def test_encrypt_decrypt_file(self, tmp_path):
        original = tmp_path / "data.bin"
        content = b"The quick brown fox jumps over the lazy dog"
        original.write_bytes(content)

        encrypted = tmp_path / "data.bin.enc"
        decrypted = tmp_path / "data_out.bin"

        encrypt_file(original, encrypted, "password123")
        assert encrypted.exists()
        # Encrypted file must differ from original
        assert encrypted.read_bytes() != content

        decrypt_file(encrypted, decrypted, "password123")
        assert decrypted.read_bytes() == content


class TestEncryptDecryptBytes:
    def test_encrypt_decrypt_bytes(self):
        plaintext = b"sensitive achievement data 0123456789"
        password = "strong_password"

        ciphertext = encrypt_bytes(plaintext, password)
        assert ciphertext != plaintext

        result = decrypt_bytes(ciphertext, password)
        assert result == plaintext


class TestWrongPassword:
    def test_wrong_password_fails(self, tmp_path):
        original = tmp_path / "secret.txt"
        original.write_bytes(b"secret content")

        encrypted = tmp_path / "secret.enc"
        decrypted = tmp_path / "secret_out.txt"

        encrypt_file(original, encrypted, "correct_password")

        with pytest.raises(InvalidTag):
            decrypt_file(encrypted, decrypted, "wrong_password")


class TestDeriveKey:
    def test_derive_key_deterministic(self):
        salt = os.urandom(SALT_SIZE)
        key1 = derive_key("mypassword", salt)
        key2 = derive_key("mypassword", salt)
        assert key1 == key2

    def test_derive_key_different_salt(self):
        salt1 = os.urandom(SALT_SIZE)
        salt2 = os.urandom(SALT_SIZE)
        # Extremely unlikely to collide
        key1 = derive_key("mypassword", salt1)
        key2 = derive_key("mypassword", salt2)
        assert key1 != key2
