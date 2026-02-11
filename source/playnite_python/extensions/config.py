"""
Script configuration loader.

Each script can have a companion ``<script_name>.yaml`` config file.
Missing values fall back to ``ScriptConfig.defaults``.

Schema example
--------------
enabled: true
timeout: 30
sandbox_level: standard
allowed_paths:
  - /home/user/games
  - /mnt/storage
metadata:
  author: Jane Doe
  version: 2.1
  description: Tracks play sessions
dependencies:
  - requests>=2.28
  - Pillow
marketplace:
  id: jane.playtime-tracker
  repository: https://example.com/scripts.json
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


class SandboxLevel(Enum):
    """
    Sandbox strictness for script execution.

    * ``NONE``     – No restrictions; only suitable for fully trusted scripts.
    * ``STANDARD`` – Dangerous stdlib imports blocked; timeout enforced.
    * ``STRICT``   – Standard restrictions + filesystem access limited to
                      ``allowed_paths``.
    """
    NONE = "none"
    STANDARD = "standard"
    STRICT = "strict"


class ScriptConfig:
    """
    Parsed representation of a script's YAML configuration.

    Attributes
    ----------
    enabled:
        Whether the script should be loaded.
    timeout:
        Execution timeout in seconds (0 = no timeout).
    sandbox_level:
        Sandbox strictness.
    allowed_paths:
        Filesystem paths the script may access (only enforced under
        ``STRICT`` sandbox level).
    dependencies:
        pip-install specifiers required by the script.
    metadata:
        Arbitrary key/value pairs provided by the script author.
    marketplace:
        Optional marketplace registration info.
    """

    DEFAULT_TIMEOUT: int = 30
    DEFAULT_SANDBOX: SandboxLevel = SandboxLevel.STANDARD

    def __init__(self, data: Optional[Dict[str, Any]] = None) -> None:
        data = data or {}
        self.enabled: bool = bool(data.get("enabled", True))
        self.timeout: int = int(data.get("timeout", self.DEFAULT_TIMEOUT))
        raw_level = data.get("sandbox_level", self.DEFAULT_SANDBOX.value)
        try:
            self.sandbox_level: SandboxLevel = SandboxLevel(str(raw_level).lower())
        except ValueError:
            self.sandbox_level = self.DEFAULT_SANDBOX
        self.allowed_paths: List[str] = [
            str(p) for p in data.get("allowed_paths", [])
        ]
        self.dependencies: List[str] = list(data.get("dependencies", []))
        self.metadata: Dict[str, Any] = dict(data.get("metadata", {}))
        self.marketplace: Dict[str, Any] = dict(data.get("marketplace", {}))

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_file(cls, path: str) -> "ScriptConfig":
        """
        Load config from a YAML file.

        Falls back to defaults if the file does not exist or PyYAML is not
        installed.
        """
        p = Path(path)
        if not p.exists():
            return cls()
        if not _YAML_AVAILABLE:
            import warnings
            warnings.warn(
                "PyYAML is not installed; script config will use defaults.",
                RuntimeWarning,
            )
            return cls()
        with p.open("r", encoding="utf-8") as fh:
            try:
                data = yaml.safe_load(fh) or {}
            except yaml.YAMLError:
                data = {}
        return cls(data)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScriptConfig":
        return cls(d)

    @classmethod
    def default(cls) -> "ScriptConfig":
        return cls()

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "timeout": self.timeout,
            "sandbox_level": self.sandbox_level.value,
            "allowed_paths": self.allowed_paths,
            "dependencies": self.dependencies,
            "metadata": self.metadata,
            "marketplace": self.marketplace,
        }

    def save(self, path: str) -> None:
        """Persist config to *path* as YAML (requires PyYAML)."""
        if not _YAML_AVAILABLE:
            raise RuntimeError("PyYAML is required to save config files.")
        with open(path, "w", encoding="utf-8") as fh:
            yaml.dump(self.to_dict(), fh, default_flow_style=False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def is_path_allowed(self, path: str) -> bool:
        """
        Return *True* if *path* is inside one of the ``allowed_paths``.

        For ``NONE`` level all paths are permitted.  For ``STANDARD`` and
        ``STRICT``, at least one matching entry in ``allowed_paths`` is
        required; an empty ``allowed_paths`` list denies all paths.
        """
        if self.sandbox_level == SandboxLevel.NONE:
            return True
        if not self.allowed_paths:
            return False
        p = Path(path).resolve()
        return any(p.is_relative_to(Path(ap).resolve()) for ap in self.allowed_paths)

    def __repr__(self) -> str:
        return (
            f"ScriptConfig(enabled={self.enabled}, timeout={self.timeout}, "
            f"sandbox={self.sandbox_level.value})"
        )
