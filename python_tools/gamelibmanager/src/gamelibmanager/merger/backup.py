"""Pre-merge backup using ZIP archives."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

# File extensions that belong to SQLite and should be skipped during
# file-level backup when we use the SQLite backup API instead.
_SQLITE_EXTENSIONS = {".db", ".db-wal", ".db-shm"}


class MergeBackup:
    """Creates and restores ZIP backups of a Playnite library directory."""

    BACKUP_DATE_FORMAT = "%Y-%m-%d-%H-%M-%S"
    BACKUP_PREFIX = "PlayniteLibMergeBackup"

    def __init__(self, library_path: str | Path, backup_dir: str | Path):
        self.library_path = Path(library_path)
        self.backup_dir = Path(backup_dir)

    def create_backup(
        self,
        include_media: bool = True,
        db_conn: sqlite3.Connection | None = None,
    ) -> str:
        """Create ZIP backup of the library. Returns path to backup file.

        Parameters
        ----------
        include_media:
            When *False*, the ``files/`` media directory is excluded.
        db_conn:
            When provided, the ``.db`` file is snapshotted using the
            SQLite online backup API (``conn.backup()``) for a
            consistent copy even while the database is open by another
            process.  Raw ``.db``/``.db-wal``/``.db-shm`` files are
            excluded from the file walk and replaced by the backup copy.
        """
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime(self.BACKUP_DATE_FORMAT)
        filename = f"{self.BACKUP_PREFIX}_{ts}.zip"
        backup_path = self.backup_dir / filename

        # If we have a live DB connection, snapshot the database first.
        tmp_db_path: str | None = None
        if db_conn is not None:
            tmp_fd, tmp_db_path = tempfile.mkstemp(suffix=".db")
            os.close(tmp_fd)
            dest = sqlite3.connect(tmp_db_path)
            try:
                db_conn.backup(dest)
            finally:
                dest.close()

        try:
            with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # Add the SQLite backup copy under the original DB name.
                if tmp_db_path is not None:
                    # Discover the original .db filename relative to library.
                    db_arcname = self._find_db_arcname()
                    if db_arcname:
                        zf.write(tmp_db_path, db_arcname)

                for root, dirs, files in os.walk(self.library_path):
                    rel_root = Path(root).relative_to(self.library_path)
                    if not include_media and os.path.normcase(
                        str(rel_root)
                    ).startswith(os.path.normcase("files")):
                        continue
                    for file in files:
                        # Skip raw SQLite files when using backup API.
                        if db_conn is not None and Path(file).suffix.lower() in _SQLITE_EXTENSIONS:
                            continue
                        file_path = Path(root) / file
                        arcname = str(file_path.relative_to(self.library_path))
                        zf.write(file_path, arcname)
        finally:
            if tmp_db_path is not None:
                os.unlink(tmp_db_path)

        return str(backup_path)

    def _find_db_arcname(self) -> str | None:
        """Return the archive name of the first .db file in the library root."""
        for entry in self.library_path.iterdir():
            if entry.is_file() and entry.suffix.lower() == ".db":
                return entry.name
        return None

    def restore_backup(self, backup_path: str | Path) -> None:
        """Restore library from a backup ZIP file."""
        bp = Path(backup_path)
        if not bp.exists():
            raise FileNotFoundError(f"Backup file not found: {bp}")

        with zipfile.ZipFile(bp, "r") as zf:
            zf.extractall(self.library_path)

    @staticmethod
    def list_backups(backup_dir: str | Path) -> list[tuple[str, datetime]]:
        """List available backups with timestamps, newest first."""
        bd = Path(backup_dir)
        if not bd.exists():
            return []
        backups = []
        for fp in bd.glob(f"{MergeBackup.BACKUP_PREFIX}_*.zip"):
            try:
                ts_str = fp.stem.replace(f"{MergeBackup.BACKUP_PREFIX}_", "")
                ts = datetime.strptime(ts_str, MergeBackup.BACKUP_DATE_FORMAT)
                backups.append((str(fp), ts))
            except ValueError:
                continue
        backups.sort(key=lambda x: x[1], reverse=True)
        return backups
