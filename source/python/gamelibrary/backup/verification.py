"""Backup integrity verification."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

HASH_ALGORITHM = "sha256"
CHUNK_SIZE = 8192


def compute_file_checksum(file_path: str | Path) -> str:
    """Compute SHA-256 checksum of a file."""
    h = hashlib.new(HASH_ALGORITHM)
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def compute_bytes_checksum(data: bytes) -> str:
    """Compute SHA-256 checksum of bytes."""
    return hashlib.new(HASH_ALGORITHM, data).hexdigest()


def verify_backup(backup_path: str | Path) -> dict:
    """Verify a backup file's integrity.

    Returns dict with verification result and details.
    """
    backup_path = Path(backup_path)
    result = {
        "path": str(backup_path),
        "valid": False,
        "errors": [],
        "warnings": [],
        "items_checked": 0,
    }

    if not backup_path.exists():
        result["errors"].append("Backup file does not exist")
        return result

    if not zipfile.is_zipfile(str(backup_path)):
        result["errors"].append("File is not a valid ZIP archive (may be encrypted)")
        return result

    try:
        with zipfile.ZipFile(str(backup_path), "r") as zf:
            bad_file = zf.testzip()
            if bad_file:
                result["errors"].append(f"Corrupt file in archive: {bad_file}")
                return result

            if "manifest.json" not in zf.namelist():
                result["warnings"].append("No manifest.json found in backup")
            else:
                manifest_data = json.loads(zf.read("manifest.json"))
                items = manifest_data.get("items", [])
                for item in items:
                    item_path = item.get("path", "")
                    expected_checksum = item.get("checksum", "")
                    if item_path in zf.namelist():
                        actual_data = zf.read(item_path)
                        actual_checksum = compute_bytes_checksum(actual_data)
                        if expected_checksum and actual_checksum != expected_checksum:
                            result["errors"].append(
                                f"Checksum mismatch for {item_path}: "
                                f"expected {expected_checksum[:12]}..., got {actual_checksum[:12]}..."
                            )
                        result["items_checked"] += 1
                    else:
                        result["errors"].append(f"Missing file in archive: {item_path}")

            if not result["errors"]:
                result["valid"] = True
    except zipfile.BadZipFile:
        result["errors"].append("Corrupt ZIP file")
    except Exception as e:
        result["errors"].append(f"Verification error: {e}")

    return result
