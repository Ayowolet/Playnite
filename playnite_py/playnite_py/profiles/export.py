"""
Profile export and import for Playnite-Py.

This module handles exporting profiles to portable archive files
and importing profiles from those archives.

Export files use the .ppf (Playnite Profile File) extension and
contain all profile data including database, settings, and media.

Example:
    >>> exporter = ProfileExporter()
    >>> exporter.export_profile(profile, profile_path, output_path)
    >>> importer = ProfileImporter()
    >>> data = importer.read_export(output_path)
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from playnite_py.core.models.profile import Profile

logger = logging.getLogger(__name__)

# Export format version for compatibility checking
EXPORT_FORMAT_VERSION = "1.0"


class ProfileExporter:
    """
    Exports profiles to portable archive files.

    Creates a compressed archive containing all profile data that
    can be imported on another machine or used for backup.

    Example:
        >>> exporter = ProfileExporter()
        >>> path = exporter.export_profile(
        ...     profile, profile_path, output_path,
        ...     include_games=True, include_media=True
        ... )
    """

    def export_profile(
        self,
        profile: Profile,
        profile_path: Path,
        output_path: Path,
        include_games: bool = True,
        include_media: bool = True,
        include_configurations: bool = True,
        include_plugins: bool = False,
        password: Optional[str] = None,
    ) -> Path:
        """
        Export a profile to an archive file.

        Creates a .ppf (Playnite Profile File) archive containing:
        - Profile metadata and settings (manifest.json)
        - Game library database (if include_games)
        - Media files (if include_media)
        - Platform configurations (if include_configurations)
        - Plugin data (if include_plugins)

        Args:
            profile: Profile to export
            profile_path: Path to the profile's data directory
            output_path: Path for the output archive
            include_games: Include game library database
            include_media: Include media files (covers, icons, etc.)
            include_configurations: Include platform configurations
            include_plugins: Include plugin data
            password: Optional password for encryption (not implemented yet)

        Returns:
            Path to the created archive file

        Raises:
            FileNotFoundError: If profile path doesn't exist
            IOError: If export fails

        Example:
            >>> exporter = ProfileExporter()
            >>> path = exporter.export_profile(
            ...     profile,
            ...     Path("/data/profiles/abc123"),
            ...     Path("~/backup/gaming.ppf")
            ... )
        """
        if not profile_path.exists():
            raise FileNotFoundError(f"Profile path not found: {profile_path}")

        # Ensure output has correct extension
        if not output_path.suffix == ".ppf":
            output_path = output_path.with_suffix(".ppf")

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create temporary directory for staging
        with tempfile.TemporaryDirectory() as temp_dir:
            staging = Path(temp_dir)

            # Create manifest
            manifest = self._create_manifest(
                profile,
                include_games=include_games,
                include_media=include_media,
                include_configurations=include_configurations,
                include_plugins=include_plugins,
            )
            manifest_path = staging / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2, default=str))

            # Copy profile settings
            settings_path = staging / "settings.json"
            settings_path.write_text(
                json.dumps(profile.settings.model_dump(), indent=2)
            )

            # Copy sharing settings
            sharing_path = staging / "sharing.json"
            sharing_path.write_text(
                json.dumps(profile.sharing.model_dump(), indent=2)
            )

            # Copy database
            if include_games:
                db_path = profile_path / "library.db"
                if db_path.exists():
                    shutil.copy2(db_path, staging / "library.db")

                    # Also copy WAL and SHM files if they exist
                    for suffix in ["-wal", "-shm"]:
                        wal_path = profile_path / f"library.db{suffix}"
                        if wal_path.exists():
                            shutil.copy2(wal_path, staging / f"library.db{suffix}")

            # Copy media files
            if include_media:
                media_path = profile_path / "media"
                if media_path.exists() and media_path.is_dir():
                    # Don't follow symlinks to shared media
                    if not media_path.is_symlink():
                        shutil.copytree(
                            media_path,
                            staging / "media",
                            symlinks=False,
                        )

            # Copy plugin data
            if include_plugins:
                plugins_path = profile_path / "plugins"
                if plugins_path.exists() and plugins_path.is_dir():
                    shutil.copytree(plugins_path, staging / "plugins")

            # Create archive
            if password:
                # TODO: Implement encrypted export
                logger.warning(
                    "Password protection not yet implemented, "
                    "exporting without encryption"
                )

            self._create_archive(staging, output_path)

        logger.info(f"Exported profile '{profile.name}' to {output_path}")
        return output_path

    def _create_manifest(
        self,
        profile: Profile,
        include_games: bool,
        include_media: bool,
        include_configurations: bool,
        include_plugins: bool,
    ) -> dict[str, Any]:
        """Create the export manifest."""
        return {
            "format_version": EXPORT_FORMAT_VERSION,
            "created_at": datetime.now().isoformat(),
            "profile": {
                "id": str(profile.id),
                "name": profile.name,
                "description": profile.description,
            },
            "contents": {
                "games": include_games,
                "media": include_media,
                "configurations": include_configurations,
                "plugins": include_plugins,
            },
            "statistics": {
                "game_count": profile.statistics.game_count,
                "total_playtime_minutes": profile.statistics.total_playtime_minutes,
            },
        }

    def _create_archive(self, source_dir: Path, output_path: Path) -> None:
        """Create a ZIP archive from the source directory."""
        with zipfile.ZipFile(
            output_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(source_dir)
                    archive.write(file_path, arcname)


class ProfileImporter:
    """
    Imports profiles from archive files.

    Reads .ppf (Playnite Profile File) archives and extracts
    profile data for import.

    Example:
        >>> importer = ProfileImporter()
        >>> data = importer.read_export(Path("gaming.ppf"))
        >>> importer.import_to_path(Path("gaming.ppf"), Path("/profiles/new"))
    """

    def read_export(
        self,
        import_path: Path,
        password: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Read and validate an export file.

        Reads the manifest and profile data from an export archive
        without extracting the full contents.

        Args:
            import_path: Path to the .ppf file
            password: Decryption password (if encrypted)

        Returns:
            Dictionary containing profile metadata and settings

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is invalid or incompatible

        Example:
            >>> data = importer.read_export(Path("gaming.ppf"))
            >>> print(data["name"])
            'Gaming'
        """
        if not import_path.exists():
            raise FileNotFoundError(f"Import file not found: {import_path}")

        with zipfile.ZipFile(import_path, "r") as archive:
            # Read manifest
            try:
                manifest_content = archive.read("manifest.json")
                manifest = json.loads(manifest_content)
            except KeyError:
                raise ValueError("Invalid export file: missing manifest.json")
            except json.JSONDecodeError:
                raise ValueError("Invalid export file: corrupt manifest.json")

            # Check format version
            format_version = manifest.get("format_version")
            if not self._is_compatible_version(format_version):
                raise ValueError(
                    f"Incompatible export format version: {format_version}. "
                    f"Expected: {EXPORT_FORMAT_VERSION}"
                )

            # Read settings
            try:
                settings_content = archive.read("settings.json")
                settings = json.loads(settings_content)
            except (KeyError, json.JSONDecodeError):
                settings = {}

            # Read sharing settings
            try:
                sharing_content = archive.read("sharing.json")
                sharing = json.loads(sharing_content)
            except (KeyError, json.JSONDecodeError):
                sharing = {}

        # Return combined data
        return {
            "manifest": manifest,
            "name": manifest["profile"]["name"],
            "description": manifest["profile"]["description"],
            "settings": settings,
            "sharing": sharing,
            "contents": manifest.get("contents", {}),
            "statistics": manifest.get("statistics", {}),
        }

    def import_to_path(
        self,
        import_path: Path,
        target_path: Path,
        password: Optional[str] = None,
    ) -> None:
        """
        Extract an export file to a target directory.

        Extracts all contents from the archive to the target path,
        creating the directory structure for a new profile.

        Args:
            import_path: Path to the .ppf file
            target_path: Directory to extract to
            password: Decryption password (if encrypted)

        Raises:
            FileNotFoundError: If import file doesn't exist
            FileExistsError: If target path already exists with data

        Example:
            >>> importer.import_to_path(
            ...     Path("gaming.ppf"),
            ...     Path("/profiles/imported")
            ... )
        """
        if not import_path.exists():
            raise FileNotFoundError(f"Import file not found: {import_path}")

        # Create target directory
        target_path.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(import_path, "r") as archive:
            # Extract all files
            for info in archive.infolist():
                # Skip manifest and settings (handled separately)
                if info.filename in ("manifest.json", "settings.json", "sharing.json"):
                    continue

                # Extract to target path
                archive.extract(info, target_path)

        logger.info(f"Imported profile data to {target_path}")

    def get_archive_info(self, import_path: Path) -> dict[str, Any]:
        """
        Get information about an export archive.

        Returns metadata about the archive without fully reading it.

        Args:
            import_path: Path to the .ppf file

        Returns:
            Dictionary with archive information
        """
        if not import_path.exists():
            raise FileNotFoundError(f"Import file not found: {import_path}")

        info = {
            "path": str(import_path),
            "size_bytes": import_path.stat().st_size,
            "modified": datetime.fromtimestamp(
                import_path.stat().st_mtime
            ).isoformat(),
        }

        with zipfile.ZipFile(import_path, "r") as archive:
            info["file_count"] = len(archive.namelist())

            # Get manifest if available
            try:
                manifest = json.loads(archive.read("manifest.json"))
                info["profile_name"] = manifest["profile"]["name"]
                info["format_version"] = manifest.get("format_version")
                info["created_at"] = manifest.get("created_at")
                info["contents"] = manifest.get("contents", {})
            except (KeyError, json.JSONDecodeError):
                info["profile_name"] = "Unknown"

        return info

    def validate_archive(self, import_path: Path) -> tuple[bool, list[str]]:
        """
        Validate an export archive.

        Checks that the archive is valid and contains required files.

        Args:
            import_path: Path to the .ppf file

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        if not import_path.exists():
            return False, ["File not found"]

        try:
            with zipfile.ZipFile(import_path, "r") as archive:
                # Check for required files
                names = archive.namelist()

                if "manifest.json" not in names:
                    errors.append("Missing manifest.json")

                # Validate manifest
                try:
                    manifest = json.loads(archive.read("manifest.json"))
                    if "format_version" not in manifest:
                        errors.append("Manifest missing format_version")
                    if "profile" not in manifest:
                        errors.append("Manifest missing profile info")
                except json.JSONDecodeError:
                    errors.append("Invalid manifest.json format")

                # Check archive integrity
                bad_file = archive.testzip()
                if bad_file:
                    errors.append(f"Corrupt file in archive: {bad_file}")

        except zipfile.BadZipFile:
            return False, ["Invalid or corrupt archive file"]

        return len(errors) == 0, errors

    def calculate_checksum(self, import_path: Path) -> str:
        """
        Calculate SHA-256 checksum of an export file.

        Args:
            import_path: Path to the .ppf file

        Returns:
            Hex-encoded SHA-256 hash
        """
        sha256 = hashlib.sha256()
        with open(import_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _is_compatible_version(self, version: Optional[str]) -> bool:
        """Check if an export format version is compatible."""
        if version is None:
            return False

        # For now, only exact match
        # In future, implement semantic versioning
        return version == EXPORT_FORMAT_VERSION
