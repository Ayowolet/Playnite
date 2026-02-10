"""Additional tests for backup/compression.py covering compress_files,
list_archive_contents, compression_ratio, and decompress error paths."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from playnite.backup.compression import (
    CompressionError,
    compress_directory,
    compress_files,
    compression_ratio,
    decompress,
    list_archive_contents,
)


# ---------------------------------------------------------------------------
# compress_files
# ---------------------------------------------------------------------------


class TestCompressFiles:
    def test_compress_files_basic(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")

        archive = tmp_path / "out.pnb"
        checksum = compress_files([(f1, "a.txt"), (f2, "b.txt")], archive)

        assert archive.exists()
        assert len(checksum) == 64
        with zipfile.ZipFile(archive, "r") as zf:
            assert set(zf.namelist()) == {"a.txt", "b.txt"}
            assert zf.read("a.txt") == b"content A"
            assert zf.read("b.txt") == b"content B"

    def test_compress_files_skips_missing_files(self, tmp_path):
        existing = tmp_path / "real.txt"
        existing.write_bytes(b"I exist")
        missing = tmp_path / "ghost.txt"  # does not exist

        archive = tmp_path / "partial.pnb"
        compress_files([(existing, "real.txt"), (missing, "ghost.txt")], archive)

        with zipfile.ZipFile(archive, "r") as zf:
            assert "real.txt" in zf.namelist()
            assert "ghost.txt" not in zf.namelist()

    def test_compress_files_returns_sha256_hex(self, tmp_path):
        f = tmp_path / "f.txt"
        f.write_bytes(b"test")
        archive = tmp_path / "f.pnb"
        ck = compress_files([(f, "f.txt")], archive)
        assert len(ck) == 64
        assert all(c in "0123456789abcdef" for c in ck)

    def test_compress_files_creates_parent_dirs(self, tmp_path):
        f = tmp_path / "f.txt"
        f.write_bytes(b"data")
        # Archive in a sub-directory that does not yet exist
        archive = tmp_path / "sub" / "archive.pnb"
        compress_files([(f, "f.txt")], archive)
        assert archive.exists()

    def test_compress_files_arcname_used_in_archive(self, tmp_path):
        f = tmp_path / "original_name.txt"
        f.write_bytes(b"renamed")
        archive = tmp_path / "renamed.pnb"
        compress_files([(f, "different_name.txt")], archive)
        with zipfile.ZipFile(archive, "r") as zf:
            assert "different_name.txt" in zf.namelist()
            assert "original_name.txt" not in zf.namelist()


# ---------------------------------------------------------------------------
# list_archive_contents
# ---------------------------------------------------------------------------


class TestListArchiveContents:
    def _make_archive(self, tmp_path: Path, members: dict[str, bytes]) -> Path:
        archive = tmp_path / "archive.pnb"
        with zipfile.ZipFile(archive, "w") as zf:
            for name, content in members.items():
                zf.writestr(name, content)
        return archive

    def test_lists_file_metadata(self, tmp_path):
        archive = self._make_archive(tmp_path, {"a.txt": b"hello", "b.txt": b"world!"})
        contents = list_archive_contents(archive)
        names = {item["name"] for item in contents}
        assert "a.txt" in names
        assert "b.txt" in names

    def test_each_entry_has_required_keys(self, tmp_path):
        archive = self._make_archive(tmp_path, {"x.txt": b"x"})
        contents = list_archive_contents(archive)
        assert len(contents) == 1
        entry = contents[0]
        assert "name" in entry
        assert "size" in entry
        assert "compressed_size" in entry
        assert "date_time" in entry

    def test_size_matches_content_length(self, tmp_path):
        content = b"0123456789"
        archive = self._make_archive(tmp_path, {"data.bin": content})
        contents = list_archive_contents(archive)
        assert contents[0]["size"] == len(content)

    def test_empty_archive_returns_empty_list(self, tmp_path):
        archive = tmp_path / "empty.pnb"
        with zipfile.ZipFile(archive, "w"):
            pass
        contents = list_archive_contents(archive)
        assert contents == []

    def test_invalid_archive_raises_compression_error(self, tmp_path):
        bad = tmp_path / "bad.pnb"
        bad.write_bytes(b"not a zip file at all")
        with pytest.raises(CompressionError):
            list_archive_contents(bad)


# ---------------------------------------------------------------------------
# compression_ratio
# ---------------------------------------------------------------------------


class TestCompressionRatio:
    def test_ratio_between_zero_and_one_for_compressible(self, tmp_path):
        # Highly compressible content (repeated bytes)
        src = tmp_path / "src"
        src.mkdir()
        (src / "big.txt").write_bytes(b"a" * 50000)
        archive = tmp_path / "compressible.pnb"
        compress_directory(src, archive)
        ratio = compression_ratio(archive)
        # Ratio should be well below 1.0 for repeated content
        assert 0.0 < ratio <= 1.0

    def test_ratio_returns_float(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "f.txt").write_bytes(b"some data")
        archive = tmp_path / "test.pnb"
        compress_directory(src, archive)
        ratio = compression_ratio(archive)
        assert isinstance(ratio, float)

    def test_ratio_on_bad_archive_returns_one(self, tmp_path):
        bad = tmp_path / "bad.pnb"
        bad.write_bytes(b"garbage data")
        ratio = compression_ratio(bad)
        assert ratio == 1.0

    def test_empty_archive_returns_one(self, tmp_path):
        archive = tmp_path / "empty.pnb"
        with zipfile.ZipFile(archive, "w"):
            pass
        ratio = compression_ratio(archive)
        assert ratio == 1.0


# ---------------------------------------------------------------------------
# decompress — error paths
# ---------------------------------------------------------------------------


class TestDecompressErrorPaths:
    def test_path_traversal_in_zip_raises_compression_error(self, tmp_path):
        """A zip-slip member should raise CompressionError."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../traversal.txt", b"evil")
        archive = tmp_path / "slip.pnb"
        archive.write_bytes(buf.getvalue())
        dest = tmp_path / "dest"
        dest.mkdir()
        with pytest.raises(CompressionError):
            decompress(archive, dest)

    def test_bad_zip_raises_compression_error(self, tmp_path):
        bad = tmp_path / "bad.pnb"
        bad.write_bytes(b"not a valid zip")
        with pytest.raises(CompressionError, match="[Ii]nvalid ZIP"):
            decompress(bad, tmp_path / "dest")
