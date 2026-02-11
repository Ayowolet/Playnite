"""Media file handling for library merging."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from ..models.game import Game


class MediaHandler:
    """Handles copying media files (icons, covers, backgrounds) between libraries."""

    def __init__(self, source_lib_path: str | Path, target_lib_path: str | Path):
        self.source_files = Path(source_lib_path) / "files"
        self.target_files = Path(target_lib_path) / "files"

    def copy_media(self, source_game: Game, target_game: Game) -> int:
        """Copy media files from source game to target library.

        Returns number of files copied.
        """
        copied = 0
        for field_name in ("icon", "cover_image", "background_image"):
            src_ref = getattr(source_game, field_name, None)
            if src_ref and self._is_db_file_ref(src_ref):
                if self._copy_file(src_ref):
                    setattr(target_game, field_name, src_ref)
                    copied += 1
        return copied

    def _is_db_file_ref(self, ref: str) -> bool:
        """Check if a media reference is a database file ID (not URL or absolute path)."""
        lower = ref.lower()
        if lower.startswith(("http://", "https://", "/")):
            return False
        # Playnite stores DB file refs as just a filename or guid-based name
        return not Path(ref).is_absolute()

    def _copy_file(self, file_ref: str) -> bool:
        """Copy a file from source to target files/ directory."""
        source_path = self.source_files / file_ref
        target_path = self.target_files / file_ref

        if not source_path.exists():
            return False

        # Avoid self-copy when source and target resolve to the same file
        if os.path.normcase(str(source_path)) == os.path.normcase(str(target_path)):
            return False

        if target_path.exists():
            # Skip if identical (hash comparison)
            if self._files_identical(source_path, target_path):
                return False

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        return True

    @staticmethod
    def _files_identical(a: Path, b: Path) -> bool:
        """Compare two files by SHA-256 hash."""
        def _hash(p: Path) -> str:
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()
        return _hash(a) == _hash(b)

    def count_media_to_copy(self, source_game: Game) -> int:
        """Count how many media files would be copied for a game."""
        count = 0
        for field_name in ("icon", "cover_image", "background_image"):
            ref = getattr(source_game, field_name, None)
            if ref and self._is_db_file_ref(ref):
                source_path = self.source_files / ref
                if source_path.exists():
                    count += 1
        return count
