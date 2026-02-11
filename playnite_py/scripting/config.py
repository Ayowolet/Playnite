"""YAML-based script configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class SandboxLevel(Enum):
    NONE = "none"           # No restrictions (trusted scripts)
    BASIC = "basic"         # Restricted imports, limited file access
    STRICT = "strict"       # Very limited: no file I/O, no network, no subprocess


class ExtensionType(Enum):
    SCRIPT = "script"
    GENERIC_PLUGIN = "generic_plugin"
    GAME_LIBRARY = "game_library"
    METADATA_PROVIDER = "metadata_provider"


# Regex for validating version strings (major.minor.patch with optional pre-release)
_VERSION_RE = re.compile(r"^\d+\.\d+(\.\d+)?([a-zA-Z0-9._-]*)$")


# Default allowed imports for BASIC sandbox level
DEFAULT_BASIC_ALLOWED_IMPORTS = [
    "json", "math", "datetime", "re", "collections", "itertools",
    "functools", "operator", "string", "textwrap", "enum", "dataclasses",
    "typing", "copy", "uuid", "hashlib", "base64", "pathlib",
    "statistics", "decimal", "fractions", "random", "time",
]

# Additional imports allowed in NONE (all standard library)
DEFAULT_NONE_DENIED_IMPORTS = [
    "ctypes", "importlib", "code", "codeop", "compile", "compileall",
]


@dataclass
class ScriptConfig:
    """Configuration for a single script extension, loaded from config.yaml."""
    name: str = ""
    extension_id: str = ""  # Explicit unique ID (GUID or slug); falls back to dir name
    extension_type: ExtensionType = ExtensionType.SCRIPT
    enabled: bool = True
    timeout: int = 30
    sandbox_level: SandboxLevel = SandboxLevel.BASIC
    allowed_paths: list[str] = field(default_factory=list)
    allowed_imports: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    icon: str = ""  # Relative path to extension icon
    # Empty game_ids = global script; otherwise game-specific
    game_ids: list[str] = field(default_factory=list)
    auto_update: bool = True
    entry_point: str = "script.py"
    repository_url: str = ""
    min_app_version: str = ""
    links: list[dict[str, str]] = field(default_factory=list)

    def validate_version(self) -> bool:
        """Return True if ``version`` is a valid version string."""
        return bool(_VERSION_RE.match(self.version))

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty if valid)."""
        errors: list[str] = []
        if not self.name:
            errors.append("Extension name is required")
        if self.version and not self.validate_version():
            errors.append(
                f"Version '{self.version}' is not a valid version string "
                "(expected major.minor or major.minor.patch)"
            )
        return errors

    @classmethod
    def from_yaml(cls, path: str | Path) -> ScriptConfig:
        """Load a ScriptConfig from a YAML file."""
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls._from_raw(data)

    @classmethod
    def _from_raw(cls, data: dict[str, Any]) -> ScriptConfig:
        sandbox = data.get("sandbox_level", "basic")
        if isinstance(sandbox, str):
            sandbox = SandboxLevel(sandbox)
        ext_type = data.get("extension_type", "script")
        if isinstance(ext_type, str):
            try:
                ext_type = ExtensionType(ext_type)
            except ValueError:
                ext_type = ExtensionType.SCRIPT
        return cls(
            name=data.get("name", ""),
            extension_id=data.get("extension_id", data.get("id", "")),
            extension_type=ext_type,
            enabled=data.get("enabled", True),
            timeout=data.get("timeout", 30),
            sandbox_level=sandbox,
            allowed_paths=data.get("allowed_paths", []),
            allowed_imports=data.get("allowed_imports", []),
            dependencies=data.get("dependencies", []),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            description=data.get("description", ""),
            icon=data.get("icon", ""),
            game_ids=data.get("game_ids", []),
            auto_update=data.get("auto_update", True),
            entry_point=data.get("entry_point", "script.py"),
            repository_url=data.get("repository_url", ""),
            min_app_version=data.get("min_app_version", ""),
            links=data.get("links", []),
        )

    def to_yaml(self, path: str | Path) -> None:
        """Write this configuration to a YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "name": self.name,
            "extension_id": self.extension_id,
            "extension_type": self.extension_type.value,
            "enabled": self.enabled,
            "timeout": self.timeout,
            "sandbox_level": self.sandbox_level.value,
            "allowed_paths": self.allowed_paths,
            "allowed_imports": self.allowed_imports,
            "dependencies": self.dependencies,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "icon": self.icon,
            "game_ids": self.game_ids,
            "auto_update": self.auto_update,
            "entry_point": self.entry_point,
            "repository_url": self.repository_url,
            "min_app_version": self.min_app_version,
            "links": self.links,
        }

    def get_effective_allowed_imports(self) -> list[str]:
        """Return the combined list of imports allowed by sandbox level + config."""
        if self.sandbox_level == SandboxLevel.NONE:
            return []  # No restrictions
        base = list(DEFAULT_BASIC_ALLOWED_IMPORTS)
        for imp in self.allowed_imports:
            if imp not in base:
                base.append(imp)
        return base
