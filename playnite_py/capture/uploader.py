"""
Media uploader — upload screenshots and video clips to cloud storage
or sharing platforms, and generate shareable links.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests as _requests_lib
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


@dataclass
class UploadResult:
    """Result of an upload operation."""
    id: str
    local_path: str
    destination: str        # URL or target path
    upload_type: str        # "local_copy" | "http" | "simulated"
    success: bool
    error_message: Optional[str] = None
    bytes_transferred: int = 0
    uploaded_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "local_path": self.local_path,
            "destination": self.destination,
            "upload_type": self.upload_type,
            "success": self.success,
            "error_message": self.error_message,
            "bytes_transferred": self.bytes_transferred,
            "uploaded_at": self.uploaded_at,
        }


class MediaUploader:
    """
    Uploads captured media files to various destinations.

    Supported backends:
    - local_copy  — copies files to another local directory (always available)
    - http        — HTTP POST multipart upload to a configured URL
    - simulated   — returns fake success for testing

    Configuration
    -------------
    Pass ``upload_config`` dict with keys:
        type:     "local_copy" | "http" | "simulated"
        dest_dir: (local_copy) target directory
        url:      (http) endpoint URL
        headers:  (http) additional headers dict
        api_key:  (http) Authorization header value (Bearer token)
        max_size_mb: maximum file size to upload (default 500 MB)
    """

    DEFAULT_MAX_MB = 500.0

    def __init__(self, upload_config: Optional[Dict[str, Any]] = None) -> None:
        self.config = upload_config or {"type": "simulated"}

    # ------------------------------------------------------------------ #
    # Core upload                                                          #
    # ------------------------------------------------------------------ #

    def upload(
        self,
        file_path: Path,
        game_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> UploadResult:
        """
        Upload a single file.  Auto-detects capture type from extension.
        """
        upload_id = str(uuid.uuid4())
        upload_type = self.config.get("type", "simulated")
        max_bytes = self.config.get("max_size_mb", self.DEFAULT_MAX_MB) * 1024 * 1024

        if file_path.exists() and file_path.stat().st_size > max_bytes:
            return UploadResult(
                id=upload_id,
                local_path=str(file_path),
                destination="",
                upload_type=upload_type,
                success=False,
                error_message=f"File exceeds maximum upload size ({max_bytes / 1024 / 1024:.0f} MB)",
            )

        if upload_type == "local_copy":
            return self._upload_local_copy(upload_id, file_path, game_name, tags)
        elif upload_type == "http":
            return self._upload_http(upload_id, file_path, game_name, tags)
        else:
            return self._upload_simulated(upload_id, file_path)

    def upload_batch(
        self, file_paths: List[Path], game_name: Optional[str] = None
    ) -> List[UploadResult]:
        return [self.upload(f, game_name=game_name) for f in file_paths]

    # ------------------------------------------------------------------ #
    # Backends                                                             #
    # ------------------------------------------------------------------ #

    def _upload_local_copy(
        self,
        upload_id: str,
        file_path: Path,
        game_name: Optional[str],
        tags: Optional[List[str]],
    ) -> UploadResult:
        dest_dir = Path(self.config.get("dest_dir", str(Path.home() / "PlayniteUploads")))
        if game_name:
            dest_dir = dest_dir / game_name.replace(" ", "_")
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest = dest_dir / file_path.name
        try:
            if file_path.exists():
                shutil.copy2(str(file_path), str(dest))
                bytes_transferred = dest.stat().st_size
            else:
                bytes_transferred = 0

            # Write minimal manifest
            manifest = dest_dir / "manifest.json"
            entries: List[Dict] = []
            if manifest.exists():
                try:
                    entries = json.loads(manifest.read_text(encoding="utf-8"))
                except Exception:
                    entries = []
            entries.append({
                "id": upload_id,
                "file": file_path.name,
                "game_name": game_name,
                "tags": tags or [],
                "uploaded_at": datetime.utcnow().isoformat(),
            })
            manifest.write_text(json.dumps(entries, indent=2), encoding="utf-8")

            return UploadResult(
                id=upload_id,
                local_path=str(file_path),
                destination=str(dest),
                upload_type="local_copy",
                success=True,
                bytes_transferred=bytes_transferred,
                uploaded_at=datetime.utcnow().isoformat(),
            )
        except Exception as exc:
            return UploadResult(
                id=upload_id,
                local_path=str(file_path),
                destination=str(dest),
                upload_type="local_copy",
                success=False,
                error_message=str(exc),
            )

    def _upload_http(
        self,
        upload_id: str,
        file_path: Path,
        game_name: Optional[str],
        tags: Optional[List[str]],
    ) -> UploadResult:
        if not _REQUESTS_AVAILABLE:
            return UploadResult(
                id=upload_id,
                local_path=str(file_path),
                destination=self.config.get("url", ""),
                upload_type="http",
                success=False,
                error_message="requests library not installed. pip install requests",
            )

        url = self.config.get("url", "")
        headers: Dict[str, str] = dict(self.config.get("headers", {}))
        api_key = self.config.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            with open(str(file_path), "rb") as fh:
                files = {"file": (file_path.name, fh, "application/octet-stream")}
                data = {
                    "upload_id": upload_id,
                    "game_name": game_name or "",
                    "tags": json.dumps(tags or []),
                }
                response = _requests_lib.post(
                    url, files=files, data=data, headers=headers, timeout=120
                )
                response.raise_for_status()
                resp_data = response.json() if response.content else {}
                share_url = resp_data.get("url", url)

            return UploadResult(
                id=upload_id,
                local_path=str(file_path),
                destination=share_url,
                upload_type="http",
                success=True,
                bytes_transferred=file_path.stat().st_size if file_path.exists() else 0,
                uploaded_at=datetime.utcnow().isoformat(),
            )
        except Exception as exc:
            return UploadResult(
                id=upload_id,
                local_path=str(file_path),
                destination=url,
                upload_type="http",
                success=False,
                error_message=str(exc),
            )

    def _upload_simulated(self, upload_id: str, file_path: Path) -> UploadResult:
        return UploadResult(
            id=upload_id,
            local_path=str(file_path),
            destination=f"simulated://uploads/{file_path.name}",
            upload_type="simulated",
            success=True,
            bytes_transferred=file_path.stat().st_size if file_path.exists() else 0,
            uploaded_at=datetime.utcnow().isoformat(),
        )

    # ------------------------------------------------------------------ #
    # Gallery sharing                                                      #
    # ------------------------------------------------------------------ #

    def share_gallery(
        self,
        game_name: str,
        screenshots: List[Path],
        output_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Upload a batch of screenshots and return a summary with destinations.
        """
        results = self.upload_batch(screenshots, game_name=game_name)
        success_count = sum(1 for r in results if r.success)
        return {
            "game_name": game_name,
            "total": len(results),
            "success": success_count,
            "failed": len(results) - success_count,
            "uploads": [r.to_dict() for r in results],
        }

    def get_upload_status(self, upload_id: str) -> Dict[str, Any]:
        """
        Check upload status.  For HTTP uploads, status is synchronous
        so this just returns a placeholder.
        """
        return {"upload_id": upload_id, "status": "completed"}
