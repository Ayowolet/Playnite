"""Unit tests for backup encryption, compression, and verification."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from playnite.backup.compression import CompressionError, compress_directory, decompress
from playnite.backup.encryption import EncryptionError, decrypt_file, encrypt_file
from playnite.backup.verification import BackupVerifier, calculate_file_checksum


# ---------------------------------------------------------------------------
# Encryption / decryption
# ---------------------------------------------------------------------------


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self, tmp_path):
        src = tmp_path / "test.txt"
        src.write_text("Hello, Playnite backup!")
        enc = tmp_path / "test.pnbe"
        dec = tmp_path / "decrypted.txt"

        encrypt_file(src, enc, "secret_password")
        decrypt_file(enc, dec, "secret_password")

        assert dec.read_text() == "Hello, Playnite backup!"

    def test_wrong_password_raises(self, tmp_path):
        src = tmp_path / "data.bin"
        src.write_bytes(b"\x00" * 1024)
        enc = tmp_path / "data.pnbe"
        dec = tmp_path / "data_dec.bin"

        encrypt_file(src, enc, "correct_password")

        with pytest.raises(EncryptionError, match="Decryption failed"):
            decrypt_file(enc, dec, "wrong_password")

    def test_encrypt_produces_magic_header(self, tmp_path):
        src = tmp_path / "h.txt"
        src.write_bytes(b"test data")
        enc = tmp_path / "h.pnbe"
        encrypt_file(src, enc, "pw")
        data = enc.read_bytes()
        assert data[:4] == b"PNBE"

    def test_bad_magic_header_raises(self, tmp_path):
        bad_file = tmp_path / "bad.pnbe"
        bad_file.write_bytes(b"XXXX" + b"\x00" * 100)
        with pytest.raises(EncryptionError, match="Not a Playnite encrypted backup"):
            decrypt_file(bad_file, tmp_path / "out.txt", "pw")

    def test_empty_file_roundtrip(self, tmp_path):
        src = tmp_path / "empty.txt"
        src.write_bytes(b"")
        enc = tmp_path / "empty.pnbe"
        dec = tmp_path / "empty_dec.txt"
        encrypt_file(src, enc, "pw")
        decrypt_file(enc, dec, "pw")
        assert dec.read_bytes() == b""

    def test_encrypt_returns_checksum_hex(self, tmp_path):
        src = tmp_path / "f.txt"
        src.write_bytes(b"abc")
        enc = tmp_path / "f.pnbe"
        checksum = encrypt_file(src, enc, "pw")
        assert len(checksum) == 64  # SHA-256 hex

    def test_large_file_roundtrip(self, tmp_path):
        src = tmp_path / "large.bin"
        src.write_bytes(b"x" * 10 * 1024 * 1024)  # 10 MB
        enc = tmp_path / "large.pnbe"
        dec = tmp_path / "large_dec.bin"
        encrypt_file(src, enc, "large_test_pw")
        decrypt_file(enc, dec, "large_test_pw")
        assert dec.read_bytes() == src.read_bytes()


# ---------------------------------------------------------------------------
# Compression / decompression
# ---------------------------------------------------------------------------


class TestCompression:
    def _make_tree(self, root: Path) -> None:
        (root / "a.txt").write_text("file a")
        (root / "subdir").mkdir()
        (root / "subdir" / "b.txt").write_text("file b")

    def test_compress_and_decompress(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        self._make_tree(src)

        archive = tmp_path / "archive.pnb"
        compress_directory(src, archive)

        assert archive.exists()
        assert archive.stat().st_size > 0

        dest = tmp_path / "restored"
        names = decompress(archive, dest)
        assert any("a.txt" in n for n in names)
        assert (dest / "a.txt").read_text() == "file a"
        assert (dest / "subdir" / "b.txt").read_text() == "file b"

    def test_compress_returns_sha256(self, tmp_path):
        src = tmp_path / "src2"
        src.mkdir()
        (src / "c.txt").write_text("c")
        archive = tmp_path / "out.pnb"
        ck = compress_directory(src, archive)
        assert len(ck) == 64

    def test_decompress_bad_zip_raises(self, tmp_path):
        bad = tmp_path / "bad.pnb"
        bad.write_bytes(b"this is not a zip file")
        with pytest.raises(CompressionError):
            decompress(bad, tmp_path / "out")

    def test_empty_directory(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        archive = tmp_path / "empty.pnb"
        compress_directory(empty, archive)
        dest = tmp_path / "empty_out"
        names = decompress(archive, dest)
        assert names == []

    def test_checksum_stability(self, tmp_path):
        """Two compression calls on the same content should produce stable archives."""
        src = tmp_path / "stable"
        src.mkdir()
        (src / "x.txt").write_text("hello")
        a1 = tmp_path / "a1.pnb"
        a2 = tmp_path / "a2.pnb"
        compress_directory(src, a1)
        compress_directory(src, a2)
        # Both archives should contain the same entry
        with zipfile.ZipFile(a1) as z1, zipfile.ZipFile(a2) as z2:
            assert set(z1.namelist()) == set(z2.namelist())


# ---------------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------------


class TestChecksum:
    def test_sha256_known_value(self, tmp_path):
        import hashlib
        content = b"playnite test"
        f = tmp_path / "f.bin"
        f.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert calculate_file_checksum(f) == expected

    def test_different_files_differ(self, tmp_path):
        f1 = tmp_path / "f1.bin"
        f2 = tmp_path / "f2.bin"
        f1.write_bytes(b"aaa")
        f2.write_bytes(b"bbb")
        assert calculate_file_checksum(f1) != calculate_file_checksum(f2)

    def test_identical_files_same_checksum(self, tmp_path):
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        content = b"same content"
        f1.write_bytes(content)
        f2.write_bytes(content)
        assert calculate_file_checksum(f1) == calculate_file_checksum(f2)


# ---------------------------------------------------------------------------
# Backup verification
# ---------------------------------------------------------------------------


class TestBackupVerifier:
    def test_verify_valid_backup(self, tmp_db, tmp_config, tmp_path):
        """A correctly created backup should pass all checks."""
        from playnite.backup.manager import BackupManager

        # Create a small file to back up
        Path(tmp_config.data_dir).mkdir(parents=True, exist_ok=True)
        db_file = Path(tmp_config.database_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        db_file.write_bytes(b"fake sqlite db")

        mgr = BackupManager(tmp_config, tmp_db)
        result = mgr.create_full_backup(destination=str(tmp_path / "backups"))
        assert result.success

        report = mgr.verify_backup(result.job_id)
        assert report["passed"], f"Verification checks: {report['checks']}"

    def test_verify_missing_file(self, tmp_db, tmp_config, tmp_path):
        """Verification should fail if the archive file has been deleted."""
        from playnite.backup.manager import BackupManager

        Path(tmp_config.database_path).parent.mkdir(parents=True, exist_ok=True)
        Path(tmp_config.database_path).write_bytes(b"db")

        mgr = BackupManager(tmp_config, tmp_db)
        result = mgr.create_full_backup(destination=str(tmp_path / "backups"))

        # Delete the file
        Path(result.backup_path).unlink()

        report = mgr.verify_backup(result.job_id)
        assert not report["passed"]
        assert any(not c["passed"] for c in report["checks"])

    def test_verify_corrupted_archive(self, tmp_db, tmp_config, tmp_path):
        """Verification should fail on a corrupted ZIP."""
        from playnite.backup.manager import BackupManager

        Path(tmp_config.database_path).parent.mkdir(parents=True, exist_ok=True)
        Path(tmp_config.database_path).write_bytes(b"db")

        mgr = BackupManager(tmp_config, tmp_db)
        result = mgr.create_full_backup(destination=str(tmp_path / "backups"))

        # Corrupt the archive
        archive = Path(result.backup_path)
        data = archive.read_bytes()
        archive.write_bytes(data[:50] + b"\xff\xfe\xfd" + data[53:])

        report = mgr.verify_backup(result.job_id)
        assert not report["passed"]

    def test_verify_encrypted_backup(self, tmp_db, tmp_config, tmp_path):
        """Encrypted backups pass verification when correct password is given."""
        from playnite.backup.manager import BackupManager

        Path(tmp_config.database_path).parent.mkdir(parents=True, exist_ok=True)
        Path(tmp_config.database_path).write_bytes(b"db content")

        mgr = BackupManager(tmp_config, tmp_db)
        result = mgr.create_full_backup(
            destination=str(tmp_path / "backups"),
            password="secure_password",
        )
        assert result.encrypted

        report = mgr.verify_backup(result.job_id, password="secure_password")
        assert report["passed"], f"Verification checks: {report['checks']}"

    def test_verify_encrypted_wrong_password(self, tmp_db, tmp_config, tmp_path):
        """Encrypted backup verification fails with wrong password."""
        from playnite.backup.manager import BackupManager

        Path(tmp_config.database_path).parent.mkdir(parents=True, exist_ok=True)
        Path(tmp_config.database_path).write_bytes(b"db content")

        mgr = BackupManager(tmp_config, tmp_db)
        result = mgr.create_full_backup(
            destination=str(tmp_path / "backups"),
            password="correct_pw",
        )

        report = mgr.verify_backup(result.job_id, password="wrong_pw")
        assert not report["passed"]
