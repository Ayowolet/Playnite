"""Action variable resolution: pass game metadata and environment info to scripts."""

from __future__ import annotations

import os
import platform
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playnite_py.models.game import Game


class VariableResolver:
    """Resolves template variables in action scripts and arguments.

    Variables use the format {variable_name} and can reference game fields,
    environment variables, and built-in values.
    """

    VARIABLE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")

    def __init__(self):
        self._custom_vars: dict[str, str] = {}
        self._platform_lookup: dict[str, str] = {}  # id -> name
        self._playnite_dir: str = ""
        self._emulator_dir: str = ""

    def set_custom_variable(self, name: str, value: str) -> None:
        """Register a custom variable available during resolution."""
        self._custom_vars[name] = value

    def set_platform_lookup(self, platforms: dict[str, str]) -> None:
        """Set the platform id -> name lookup table (from GameDatabase)."""
        self._platform_lookup = dict(platforms)

    def set_playnite_dir(self, path: str) -> None:
        """Set the Playnite program directory for ``{playnite_dir}``."""
        self._playnite_dir = path

    def set_emulator_dir(self, path: str) -> None:
        """Set the emulator directory for ``{emulator_dir}``."""
        self._emulator_dir = path

    def build_context(
        self,
        game: Game | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Build the full variable context for resolution."""
        ctx: dict[str, str] = {}

        # Game fields
        if game:
            ctx["game.id"] = game.id
            ctx["game.name"] = game.name
            ctx["game.source"] = game.source
            ctx["game.install_directory"] = game.install_directory
            ctx["game.is_installed"] = str(game.is_installed)
            ctx["game.playtime"] = str(game.playtime)
            ctx["game.play_count"] = str(game.play_count)
            ctx["game.completion_status"] = game.completion_status.value
            ctx["game.version"] = game.version
            ctx["game.notes"] = game.notes
            ctx["game.hidden"] = str(game.hidden)
            ctx["game.favorite"] = str(game.favorite)
            ctx["game.last_activity"] = game.last_activity or ""
            ctx["game.added"] = game.added
            ctx["game.platform_ids"] = ",".join(game.platform_ids)
            ctx["game.genre_ids"] = ",".join(game.genre_ids)
            ctx["game.tag_ids"] = ",".join(game.tag_ids)
            ctx["game.description"] = game.description

            # C#-compatible short aliases
            ctx["Name"] = game.name
            ctx["GameId"] = game.id
            ctx["Version"] = game.version
            ctx["InstallDir"] = game.install_directory
            ctx["DatabaseId"] = game.id

            # Install directory name (last component)
            if game.install_directory:
                ctx["InstallDirName"] = Path(game.install_directory).name
                ctx["game.install_dir_name"] = Path(game.install_directory).name
            else:
                ctx["InstallDirName"] = ""
                ctx["game.install_dir_name"] = ""

            # Platform name (first platform, resolved from ID)
            platform_name = ""
            if game.platform_ids:
                first_id = game.platform_ids[0]
                if self._platform_lookup:
                    platform_name = self._platform_lookup.get(first_id, first_id)
                else:
                    platform_name = first_id
            ctx["Platform"] = platform_name
            ctx["game.platform"] = platform_name

            # Plugin ID (source)
            ctx["PluginId"] = game.source
            ctx["game.plugin_id"] = game.source

        # Emulator/Image variables (populated if caller provides them)
        ctx["EmulatorDir"] = self._emulator_dir
        ctx["emulator_dir"] = self._emulator_dir

        # Playnite program directory
        ctx["PlayniteDir"] = self._playnite_dir
        ctx["playnite_dir"] = self._playnite_dir

        # Image/ROM path (caller should set via extra if applicable)
        # Provide empty defaults so templates don't leave raw {ImagePath}
        ctx.setdefault("ImagePath", "")
        ctx.setdefault("ImageName", "")
        ctx.setdefault("ImageNameNoExt", "")

        # Environment
        ctx["env.os"] = platform.system().lower()
        ctx["env.os_version"] = platform.version()
        ctx["env.hostname"] = platform.node()
        ctx["env.user"] = os.environ.get("USER", os.environ.get("USERNAME", ""))
        ctx["env.home"] = os.path.expanduser("~")
        ctx["env.cwd"] = os.getcwd()

        # Built-in
        ctx["now"] = datetime.now(timezone.utc).isoformat()
        ctx["date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ctx["time"] = datetime.now(timezone.utc).strftime("%H:%M:%S")

        # Custom variables
        ctx.update(self._custom_vars)

        # Extra overrides
        if extra:
            for k, v in extra.items():
                ctx[k] = str(v)
                # Derive ImageName/ImageNameNoExt if ImagePath is provided
                if k == "ImagePath" and v:
                    p = Path(str(v))
                    ctx["ImageName"] = p.name
                    ctx["ImageNameNoExt"] = p.stem

        return ctx

    def resolve(self, template: str, context: dict[str, str]) -> str:
        """Replace all {variable} placeholders with their values from context."""
        def _replacer(match: re.Match) -> str:
            var_name = match.group(1)
            return context.get(var_name, match.group(0))

        return self.VARIABLE_PATTERN.sub(_replacer, template)

    def resolve_dict(
        self, data: dict[str, str], context: dict[str, str]
    ) -> dict[str, str]:
        """Resolve variables in all values of a dict."""
        return {k: self.resolve(v, context) for k, v in data.items()}

    @staticmethod
    def fix_path_separators(path: str) -> str:
        """Normalise path separators for the current platform."""
        return str(Path(path)) if path else path

    def resolve_and_fix_paths(
        self,
        template: str,
        context: dict[str, str],
        path_vars: set[str] | None = None,
    ) -> str:
        """Resolve variables and normalise path separators for path-like values.

        ``path_vars`` is the set of variable names whose values should be
        path-normalised after substitution.  Defaults to common path variables.
        """
        if path_vars is None:
            path_vars = {
                "InstallDir", "game.install_directory", "EmulatorDir",
                "PlayniteDir", "ImagePath", "playnite_dir", "emulator_dir",
            }

        resolved = self.resolve(template, context)

        # Only fix separators if the resolved string looks like a path
        if os.sep in resolved or "/" in resolved or "\\" in resolved:
            resolved = self.fix_path_separators(resolved)

        return resolved
