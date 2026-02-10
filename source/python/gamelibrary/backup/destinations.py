"""Backup destination management - local, external, network, and cloud."""

from __future__ import annotations

import json
import logging
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from ..database import Database

logger = logging.getLogger(__name__)


class CloudProvider(ABC):
    """Abstract interface for cloud storage providers."""

    @abstractmethod
    def upload(self, local_path: str | Path, remote_name: str) -> dict:
        """Upload a file to cloud storage. Returns result dict."""

    @abstractmethod
    def download(self, remote_name: str, local_path: str | Path) -> dict:
        """Download a file from cloud storage. Returns result dict."""

    @abstractmethod
    def validate_config(self) -> bool:
        """Validate the provider configuration/credentials."""


class SimulatedCloudProvider(CloudProvider):
    """Cloud provider that copies to a local directory to simulate uploads.

    Used for testing and as a reference implementation. Real providers
    (Google Drive, Dropbox, OneDrive) would subclass CloudProvider directly.
    """

    def __init__(self, config: dict):
        self.simulate_dir = Path(config.get("simulate_dir", "/tmp/cloud_sim"))
        self.provider_name = config.get("provider", "simulated")

    def upload(self, local_path: str | Path, remote_name: str) -> dict:
        local_path = Path(local_path)
        if not local_path.exists():
            return {"status": "failed", "error": f"Source file not found: {local_path}"}
        self.simulate_dir.mkdir(parents=True, exist_ok=True)
        dest = self.simulate_dir / remote_name
        shutil.copy2(str(local_path), str(dest))
        return {
            "status": "completed",
            "provider": self.provider_name,
            "remote_name": remote_name,
            "size": dest.stat().st_size,
            "path": str(dest),
        }

    def download(self, remote_name: str, local_path: str | Path) -> dict:
        source = self.simulate_dir / remote_name
        if not source.exists():
            return {"status": "failed", "error": f"Remote file not found: {remote_name}"}
        shutil.copy2(str(source), str(local_path))
        return {"status": "completed", "path": str(local_path)}

    def validate_config(self) -> bool:
        return True


CLOUD_PROVIDERS: dict[str, type[CloudProvider]] = {
    "simulated": SimulatedCloudProvider,
}


def get_cloud_provider(config: dict) -> CloudProvider:
    """Instantiate a cloud provider from config."""
    provider_name = config.get("provider", "")
    cls = CLOUD_PROVIDERS.get(provider_name)
    if not cls:
        raise ValueError(
            f"Unknown cloud provider: {provider_name}. "
            f"Available: {', '.join(CLOUD_PROVIDERS.keys())}"
        )
    return cls(config)


class DestinationManager:
    """Manages backup destinations and distributes backups to them."""

    def __init__(self, db: Database):
        self.db = db

    def register_destination(
        self, name: str, dest_type: str, config: dict
    ) -> int:
        """Register a backup destination.

        dest_type: 'local' for filesystem paths (local folder, external drive,
                   network share) or 'cloud' for cloud storage.
        config: For local: {"path": "/some/dir"}
                For cloud: {"provider": "gdrive", ...}
        """
        if dest_type not in ("local", "cloud"):
            raise ValueError(f"Invalid destination type: {dest_type}. Must be 'local' or 'cloud'.")

        if dest_type == "local":
            path = config.get("path")
            if not path:
                raise ValueError("Local destination requires 'path' in config.")
            Path(path).mkdir(parents=True, exist_ok=True)

        if dest_type == "cloud":
            provider = config.get("provider")
            if not provider:
                raise ValueError("Cloud destination requires 'provider' in config.")

        existing = self.db.execute(
            "SELECT id FROM backup_destinations WHERE name = ?", (name,)
        )
        if existing:
            self.db.execute(
                "UPDATE backup_destinations SET dest_type = ?, config = ? WHERE name = ?",
                (dest_type, json.dumps(config), name),
            )
            return existing[0]["id"]

        return self.db.execute_insert(
            "INSERT INTO backup_destinations (name, dest_type, config) VALUES (?, ?, ?)",
            (name, dest_type, json.dumps(config)),
        )

    def get_destination(self, name: str) -> dict | None:
        rows = self.db.execute(
            "SELECT * FROM backup_destinations WHERE name = ?", (name,)
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "id": r["id"],
            "name": r["name"],
            "dest_type": r["dest_type"],
            "config": json.loads(r["config"]) if r["config"] else {},
            "enabled": bool(r["enabled"]),
        }

    def list_destinations(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM backup_destinations WHERE enabled = 1 ORDER BY name"
        )
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "dest_type": r["dest_type"],
                "config": json.loads(r["config"]) if r["config"] else {},
                "enabled": bool(r["enabled"]),
            }
            for r in rows
        ]

    def remove_destination(self, name: str):
        self.db.execute(
            "DELETE FROM backup_destinations WHERE name = ?", (name,)
        )

    def distribute(
        self,
        source_path: str | Path,
        destination_names: list[str] | None = None,
    ) -> list[dict]:
        """Distribute a backup file to one or more destinations.

        If destination_names is None, distributes to all enabled destinations.
        Returns a list of per-destination result dicts.
        """
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Backup file not found: {source_path}")

        if destination_names:
            destinations = []
            for name in destination_names:
                dest = self.get_destination(name)
                if dest:
                    destinations.append(dest)
                else:
                    logger.warning("Destination '%s' not found, skipping", name)
        else:
            destinations = self.list_destinations()

        results = []
        for dest in destinations:
            result = self._distribute_to_one(source_path, dest)
            results.append(result)
        return results

    def _distribute_to_one(self, source_path: Path, dest: dict) -> dict:
        """Copy/upload the backup file to a single destination."""
        name = dest["name"]
        dest_type = dest["dest_type"]
        config = dest["config"]

        try:
            if dest_type == "local":
                return self._distribute_local(source_path, name, config)
            elif dest_type == "cloud":
                return self._distribute_cloud(source_path, name, config)
            else:
                return {
                    "destination": name,
                    "type": dest_type,
                    "status": "failed",
                    "error": f"Unknown destination type: {dest_type}",
                }
        except Exception as e:
            logger.error("Failed to distribute to %s: %s", name, e)
            return {
                "destination": name,
                "type": dest_type,
                "status": "failed",
                "error": str(e),
            }

    def _distribute_local(
        self, source_path: Path, name: str, config: dict
    ) -> dict:
        dest_dir = Path(config["path"])
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / source_path.name
        shutil.copy2(str(source_path), str(dest_file))
        return {
            "destination": name,
            "type": "local",
            "status": "completed",
            "path": str(dest_file),
            "size": dest_file.stat().st_size,
        }

    def _distribute_cloud(
        self, source_path: Path, name: str, config: dict
    ) -> dict:
        provider = get_cloud_provider(config)
        result = provider.upload(source_path, source_path.name)
        result["destination"] = name
        result["type"] = "cloud"
        return result
