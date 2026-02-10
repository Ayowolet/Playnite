"""
Media organiser — manages the directory structure for captured screenshots
and video clips, applies metadata tags, and implements storage policies.

Directory structure
-------------------
{captures_dir}/
    {game_name}/
        screenshots/
            YYYY-MM-DD/
                {timestamp}_{id}.png
                {timestamp}_{id}.json  ← sidecar
        videos/
            YYYY-MM-DD/
                {timestamp}_{id}.mp4
                {timestamp}_{id}.json  ← sidecar
        replays/
            YYYY-MM-DD/
                replay_{timestamp}.mp4
"""

from __future__ import annotations

import html
import json
import logging
import re
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def _assert_source_safe(source: Path, extra_roots: tuple = ()) -> None:
    """Raise ValueError if *source* resolves outside all allowed roots."""
    resolved = source.resolve()
    # Allow the file's own parent directory as a valid root
    allowed = list(extra_roots) + [source.parent.resolve()]
    for root in allowed:
        try:
            resolved.relative_to(root.resolve())
            return  # Safe — within an allowed root
        except ValueError:
            pass
    raise ValueError(
        f"Source path {source!r} resolves outside allowed directories"
    )


def _safe_dirname(name: str) -> str:
    """Convert a game name to a safe directory name, blocking path traversal."""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    safe = re.sub(r"\s+", "_", safe.strip())
    # Remove any remaining dots-only segments to prevent path traversal (e.g. "..")
    safe = re.sub(r"\.+", "", safe)
    return safe[:100] or "UnknownGame"


class MediaOrganizer:
    """
    Manages the organised hierarchy of captured media files.
    """

    CAPTURE_TYPES = ("screenshots", "videos", "replays")

    def __init__(self, captures_root: Optional[Path] = None) -> None:
        self.root = captures_root or Path.home() / "Videos" / "PlayniteCaptures"
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Directory helpers                                                    #
    # ------------------------------------------------------------------ #

    def get_game_dir(self, game_name: str) -> Path:
        return self.root / _safe_dirname(game_name)

    def get_capture_dir(self, game_name: str, capture_type: str) -> Path:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        d = self.get_game_dir(game_name) / capture_type / today
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------ #
    # Organise captured files                                              #
    # ------------------------------------------------------------------ #

    def organise_screenshot(
        self,
        source: Path,
        game_name: str,
        game_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Path:
        """
        Move/copy a screenshot into the organised library directory.
        Returns the new path.
        """
        _assert_source_safe(source, extra_roots=(self.root,))
        dest_dir = self.get_capture_dir(game_name, "screenshots")
        ts = datetime.utcnow().strftime("%H%M%S")
        new_name = f"{ts}_{source.name}"
        dest = dest_dir / new_name

        if source.exists():
            shutil.move(str(source), str(dest))

        # Move sidecar if it exists
        sidecar_src = source.with_suffix(".json")
        if sidecar_src.exists():
            shutil.move(str(sidecar_src), str(dest.with_suffix(".json")))
        else:
            self._write_sidecar(dest, "screenshot", game_name, game_id, tags)

        return dest

    def organise_video(
        self,
        source: Path,
        game_name: str,
        game_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Path:
        _assert_source_safe(source, extra_roots=(self.root,))
        dest_dir = self.get_capture_dir(game_name, "videos")
        ts = datetime.utcnow().strftime("%H%M%S")
        new_name = f"{ts}_{source.name}"
        dest = dest_dir / new_name

        if source.exists():
            shutil.move(str(source), str(dest))

        sidecar_src = source.with_suffix(".json")
        if sidecar_src.exists():
            shutil.move(str(sidecar_src), str(dest.with_suffix(".json")))
        else:
            self._write_sidecar(dest, "video", game_name, game_id, tags)

        return dest

    def organise_replay(
        self,
        source: Path,
        game_name: str,
        game_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Path:
        _assert_source_safe(source, extra_roots=(self.root,))
        dest_dir = self.get_capture_dir(game_name, "replays")
        ts = datetime.utcnow().strftime("%H%M%S")
        new_name = f"{ts}_{source.name}"
        dest = dest_dir / new_name

        if source.exists():
            shutil.move(str(source), str(dest))

        sidecar_src = source.with_suffix(".json")
        if sidecar_src.exists():
            shutil.move(str(sidecar_src), str(dest.with_suffix(".json")))
        else:
            self._write_sidecar(dest, "replay", game_name, game_id, tags)

        return dest

    # ------------------------------------------------------------------ #
    # Listing                                                              #
    # ------------------------------------------------------------------ #

    def list_captures(
        self,
        game_name: Optional[str] = None,
        capture_type: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        tag_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return a list of all captured media files with metadata.

        Parameters
        ----------
        since:
            Exclude captures with a capture time before this datetime.
        until:
            Exclude captures with a capture time after this datetime.
        tag_filter:
            Only include captures whose tag list contains this string.
        """
        results = []

        if game_name:
            game_dirs = [self.get_game_dir(game_name)]
        else:
            game_dirs = [d for d in self.root.iterdir() if d.is_dir() and not d.name.startswith(".")]

        for game_dir in game_dirs:
            types = [capture_type] if capture_type else list(self.CAPTURE_TYPES)
            for ctype in types:
                type_dir = game_dir / ctype
                if not type_dir.exists():
                    continue
                for date_dir in sorted(type_dir.iterdir()):
                    if not date_dir.is_dir():
                        continue
                    for file in sorted(date_dir.iterdir()):
                        if file.suffix in (".json",):
                            continue
                        if not file.is_file():
                            continue

                        # Load sidecar first so we can use captured_at for date filtering
                        sidecar = file.with_suffix(".json")
                        meta: Dict[str, Any] = {}
                        if sidecar.exists():
                            try:
                                meta = json.loads(sidecar.read_text(encoding="utf-8"))
                            except Exception:
                                log.warning("Failed to parse sidecar %s", sidecar, exc_info=True)

                        # Determine capture time (prefer sidecar timestamp, fall back to mtime)
                        cap_ts = meta.get("captured_at") or meta.get("started_at")
                        if cap_ts:
                            try:
                                cap_time = datetime.fromisoformat(cap_ts)
                            except ValueError:
                                cap_time = datetime.utcfromtimestamp(file.stat().st_mtime)
                        else:
                            cap_time = datetime.utcfromtimestamp(file.stat().st_mtime)

                        if since and cap_time < since:
                            continue
                        if until and cap_time > until:
                            continue

                        # Tag filter
                        if tag_filter and tag_filter not in meta.get("tags", []):
                            continue

                        results.append({
                            "file_path": str(file),
                            "game_name": game_dir.name.replace("_", " "),
                            "capture_type": ctype.rstrip("s"),  # screenshots→screenshot
                            "file_size_bytes": file.stat().st_size,
                            "captured_at": cap_time.isoformat(),
                            "modified_at": datetime.utcfromtimestamp(file.stat().st_mtime).isoformat(),
                            "tags": meta.get("tags", []),
                            "session_id": meta.get("session_id"),
                            "metadata": meta,
                        })

        return results

    def list_game_names(self) -> List[str]:
        return [
            d.name.replace("_", " ")
            for d in self.root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]

    # ------------------------------------------------------------------ #
    # Storage                                                              #
    # ------------------------------------------------------------------ #

    def get_storage_usage(self) -> Dict[str, Any]:
        """Return total and per-game storage usage."""
        total = 0
        by_game: Dict[str, int] = {}

        for game_dir in self.root.iterdir():
            if not game_dir.is_dir() or game_dir.name.startswith("."):
                continue
            game_size = sum(
                f.stat().st_size
                for f in game_dir.rglob("*")
                if f.is_file()
            )
            by_game[game_dir.name] = game_size
            total += game_size

        return {
            "total_bytes": total,
            "total_mb": round(total / (1024 * 1024), 2),
            "total_gb": round(total / (1024 ** 3), 3),
            "by_game_bytes": by_game,
        }

    def cleanup_old_captures(
        self,
        max_age_days: int = 90,
        max_total_gb: Optional[float] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Remove captures older than max_age_days and/or if total exceeds max_total_gb.
        Returns a summary of what was (or would be) deleted.
        """
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        deleted_files: List[str] = []
        deleted_bytes = 0

        # Collect all files sorted oldest first
        all_files = sorted(
            (f for f in self.root.rglob("*") if f.is_file() and not f.name.startswith(".")),
            key=lambda f: f.stat().st_mtime,
        )

        for f in all_files:
            try:
                mtime = datetime.utcfromtimestamp(f.stat().st_mtime)
            except FileNotFoundError:
                continue  # Already deleted (e.g., a sidecar removed earlier)
            should_delete = mtime < cutoff

            # Also delete if over size limit
            if max_total_gb and not should_delete:
                usage = self.get_storage_usage()
                should_delete = usage["total_gb"] > max_total_gb

            if should_delete:
                deleted_bytes += f.stat().st_size
                deleted_files.append(str(f))
                if not dry_run:
                    f.unlink(missing_ok=True)
                    # Remove sidecar if exists
                    sidecar = f.with_suffix(".json")
                    sidecar.unlink(missing_ok=True)

        # Remove empty directories
        if not dry_run:
            self._remove_empty_dirs()

        return {
            "dry_run": dry_run,
            "deleted_count": len(deleted_files),
            "deleted_bytes": deleted_bytes,
            "deleted_files": deleted_files[:20],  # first 20 for display
        }

    def _remove_empty_dirs(self) -> None:
        for dirpath in sorted(self.root.rglob("*"), reverse=True):
            if dirpath.is_dir() and not any(dirpath.iterdir()):
                try:
                    dirpath.rmdir()
                except Exception:
                    log.debug("Could not remove empty dir %s", dirpath)

    # ------------------------------------------------------------------ #
    # Gallery generation                                                   #
    # ------------------------------------------------------------------ #

    def create_html_gallery(self, game_name: str, output_path: Optional[Path] = None) -> Path:
        """
        Generate a simple HTML gallery of screenshots for a game.
        """
        captures = self.list_captures(game_name=game_name, capture_type="screenshot")
        if output_path is None:
            output_path = self.get_game_dir(game_name) / "gallery.html"

        img_tags = []
        for cap in captures:
            fp = Path(cap["file_path"])
            rel = fp.relative_to(self.get_game_dir(game_name))
            img_tags.append(
                f'<div class="item"><img src="{rel}" loading="lazy" '
                f'title="{html.escape(fp.name)}"></div>'
            )

        safe_game_name = html.escape(game_name)
        gallery_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{safe_game_name} — Screenshots</title>
<style>
body {{font-family: sans-serif; background: #1a1a2e; color: #eee; margin: 0; padding: 20px;}}
h1 {{color: #e94560;}}
.gallery {{display: flex; flex-wrap: wrap; gap: 10px;}}
.item img {{width: 320px; height: 180px; object-fit: cover; border-radius: 4px;
           border: 1px solid #333; transition: transform 0.2s;}}
.item img:hover {{transform: scale(1.05);}}
</style>
</head>
<body>
<h1>{safe_game_name} — Screenshot Gallery</h1>
<p>{len(img_tags)} screenshots</p>
<div class="gallery">
{"".join(img_tags)}
</div>
</body>
</html>"""

        output_path.write_text(gallery_html, encoding="utf-8")
        return output_path

    # ------------------------------------------------------------------ #
    # Metadata helpers                                                     #
    # ------------------------------------------------------------------ #

    def _write_sidecar(
        self,
        file_path: Path,
        capture_type: str,
        game_name: Optional[str],
        game_id: Optional[str],
        tags: Optional[List[str]],
        session_id: Optional[str] = None,
    ) -> Path:
        sidecar = file_path.with_suffix(".json")
        meta: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "capture_type": capture_type,
            "game_name": game_name,
            "game_id": game_id,
            "captured_at": datetime.utcnow().isoformat(),
            "tags": tags or [],
        }
        if session_id:
            meta["session_id"] = session_id
        sidecar.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return sidecar

    def tag_capture(
        self,
        file_path: Path,
        tags: List[str],
        *,
        remove_tags: Optional[List[str]] = None,
    ) -> None:
        """Add (and optionally remove) tags on a capture's sidecar metadata."""
        sidecar = file_path.with_suffix(".json")
        meta: Dict[str, Any] = {}
        if sidecar.exists():
            try:
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
            except Exception:
                log.warning("Failed to read sidecar for tagging: %s", sidecar, exc_info=True)
        existing = set(meta.get("tags", []))
        updated = (existing | set(tags)) - set(remove_tags or [])
        meta["tags"] = list(updated)
        sidecar.write_text(json.dumps(meta, indent=2), encoding="utf-8")
