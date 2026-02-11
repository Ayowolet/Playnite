"""
Script marketplace / repository integration.

The marketplace fetches a JSON index from a configurable URL and allows users
to discover, install, and update community scripts.

Index format
------------
The remote JSON file must be a list of objects::

    [
        {
            "id": "jane.playtime-tracker",
            "name": "Playtime Tracker",
            "description": "Tracks detailed playtime statistics",
            "author": "Jane Doe",
            "version": "2.1.0",
            "download_url": "https://example.com/scripts/playtime_tracker.py",
            "config_url": "https://example.com/scripts/playtime_tracker.yaml",
            "homepage": "https://github.com/jane/playtime-tracker",
            "tags": ["statistics", "playtime"],
            "requires_packages": ["matplotlib"]
        },
        ...
    ]

All operations degrade gracefully when the network is unavailable or
``requests`` is not installed.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

# Default community marketplace index URL
DEFAULT_INDEX_URL = "https://raw.githubusercontent.com/playnite-python/marketplace/main/index.json"


class MarketplaceEntry:
    """A single script entry from the marketplace index."""

    def __init__(self, data: Dict[str, Any]) -> None:
        self.id: str = data.get("id", "")
        self.name: str = data.get("name", "")
        self.description: str = data.get("description", "")
        self.author: str = data.get("author", "")
        self.version: str = data.get("version", "0.0.0")
        self.download_url: str = data.get("download_url", "")
        self.config_url: str = data.get("config_url", "")
        self.homepage: str = data.get("homepage", "")
        self.tags: List[str] = data.get("tags", [])
        self.requires_packages: List[str] = data.get("requires_packages", [])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "version": self.version,
            "download_url": self.download_url,
            "config_url": self.config_url,
            "homepage": self.homepage,
            "tags": self.tags,
            "requires_packages": self.requires_packages,
        }

    def __repr__(self) -> str:
        return f"MarketplaceEntry({self.id!r}, v{self.version})"


class MarketplaceError(Exception):
    """Raised when a marketplace operation fails."""


class ScriptMarketplace:
    """
    Interface for the script community marketplace.

    Parameters
    ----------
    extensions_dir:
        Directory where scripts are installed.
    index_url:
        URL of the remote JSON index.
    cache_dir:
        Optional directory for caching the fetched index.
    """

    def __init__(
        self,
        extensions_dir: str,
        index_url: str = DEFAULT_INDEX_URL,
        cache_dir: Optional[str] = None,
    ) -> None:
        self._ext_dir = Path(extensions_dir)
        self._ext_dir.mkdir(parents=True, exist_ok=True)
        self._index_url = index_url
        self._cache_dir = Path(cache_dir) if cache_dir else self._ext_dir / ".marketplace_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._index: Optional[List[MarketplaceEntry]] = None

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def refresh_index(self, force: bool = False) -> List[MarketplaceEntry]:
        """
        Download (or load from cache) the marketplace index.

        Parameters
        ----------
        force:
            Bypass cache and always download fresh data.

        Returns
        -------
        list[MarketplaceEntry]
        """
        cache_file = self._cache_dir / "index.json"
        cache_age_seconds = self._file_age(cache_file)

        if not force and cache_file.exists() and cache_age_seconds < 3600:
            with cache_file.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = self._fetch_json(self._index_url)
            with cache_file.open("w", encoding="utf-8") as fh:
                json.dump(data, fh)

        self._index = [MarketplaceEntry(d) for d in data]
        return self._index

    def list_available(self) -> List[MarketplaceEntry]:
        """Return the cached index (refreshing if not yet loaded)."""
        if self._index is None:
            self.refresh_index()
        return self._index or []

    def search(self, query: str) -> List[MarketplaceEntry]:
        """Case-insensitive search across name, description, and tags."""
        q = query.lower()
        return [
            e for e in self.list_available()
            if q in e.name.lower()
            or q in e.description.lower()
            or any(q in t.lower() for t in e.tags)
        ]

    def get_entry(self, script_id: str) -> Optional[MarketplaceEntry]:
        for e in self.list_available():
            if e.id == script_id:
                return e
        return None

    # ------------------------------------------------------------------
    # Install / update
    # ------------------------------------------------------------------

    def install(self, script_id: str, overwrite: bool = False) -> Path:
        """
        Download and install *script_id*.

        Returns the path to the installed script file.

        Raises
        ------
        MarketplaceError
            If the script is not found in the index or download fails.
        """
        entry = self.get_entry(script_id)
        if not entry:
            raise MarketplaceError(f"Script '{script_id}' not found in marketplace.")

        if not entry.download_url:
            raise MarketplaceError(f"Script '{script_id}' has no download URL.")

        dest_script = self._ext_dir / f"{script_id}.py"
        dest_config = self._ext_dir / f"{script_id}.yaml"

        if dest_script.exists() and not overwrite:
            raise MarketplaceError(
                f"Script '{script_id}' is already installed. "
                "Pass overwrite=True to reinstall."
            )

        # Download to temp then move atomically
        script_content = self._fetch_text(entry.download_url)
        self._atomic_write(dest_script, script_content)

        if entry.config_url:
            try:
                config_content = self._fetch_text(entry.config_url)
                self._atomic_write(dest_config, config_content)
            except MarketplaceError:
                pass  # Config is optional

        return dest_script

    def update(self, script_id: str) -> bool:
        """
        Check for and apply an update for *script_id*.

        Returns *True* if an update was applied.
        """
        entry = self.get_entry(script_id)
        if not entry:
            return False

        installed_version = self._get_installed_version(script_id)
        if installed_version and installed_version >= entry.version:
            return False

        self.install(script_id, overwrite=True)
        return True

    def check_updates(self) -> List[Dict[str, str]]:
        """Return list of ``{id, installed, available}`` for scripts with updates."""
        updates = []
        for entry in self.list_available():
            dest = self._ext_dir / f"{entry.id}.py"
            if not dest.exists():
                continue
            installed = self._get_installed_version(entry.id)
            if installed and installed < entry.version:
                updates.append(
                    {
                        "id": entry.id,
                        "name": entry.name,
                        "installed": installed,
                        "available": entry.version,
                    }
                )
        return updates

    def uninstall(self, script_id: str) -> bool:
        """Remove an installed script and its config. Returns *True* if found."""
        removed = False
        for suffix in (".py", ".yaml"):
            p = self._ext_dir / f"{script_id}{suffix}"
            if p.exists():
                p.unlink()
                removed = True
        return removed

    # ------------------------------------------------------------------
    # Installed scripts inventory
    # ------------------------------------------------------------------

    def list_installed(self) -> List[Dict[str, str]]:
        """List scripts installed from the marketplace."""
        installed = []
        for py_file in sorted(self._ext_dir.glob("*.py")):
            meta_file = self._ext_dir / (py_file.stem + "_meta.json")
            version = "unknown"
            if meta_file.exists():
                with meta_file.open() as fh:
                    meta = json.load(fh)
                version = meta.get("version", version)
            installed.append({"id": py_file.stem, "version": version, "path": str(py_file)})
        return installed

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fetch_json(self, url: str) -> Any:
        text = self._fetch_text(url)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise MarketplaceError(f"Invalid JSON from {url}: {exc}") from exc

    def _fetch_text(self, url: str) -> str:
        if not _REQUESTS_AVAILABLE:
            raise MarketplaceError(
                "The 'requests' package is required for marketplace operations. "
                "Install it with: pip install requests"
            )
        try:
            resp = _requests.get(url, timeout=15)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            raise MarketplaceError(f"Download failed for {url}: {exc}") from exc

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=path.parent, prefix=path.stem + "_", suffix=".tmp"
        )
        try:
            with open(tmp_fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            shutil.move(tmp_path, str(path))
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    @staticmethod
    def _file_age(path: Path) -> float:
        """Return file age in seconds, or infinity if not found."""
        if not path.exists():
            return float("inf")
        mtime = path.stat().st_mtime
        return (datetime.now().timestamp() - mtime)

    def _get_installed_version(self, script_id: str) -> Optional[str]:
        meta_file = self._ext_dir / f"{script_id}_meta.json"
        if meta_file.exists():
            with meta_file.open() as fh:
                return json.load(fh).get("version")
        # Try to extract from marketplace entry
        entry = self.get_entry(script_id)
        return entry.version if entry else None
