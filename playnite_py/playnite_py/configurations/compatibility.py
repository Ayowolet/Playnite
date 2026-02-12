"""
Compatibility layer management for Playnite-Py.

This module handles compatibility layers like Wine/Proton on Linux,
and compatibility mode settings on Windows.

Example:
    >>> manager = CompatibilityManager()
    >>> command = manager.get_launch_command("/path/to/game.exe", compat_config)
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path, PureWindowsPath
from typing import Optional

from playnite_py.core.models.configuration import CompatibilityConfig

logger = logging.getLogger(__name__)


# Windows executable extensions
WINDOWS_EXECUTABLE_EXTENSIONS = frozenset({'.exe', '.msi', '.bat', '.cmd', '.com'})


def _normalize_path(path: str) -> Path:
    """
    Normalize a path by expanding ~ and resolving . and .. components.

    Args:
        path: Path string to normalize

    Returns:
        Normalized Path object
    """
    return Path(path).expanduser().resolve()


def _convert_unix_to_wine_path(
    unix_path: str,
    prefix_path: Optional[Path] = None,
) -> str:
    """
    Convert a Unix path to a Wine-compatible path.

    If the path is inside the Wine prefix's drive_c, converts to a C: path.
    Otherwise, returns the original path (Wine maps it via Z: drive).

    Args:
        unix_path: Unix path to convert
        prefix_path: Wine prefix path (e.g., ~/.wine)

    Returns:
        Wine-compatible path string
    """
    normalized = _normalize_path(unix_path)

    # Check if path is inside Wine prefix's drive_c
    if prefix_path:
        prefix_path = _normalize_path(str(prefix_path))
        drive_c = prefix_path / "drive_c"

        try:
            # Get relative path from drive_c
            relative = normalized.relative_to(drive_c)
            # Convert to Windows path format
            windows_path = PureWindowsPath("C:/") / relative
            return str(windows_path)
        except ValueError:
            # Path is not inside drive_c, use original
            pass

    # Return original path - Wine will map via Z: drive
    return str(normalized)


def _is_windows_executable(path: str) -> bool:
    """
    Check if a path appears to be a Windows executable.

    Args:
        path: Path to check

    Returns:
        True if path has a Windows executable extension
    """
    return Path(path).suffix.lower() in WINDOWS_EXECUTABLE_EXTENSIONS


class CompatibilityManager:
    """
    Manages compatibility layers for cross-platform gaming.

    Handles Wine, Proton, CrossOver, and other compatibility
    layers on Linux, as well as Windows compatibility settings.

    Environment variables are returned as dicts, never modifying os.environ
    directly, to prevent pollution of the parent process and ensure
    thread-safe concurrent game launches.

    Example:
        >>> manager = CompatibilityManager()
        >>> cmd = manager.get_launch_command("/game.exe", config)
        >>> env = manager.get_launch_environment(config)
        >>> subprocess.Popen(cmd, env={**os.environ, **env})
    """

    # Well-known Proton paths in Steam
    PROTON_PATHS = [
        "~/.steam/steam/steamapps/common/Proton - Experimental",
        "~/.steam/steam/steamapps/common/Proton 8.0",
        "~/.steam/steam/steamapps/common/Proton 7.0",
        "~/.local/share/Steam/steamapps/common/Proton - Experimental",
        "~/.local/share/Steam/steamapps/common/Proton 8.0",
    ]

    def __init__(self) -> None:
        """Initialize the compatibility manager."""
        self._wine_path: Optional[Path] = None
        self._proton_path: Optional[Path] = None
        self._last_env: dict[str, str] = {}  # Store env from last get_launch_command

    def get_launch_command(
        self,
        executable_path: str,
        config: CompatibilityConfig,
    ) -> Optional[list[str]]:
        """
        Get the launch command for a Windows executable.

        Also builds the environment variables needed (retrievable via
        get_launch_environment()). Does NOT modify os.environ.

        Args:
            executable_path: Path to the Windows executable
            config: Compatibility layer configuration

        Returns:
            List of command arguments, or None if no compatibility needed

        Example:
            >>> cmd = manager.get_launch_command("/path/game.exe", config)
            >>> env = manager.get_launch_environment()
            >>> subprocess.Popen(cmd, env={**os.environ, **env})
        """
        # Reset last environment
        self._last_env = {}

        # No compatibility layer needed on Windows
        if platform.system() == "Windows":
            return None

        if not config.use_compatibility_layer:
            return None

        layer_type = config.layer_type.lower()

        if layer_type == "wine":
            return self._get_wine_command(executable_path, config)
        elif layer_type == "proton":
            return self._get_proton_command(executable_path, config)
        elif layer_type == "crossover":
            return self._get_crossover_command(executable_path, config)
        elif layer_type == "whisky":
            return self._get_whisky_command(executable_path, config)
        elif layer_type == "gptk":
            return self._get_gptk_command(executable_path, config)
        else:
            logger.warning(f"Unknown compatibility layer type: {layer_type}")
            return None

    def get_launch_environment(self) -> dict[str, str]:
        """
        Get the environment variables from the last get_launch_command() call.

        Returns a dict that should be merged with os.environ and passed to
        subprocess. Does NOT modify os.environ.

        Returns:
            Dictionary of environment variables for the compatibility layer

        Example:
            >>> cmd = manager.get_launch_command("/game.exe", config)
            >>> env = manager.get_launch_environment()
            >>> full_env = {**os.environ, **env}
            >>> subprocess.Popen(cmd, env=full_env)
        """
        return self._last_env.copy()

    def _get_wine_command(
        self,
        executable_path: str,
        config: CompatibilityConfig,
    ) -> list[str]:
        """Build Wine launch command."""
        command = []

        # Find Wine executable
        wine_path = self._find_wine(config.layer_path)
        if not wine_path:
            logger.warning("Wine not found, using 'wine' from PATH")
            wine_path = "wine"

        # Build environment variables for Wine (stored for later retrieval)
        self._last_env = self._setup_wine_environment(config)

        # Normalize and convert path for Wine
        converted_path = _convert_unix_to_wine_path(
            executable_path,
            config.prefix_path,
        )

        # Warn if not a Windows executable
        if not _is_windows_executable(executable_path):
            logger.warning(
                f"Path '{executable_path}' does not appear to be a Windows executable"
            )

        command.append(str(wine_path))
        command.append(converted_path)

        return command

    def _get_proton_command(
        self,
        executable_path: str,
        config: CompatibilityConfig,
    ) -> list[str]:
        """Build Proton launch command."""
        # Find Proton installation
        proton_path = self._find_proton(config.layer_path, config.layer_version)
        if not proton_path:
            logger.warning("Proton not found, falling back to Wine")
            return self._get_wine_command(executable_path, config)

        # Build Proton environment (stored for later retrieval)
        self._last_env = self._setup_proton_environment(config, proton_path)

        # Normalize and convert path for Proton
        converted_path = _convert_unix_to_wine_path(
            executable_path,
            config.prefix_path,
        )

        # Warn if not a Windows executable
        if not _is_windows_executable(executable_path):
            logger.warning(
                f"Path '{executable_path}' does not appear to be a Windows executable"
            )

        proton_run = proton_path / "proton"
        return [str(proton_run), "run", converted_path]

    def _get_crossover_command(
        self,
        executable_path: str,
        config: CompatibilityConfig,
    ) -> list[str]:
        """Build CrossOver launch command."""
        # CrossOver on macOS
        if platform.system() == "Darwin":
            crossover_path = Path("/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/bin/wine")
            if crossover_path.exists():
                # Set up Wine environment (CrossOver uses Wine under the hood)
                self._last_env = self._setup_wine_environment(config)

                # Normalize and convert path
                converted_path = _convert_unix_to_wine_path(
                    executable_path,
                    config.prefix_path,
                )

                return [str(crossover_path), converted_path]

        logger.warning("CrossOver not found")
        return self._get_wine_command(executable_path, config)

    def _get_whisky_command(
        self,
        executable_path: str,
        config: CompatibilityConfig,
    ) -> list[str]:
        """Build Whisky launch command (macOS)."""
        # Whisky is a macOS Wine wrapper
        whisky_wine = Path("~/Library/Application Support/Whisky/Wine/bin/wine").expanduser()
        if whisky_wine.exists():
            # Set up Wine environment (Whisky uses Wine under the hood)
            self._last_env = self._setup_wine_environment(config)

            # Normalize and convert path
            converted_path = _convert_unix_to_wine_path(
                executable_path,
                config.prefix_path,
            )

            return [str(whisky_wine), converted_path]

        logger.warning("Whisky not found")
        return self._get_wine_command(executable_path, config)

    def _get_gptk_command(
        self,
        executable_path: str,
        config: CompatibilityConfig,
    ) -> list[str]:
        """Build Apple Game Porting Toolkit command."""
        gptk_wine: Optional[Path] = None

        # GPTK on macOS - check standard installation path
        standard_path = Path("/usr/local/opt/game-porting-toolkit/bin/wine64")
        if standard_path.exists():
            gptk_wine = standard_path
        else:
            # Try to find via Homebrew (properly execute the command)
            try:
                result = subprocess.run(
                    ["brew", "--prefix", "game-porting-toolkit"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    brew_prefix = Path(result.stdout.strip())
                    brew_wine = brew_prefix / "bin" / "wine64"
                    if brew_wine.exists():
                        gptk_wine = brew_wine
            except (subprocess.SubprocessError, FileNotFoundError, OSError):
                pass

        if gptk_wine:
            # Set up Wine environment (GPTK uses Wine under the hood)
            self._last_env = self._setup_wine_environment(config)

            # Normalize and convert path
            converted_path = _convert_unix_to_wine_path(
                executable_path,
                config.prefix_path,
            )

            return [str(gptk_wine), converted_path]

        logger.warning("Game Porting Toolkit not found")
        return self._get_wine_command(executable_path, config)

    def _find_wine(self, custom_path: Optional[Path] = None) -> Optional[str]:
        """Find Wine executable."""
        if custom_path:
            wine_exe = custom_path / "bin" / "wine"
            if wine_exe.exists():
                return str(wine_exe)
            if custom_path.exists():
                return str(custom_path)

        # Check PATH
        return shutil.which("wine")

    def _find_proton(
        self,
        custom_path: Optional[Path] = None,
        version: Optional[str] = None,
    ) -> Optional[Path]:
        """Find Proton installation."""
        if custom_path and custom_path.exists():
            return custom_path

        # Search well-known locations
        for path_str in self.PROTON_PATHS:
            path = Path(path_str).expanduser()
            if path.exists():
                # Check version if specified
                if version and version not in path.name:
                    continue
                return path

        return None

    def _setup_wine_environment(self, config: CompatibilityConfig) -> dict[str, str]:
        """
        Build environment variables for Wine.

        Returns a dict of environment variables to set. Does NOT modify os.environ.

        Args:
            config: Compatibility configuration

        Returns:
            Dictionary of environment variables for Wine
        """
        env: dict[str, str] = {}

        # Set Wine prefix
        if config.prefix_path:
            env["WINEPREFIX"] = str(config.prefix_path)

        # Windows version
        env["WINEARCH"] = "win64"

        # Esync/Fsync
        if config.esync_enabled:
            env["WINEESYNC"] = "1"
        if config.fsync_enabled:
            env["WINEFSYNC"] = "1"

        # DXVK
        if config.dxvk_enabled:
            env["DXVK_LOG_LEVEL"] = "none"

        # VKD3D
        if config.vkd3d_enabled:
            env["VKD3D_LOG_LEVEL"] = "none"

        # DLL overrides
        if config.dll_overrides:
            overrides = ";".join(
                f"{dll}={mode}" for dll, mode in config.dll_overrides.items()
            )
            env["WINEDLLOVERRIDES"] = overrides

        return env

    def _setup_proton_environment(
        self,
        config: CompatibilityConfig,
        proton_path: Path,
    ) -> dict[str, str]:
        """
        Build environment variables for Proton.

        Returns a dict of environment variables to set. Does NOT modify os.environ.

        Args:
            config: Compatibility configuration
            proton_path: Path to Proton installation

        Returns:
            Dictionary of environment variables for Proton
        """
        env: dict[str, str] = {}

        # Proton uses STEAM_COMPAT_DATA_PATH for prefix
        if config.prefix_path:
            compat_data_path = str(config.prefix_path)
        else:
            # Default to proton data in profile
            compat_data_path = str(Path.home() / ".proton" / "default")

        env["STEAM_COMPAT_DATA_PATH"] = compat_data_path

        # Ensure prefix directory exists
        prefix_path = Path(compat_data_path)
        prefix_path.mkdir(parents=True, exist_ok=True)

        # Steam runtime compatibility
        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = str(
            Path.home() / ".steam" / "steam"
        )

        # Esync/Fsync
        if config.esync_enabled:
            env["PROTON_NO_ESYNC"] = "0"
        else:
            env["PROTON_NO_ESYNC"] = "1"

        if config.fsync_enabled:
            env["PROTON_NO_FSYNC"] = "0"
        else:
            env["PROTON_NO_FSYNC"] = "1"

        # DXVK
        if not config.dxvk_enabled:
            env["PROTON_USE_WINED3D"] = "1"

        return env

    def detect_installed_layers(self) -> dict[str, list[str]]:
        """
        Detect installed compatibility layers.

        Returns:
            Dictionary mapping layer type to list of installed versions

        Example:
            >>> layers = manager.detect_installed_layers()
            >>> print(layers)
            {'wine': ['wine-8.0'], 'proton': ['Proton 8.0', 'Proton Experimental']}
        """
        layers: dict[str, list[str]] = {
            "wine": [],
            "proton": [],
            "crossover": [],
            "whisky": [],
            "gptk": [],
        }

        # Detect Wine
        wine = shutil.which("wine")
        if wine:
            try:
                result = subprocess.run(
                    [wine, "--version"],
                    capture_output=True,
                    text=True,
                )
                version = result.stdout.strip()
                layers["wine"].append(version)
            except (subprocess.SubprocessError, FileNotFoundError):
                layers["wine"].append("wine (version unknown)")

        # Detect Proton
        for path_str in self.PROTON_PATHS:
            path = Path(path_str).expanduser()
            if path.exists():
                layers["proton"].append(path.name)

        # Detect CrossOver (macOS)
        if platform.system() == "Darwin":
            crossover_path = Path("/Applications/CrossOver.app")
            if crossover_path.exists():
                layers["crossover"].append("CrossOver")

        # Detect Whisky (macOS)
        if platform.system() == "Darwin":
            whisky_path = Path("~/Library/Application Support/Whisky").expanduser()
            if whisky_path.exists():
                layers["whisky"].append("Whisky")

        # Detect GPTK (macOS)
        if platform.system() == "Darwin":
            gptk_path = Path("/usr/local/opt/game-porting-toolkit")
            if gptk_path.exists():
                layers["gptk"].append("Game Porting Toolkit")

        return layers

    def validate_configuration(
        self,
        config: CompatibilityConfig,
    ) -> tuple[bool, list[str]]:
        """
        Validate a compatibility configuration.

        Args:
            config: Configuration to validate

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        if not config.use_compatibility_layer:
            return True, []

        layer_type = config.layer_type.lower()

        # Check layer type is valid
        valid_types = {"wine", "proton", "crossover", "whisky", "gptk", "none"}
        if layer_type not in valid_types:
            errors.append(f"Invalid layer type: {config.layer_type}")

        # Check layer path if specified
        if config.layer_path and not config.layer_path.exists():
            errors.append(f"Compatibility layer path not found: {config.layer_path}")

        # Check prefix path if specified
        if config.prefix_path:
            parent = config.prefix_path.parent
            if not parent.exists():
                errors.append(f"Prefix parent directory not found: {parent}")

        return len(errors) == 0, errors

    def create_wine_prefix(
        self,
        prefix_path: Path,
        windows_version: str = "win10",
    ) -> bool:
        """
        Create a new Wine prefix.

        Args:
            prefix_path: Path for the new prefix
            windows_version: Windows version to emulate

        Returns:
            True if prefix was created successfully
        """
        try:
            prefix_path.mkdir(parents=True, exist_ok=True)

            # Set up environment
            env = os.environ.copy()
            env["WINEPREFIX"] = str(prefix_path)
            env["WINEARCH"] = "win64"

            # Create prefix with wineboot
            wine = shutil.which("wine")
            if not wine:
                logger.error("Wine not found")
                return False

            subprocess.run(
                ["wineboot", "--init"],
                env=env,
                capture_output=True,
                timeout=120,
            )

            # Set Windows version
            subprocess.run(
                ["wine", "winecfg", "/v", windows_version],
                env=env,
                capture_output=True,
                timeout=30,
            )

            logger.info(f"Created Wine prefix: {prefix_path}")
            return True

        except (subprocess.SubprocessError, OSError) as e:
            logger.error(f"Failed to create Wine prefix: {e}")
            return False
