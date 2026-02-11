"""Script marketplace/repository integration for discovering and installing community scripts."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen, Request
from urllib.error import URLError

from playnite_py.scripting.config import ScriptConfig

logger = logging.getLogger(__name__)


def _validate_url(url: str) -> None:
    """Reject non-HTTPS URLs unless targeting localhost (for development)."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    host = parsed.hostname or ""
    if scheme == "https":
        return
    if scheme == "http" and host in ("localhost", "127.0.0.1", "::1"):
        return
    raise ValueError(
        f"Insecure URL scheme '{scheme}://' is not allowed. "
        f"Use HTTPS (HTTP is only permitted for localhost)."
    )


@dataclass
class MarketplaceEntry:
    """A script available in the marketplace."""
    id: str = ""
    name: str = ""
    description: str = ""
    author: str = ""
    version: str = "1.0.0"
    download_url: str = ""
    repository_url: str = ""
    tags: list[str] = field(default_factory=list)
    downloads: int = 0
    rating: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "version": self.version,
            "download_url": self.download_url,
            "repository_url": self.repository_url,
            "tags": self.tags,
            "downloads": self.downloads,
            "rating": self.rating,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarketplaceEntry:
        """Deserialize from a dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ScriptMarketplace:
    """Interface for browsing and installing scripts from a repository.

    The marketplace uses a simple JSON-based repository index that can be
    hosted on any static file server or GitHub repository.
    """

    DEFAULT_REPO_URL = ""  # No default; must be configured

    # Default TTL for cached index: 1 hour
    INDEX_TTL_SECONDS = 3600

    # File patterns not allowed inside extension packages
    _BLOCKED_EXTENSIONS = {".dll", ".exe", ".sln"}

    def __init__(
        self,
        extensions_dir: str,
        cache_dir: str | None = None,
        repo_url: str = "",
        index_ttl: int | None = None,
    ):
        self._extensions_dir = Path(extensions_dir)
        self._cache_dir = Path(cache_dir) if cache_dir else self._extensions_dir / ".cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._repo_url = repo_url or self.DEFAULT_REPO_URL
        self._index: list[MarketplaceEntry] = []
        self._index_path = self._cache_dir / "marketplace_index.json"
        self._index_fetched_at: float = 0.0
        self._index_ttl = index_ttl if index_ttl is not None else self.INDEX_TTL_SECONDS
        # License agreement tracking
        self._license_path = self._cache_dir / "license_agreements.json"
        self._license_agreements: dict[str, str] = {}
        if self._license_path.exists():
            try:
                with open(self._license_path, "r", encoding="utf-8") as f:
                    self._license_agreements = json.load(f)
            except Exception:
                self._license_agreements = {}
        # Installation queue for deferred installs
        self._install_queue_path = self._cache_dir / "install_queue.json"
        self._install_queue: list[dict[str, str]] = []
        if self._install_queue_path.exists():
            try:
                with open(self._install_queue_path, "r", encoding="utf-8") as f:
                    self._install_queue = json.load(f)
            except Exception:
                self._install_queue = []

        # Load cached index
        if self._index_path.exists():
            self._load_cached_index()

    def set_repository_url(self, url: str) -> None:
        """Set or clear the marketplace repository URL."""
        if url:  # allow clearing to empty
            _validate_url(url)
        self._repo_url = url

    def refresh_index(self) -> dict[str, Any]:
        """Fetch the latest marketplace index from the repository."""
        if not self._repo_url:
            return {"success": False, "error": "No repository URL configured", "count": 0}

        try:
            _validate_url(self._repo_url)
            index_url = self._repo_url.rstrip("/") + "/index.json"
            req = Request(index_url, headers={"User-Agent": "PlaynitePy/0.1"})
            with urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))

            self._index = [MarketplaceEntry.from_dict(entry) for entry in data.get("scripts", [])]
            self._index_fetched_at = time.monotonic()
            self._save_cached_index()
            return {"success": True, "count": len(self._index), "error": ""}

        except URLError as e:
            return {"success": False, "error": f"Network error: {e}", "count": 0}
        except Exception as e:
            return {"success": False, "error": str(e), "count": 0}

    def is_index_stale(self) -> bool:
        """Return True if the cached index has exceeded its TTL."""
        if self._index_fetched_at == 0.0:
            return True
        return (time.monotonic() - self._index_fetched_at) > self._index_ttl

    def invalidate_index(self) -> None:
        """Clear the in-memory cached index."""
        self._index.clear()
        self._index_fetched_at = 0.0

    def search(
        self,
        query: str = "",
        tags: list[str] | None = None,
        author: str = "",
    ) -> list[dict[str, Any]]:
        """Search marketplace entries by name/description, tags, or author."""
        results = list(self._index)

        if query:
            q = query.lower()
            results = [
                e for e in results
                if q in e.name.lower() or q in e.description.lower()
            ]

        if tags:
            tag_set = set(t.lower() for t in tags)
            results = [
                e for e in results
                if tag_set.intersection(t.lower() for t in e.tags)
            ]

        if author:
            a = author.lower()
            results = [e for e in results if a in e.author.lower()]

        return [e.to_dict() for e in results]

    def get_entry(self, script_id: str) -> dict[str, Any] | None:
        """Return a single marketplace entry by script ID, or None."""
        for entry in self._index:
            if entry.id == script_id:
                return entry.to_dict()
        return None

    # ------------------------------------------------------------------
    # Package verification
    # ------------------------------------------------------------------

    @classmethod
    def verify_package(cls, archive_path: str | Path) -> dict[str, Any]:
        """Verify an extension package before installation.

        Checks:
        * File is a valid ZIP
        * Contains a config.yaml manifest
        * Manifest has a valid version string
        * No blocked file types (.dll, .exe, .sln)

        Returns ``{"valid": True}`` or ``{"valid": False, "errors": [...]}``.
        """
        archive_path = Path(archive_path)
        errors: list[str] = []

        if not zipfile.is_zipfile(str(archive_path)):
            return {"valid": False, "errors": ["File is not a valid ZIP archive"]}

        with zipfile.ZipFile(str(archive_path)) as zf:
            names = zf.namelist()

            # Check for manifest
            has_manifest = any(
                n.endswith("config.yaml") or n.endswith("config.yml")
                for n in names
            )
            if not has_manifest:
                errors.append("Package does not contain a config.yaml manifest")

            # Check for blocked file types
            for name in names:
                ext = Path(name).suffix.lower()
                if ext in cls._BLOCKED_EXTENSIONS:
                    errors.append(f"Package contains blocked file type: {name}")

            # Validate manifest if present
            if has_manifest:
                manifest_name = next(
                    n for n in names
                    if n.endswith("config.yaml") or n.endswith("config.yml")
                )
                try:
                    import yaml
                    with zf.open(manifest_name) as mf:
                        data = yaml.safe_load(mf.read().decode("utf-8")) or {}
                    config = ScriptConfig._from_raw(data)
                    validation_errors = config.validate()
                    errors.extend(validation_errors)
                except Exception as e:
                    errors.append(f"Failed to parse manifest: {e}")

        return {"valid": len(errors) == 0, "errors": errors}

    # ------------------------------------------------------------------
    # License agreement tracking
    # ------------------------------------------------------------------

    def agree_license(self, addon_id: str) -> None:
        """Record that the user has agreed to an addon's license."""
        from datetime import datetime, timezone
        self._license_agreements[addon_id] = datetime.now(timezone.utc).isoformat()
        self._save_license_agreements()

    def has_agreed_license(self, addon_id: str) -> bool:
        """Check whether the user has previously agreed to an addon's license."""
        return addon_id in self._license_agreements

    def _save_license_agreements(self) -> None:
        with open(self._license_path, "w", encoding="utf-8") as f:
            json.dump(self._license_agreements, f, indent=2)

    # ------------------------------------------------------------------
    # Installation queue
    # ------------------------------------------------------------------

    def queue_install(self, script_id: str) -> None:
        """Queue a script for installation on next startup."""
        for item in self._install_queue:
            if item.get("id") == script_id and item.get("action") == "install":
                return  # already queued
        self._install_queue.append({"id": script_id, "action": "install"})
        self._save_install_queue()

    def queue_uninstall(self, script_id: str) -> None:
        """Queue a script for uninstallation on next startup."""
        for item in self._install_queue:
            if item.get("id") == script_id and item.get("action") == "uninstall":
                return
        self._install_queue.append({"id": script_id, "action": "uninstall"})
        self._save_install_queue()

    def get_queued_items(self) -> list[dict[str, str]]:
        """Return all pending install and uninstall queue entries."""
        return list(self._install_queue)

    def process_install_queue(self) -> list[dict[str, Any]]:
        """Process all queued install/uninstall operations. Returns results."""
        results: list[dict[str, Any]] = []
        for item in list(self._install_queue):
            if item["action"] == "install":
                result = self.install_script(item["id"])
                results.append(result)
            elif item["action"] == "uninstall":
                result = self.uninstall_extension(item["id"])
                results.append(result)
        self._install_queue.clear()
        self._save_install_queue()
        return results

    def _save_install_queue(self) -> None:
        with open(self._install_queue_path, "w", encoding="utf-8") as f:
            json.dump(self._install_queue, f, indent=2)

    def uninstall_extension(self, script_id: str) -> dict[str, Any]:
        """Remove an installed extension by ID."""
        target_dir = self._extensions_dir / script_id
        if not target_dir.exists():
            return {"success": False, "error": f"Extension '{script_id}' not found"}
        try:
            shutil.rmtree(str(target_dir))
            return {"success": True, "id": script_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def install_script(self, script_id: str) -> dict[str, Any]:
        """Download and install a script from the marketplace."""
        entry = None
        for e in self._index:
            if e.id == script_id:
                entry = e
                break

        if not entry:
            return {"success": False, "error": f"Script '{script_id}' not found in marketplace"}

        if not entry.download_url:
            return {"success": False, "error": "No download URL for this script"}

        try:
            _validate_url(entry.download_url)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        target_dir = self._extensions_dir / script_id

        try:
            # Download to temp directory
            with tempfile.TemporaryDirectory() as tmp:
                archive_path = Path(tmp) / "script.zip"
                req = Request(entry.download_url, headers={"User-Agent": "PlaynitePy/0.1"})
                with urlopen(req, timeout=60) as response:
                    archive_path.write_bytes(response.read())

                # Verify package before installing
                verification = self.verify_package(archive_path)
                if not verification["valid"]:
                    return {
                        "success": False,
                        "error": "Package verification failed: "
                        + "; ".join(verification["errors"]),
                    }

                with zipfile.ZipFile(str(archive_path)) as zf:
                    extract_dir = Path(tmp) / "extracted"
                    zf.extractall(str(extract_dir))

                    # Find the script directory (may be nested)
                    contents = list(extract_dir.iterdir())
                    if len(contents) == 1 and contents[0].is_dir():
                        src = contents[0]
                    else:
                        src = extract_dir

                    # Remove old version if updating
                    if target_dir.exists():
                        shutil.rmtree(str(target_dir))
                    shutil.copytree(str(src), str(target_dir))

            return {
                "success": True,
                "path": str(target_dir),
                "name": entry.name,
                "version": entry.version,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_updates(self, installed_scripts: dict[str, str]) -> list[dict[str, Any]]:
        """Check for available updates. installed_scripts maps script_id -> version."""
        updates = []
        for entry in self._index:
            if entry.id in installed_scripts:
                installed_ver = installed_scripts[entry.id]
                if self._version_newer(entry.version, installed_ver):
                    updates.append({
                        "id": entry.id,
                        "name": entry.name,
                        "installed_version": installed_ver,
                        "available_version": entry.version,
                    })
        return updates

    def _version_newer(self, available: str, installed: str) -> bool:
        """Simple version comparison (major.minor.patch)."""
        try:
            av = tuple(int(x) for x in available.split("."))
            iv = tuple(int(x) for x in installed.split("."))
            return av > iv
        except (ValueError, AttributeError):
            return available != installed

    def _save_cached_index(self) -> None:
        data = {"scripts": [e.to_dict() for e in self._index]}
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load_cached_index(self) -> None:
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._index = [
                MarketplaceEntry.from_dict(e) for e in data.get("scripts", [])
            ]
        except Exception:
            self._index = []
