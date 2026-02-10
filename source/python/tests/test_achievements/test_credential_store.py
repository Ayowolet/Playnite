"""Tests for credential encryption at rest."""

import json
import os
import stat

import pytest

from gamelibrary.achievements.credential_store import (
    encrypt_credentials,
    decrypt_credentials,
    is_encrypted,
    _get_or_create_key,
)


@pytest.fixture
def keyfile(tmp_path):
    """Provide a temporary keyfile path for isolation."""
    return tmp_path / ".cred_key"


class TestEncryptDecryptRoundtrip:
    def test_roundtrip(self, keyfile):
        creds = {"api_key": "sk-12345", "steam_id": "76561198000000000"}
        encrypted = encrypt_credentials(creds, keyfile_path=keyfile)
        decrypted = decrypt_credentials(encrypted, keyfile_path=keyfile)
        assert decrypted == creds

    def test_roundtrip_complex_creds(self, keyfile):
        creds = {
            "access_token": "tok_abc",
            "refresh_token": "ref_xyz",
            "user_id": "12345",
            "client_id": "client",
            "client_secret": "secret",
        }
        encrypted = encrypt_credentials(creds, keyfile_path=keyfile)
        decrypted = decrypt_credentials(encrypted, keyfile_path=keyfile)
        assert decrypted == creds

    def test_roundtrip_empty_creds(self, keyfile):
        creds = {}
        encrypted = encrypt_credentials(creds, keyfile_path=keyfile)
        decrypted = decrypt_credentials(encrypted, keyfile_path=keyfile)
        assert decrypted == creds


class TestBackwardCompatibility:
    def test_decrypt_plain_json(self, keyfile):
        plain = json.dumps({"api_key": "old_key", "steam_id": "123"})
        result = decrypt_credentials(plain, keyfile_path=keyfile)
        assert result == {"api_key": "old_key", "steam_id": "123"}

    def test_decrypt_empty_string(self, keyfile):
        assert decrypt_credentials("", keyfile_path=keyfile) == {}

    def test_decrypt_none(self, keyfile):
        assert decrypt_credentials(None, keyfile_path=keyfile) == {}

    def test_decrypt_malformed_json(self, keyfile):
        result = decrypt_credentials("not json at all", keyfile_path=keyfile)
        assert result == {}


class TestIsEncrypted:
    def test_encrypted_value(self, keyfile):
        encrypted = encrypt_credentials({"key": "val"}, keyfile_path=keyfile)
        assert is_encrypted(encrypted) is True

    def test_plain_json(self):
        assert is_encrypted('{"key": "val"}') is False

    def test_empty_string(self):
        assert is_encrypted("") is False

    def test_none(self):
        assert is_encrypted(None) is False


class TestEncryptedPrefix:
    def test_uses_prefix(self, keyfile):
        encrypted = encrypt_credentials({"k": "v"}, keyfile_path=keyfile)
        assert encrypted.startswith("GLENC1:")


class TestKeyfileCreation:
    def test_keyfile_created(self, keyfile):
        assert not keyfile.exists()
        _get_or_create_key(keyfile)
        assert keyfile.exists()

    def test_keyfile_restricted_permissions(self, keyfile):
        _get_or_create_key(keyfile)
        mode = os.stat(keyfile).st_mode
        assert mode & stat.S_IRWXG == 0  # No group permissions
        assert mode & stat.S_IRWXO == 0  # No other permissions

    def test_keyfile_reused(self, keyfile):
        key1 = _get_or_create_key(keyfile)
        key2 = _get_or_create_key(keyfile)
        assert key1 == key2

    def test_different_keyfiles_produce_different_ciphertext(self, tmp_path):
        kf1 = tmp_path / "key1"
        kf2 = tmp_path / "key2"
        creds = {"api_key": "test"}
        enc1 = encrypt_credentials(creds, keyfile_path=kf1)
        enc2 = encrypt_credentials(creds, keyfile_path=kf2)
        assert enc1 != enc2  # Different keys produce different ciphertext


class TestWrongKey:
    def test_wrong_key_fails(self, tmp_path):
        kf1 = tmp_path / "key1"
        kf2 = tmp_path / "key2"
        creds = {"api_key": "secret"}
        encrypted = encrypt_credentials(creds, keyfile_path=kf1)
        with pytest.raises(Exception):
            decrypt_credentials(encrypted, keyfile_path=kf2)
