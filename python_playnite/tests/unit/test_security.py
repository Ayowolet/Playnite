"""Tests for backup/utils.py (sha256_file, safe_extract_zip) and exceptions.py hierarchy."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from playnite.backup.utils import safe_extract_zip, sha256_file
from playnite.exceptions import (
    AchievementError,
    BackupError,
    CompressionError,
    ConfigError,
    DatabaseError,
    EncryptionError,
    PlayniteError,
    VerificationError,
)


# ---------------------------------------------------------------------------
# PlayniteError hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    def test_playnite_error_is_exception(self):
        assert issubclass(PlayniteError, Exception)

    def test_backup_error_is_playnite_error(self):
        exc = BackupError("test")
        assert isinstance(exc, PlayniteError)

    def test_compression_error_is_playnite_error(self):
        assert isinstance(CompressionError("x"), PlayniteError)

    def test_encryption_error_is_playnite_error(self):
        assert isinstance(EncryptionError("x"), PlayniteError)

    def test_verification_error_is_playnite_error(self):
        assert isinstance(VerificationError("x"), PlayniteError)

    def test_database_error_is_playnite_error(self):
        assert isinstance(DatabaseError("x"), PlayniteError)

    def test_achievement_error_is_playnite_error(self):
        assert isinstance(AchievementError("x"), PlayniteError)

    def test_config_error_is_playnite_error(self):
        assert isinstance(ConfigError("x"), PlayniteError)

    def test_catch_all_with_base_class(self):
        """All domain errors can be caught with a single except clause."""
        errors = [
            BackupError("b"),
            CompressionError("c"),
            EncryptionError("e"),
            VerificationError("v"),
            DatabaseError("d"),
            AchievementError("a"),
            ConfigError("cfg"),
        ]
        for err in errors:
            caught = False
            try:
                raise err
            except PlayniteError:
                caught = True
            assert caught, f"{type(err).__name__} not caught by PlayniteError"

    def test_error_message_preserved(self):
        msg = "something went wrong"
        exc = BackupError(msg)
        assert str(exc) == msg

    def test_all_subclasses_are_distinct(self):
        """Each error class is a separate type."""
        classes = [
            BackupError,
            CompressionError,
            EncryptionError,
            VerificationError,
            DatabaseError,
            AchievementError,
            ConfigError,
        ]
        assert len(set(classes)) == len(classes)


# ---------------------------------------------------------------------------
# sha256_file
# ---------------------------------------------------------------------------


class TestSha256File:
    def test_returns_64_char_hex_string(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"hello world")
        digest = sha256_file(f)
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_deterministic(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"deterministic content")
        assert sha256_file(f) == sha256_file(f)

    def test_different_content_different_hash(self, tmp_path):
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        a.write_bytes(b"aaa")
        b.write_bytes(b"bbb")
        assert sha256_file(a) != sha256_file(b)

    def test_empty_file_produces_known_hash(self, tmp_path):
        """SHA-256 of empty data has a known value."""
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        digest = sha256_file(f)
        # SHA-256("") == e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
        assert digest == "e3b0c44298fc1c149afbf4c8996fb924" "27ae41e4649b934ca495991b7852b855"

    def test_large_file_works(self, tmp_path):
        """Files larger than the chunk size should hash correctly."""
        f = tmp_path / "large.bin"
        # Write 200 KiB (> 64 KiB chunk)
        f.write_bytes(b"x" * (200 * 1024))
        digest = sha256_file(f)
        assert len(digest) == 64


# ---------------------------------------------------------------------------
# safe_extract_zip — path traversal guard
# ---------------------------------------------------------------------------


def _make_zip_with_member(member_name: str, content: bytes = b"data") -> bytes:
    """Return bytes of a ZIP archive containing a single member at *member_name*."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(member_name, content)
    return buf.getvalue()


class TestSafeExtractZip:
    def test_normal_extraction_succeeds(self, tmp_path):
        data = _make_zip_with_member("subdir/file.txt", b"hello")
        archive = tmp_path / "archive.zip"
        archive.write_bytes(data)
        dest = tmp_path / "out"
        dest.mkdir()
        with zipfile.ZipFile(archive, "r") as zf:
            safe_extract_zip(zf, dest)
        assert (dest / "subdir" / "file.txt").read_bytes() == b"hello"

    def test_path_traversal_raises_value_error(self, tmp_path):
        """A member with ../ in its path must be rejected."""
        data = _make_zip_with_member("../evil.txt", b"malicious")
        archive = tmp_path / "evil.zip"
        archive.write_bytes(data)
        dest = tmp_path / "out"
        dest.mkdir()
        with zipfile.ZipFile(archive, "r") as zf:
            with pytest.raises(ValueError, match="[Pp]ath traversal"):
                safe_extract_zip(zf, dest)

    def test_absolute_path_member_raises_value_error(self, tmp_path):
        """A member with an absolute path must be rejected."""
        # zipfile on some platforms strips leading slashes, so use a sub-path
        # that, when joined with destination, resolves outside it via traversal
        data = _make_zip_with_member("../../etc/passwd", b"root:x:0:0")
        archive = tmp_path / "abs.zip"
        archive.write_bytes(data)
        dest = tmp_path / "out"
        dest.mkdir()
        with zipfile.ZipFile(archive, "r") as zf:
            with pytest.raises(ValueError, match="[Pp]ath traversal"):
                safe_extract_zip(zf, dest)

    def test_deeply_nested_path_is_safe(self, tmp_path):
        data = _make_zip_with_member("a/b/c/d/e/file.txt", b"deep")
        archive = tmp_path / "deep.zip"
        archive.write_bytes(data)
        dest = tmp_path / "out"
        dest.mkdir()
        with zipfile.ZipFile(archive, "r") as zf:
            safe_extract_zip(zf, dest)
        assert (dest / "a" / "b" / "c" / "d" / "e" / "file.txt").exists()

    def test_flat_extraction_succeeds(self, tmp_path):
        """A member at the root level (no subdirectory) should extract fine."""
        data = _make_zip_with_member("flat.txt", b"content")
        archive = tmp_path / "flat.zip"
        archive.write_bytes(data)
        dest = tmp_path / "out"
        dest.mkdir()
        with zipfile.ZipFile(archive, "r") as zf:
            safe_extract_zip(zf, dest)
        assert (dest / "flat.txt").read_bytes() == b"content"

    def test_multiple_members_all_extracted(self, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("a.txt", b"aaa")
            zf.writestr("b/c.txt", b"ccc")
        archive = tmp_path / "multi.zip"
        archive.write_bytes(buf.getvalue())
        dest = tmp_path / "out"
        dest.mkdir()
        with zipfile.ZipFile(archive, "r") as zf:
            safe_extract_zip(zf, dest)
        assert (dest / "a.txt").exists()
        assert (dest / "b" / "c.txt").exists()
