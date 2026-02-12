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
from pathlib import Path
from typing import Optional

from playnite_py.core.models.configuration import CompatibilityConfig

logger = logging.getLogger(__name__)


class CompatibilityManager:
    """
    Manages compatibility layers for cross-platform gaming.

    Handles Wine, Proton, CrossOver, and other compatibility
    layers on Linux, as well as Windows compatibility settings.

    Example:
        >>> manager = CompatibilityManager()
        >>> cmd = manager.get_launch_command("/game.exe", config)
        >>> print(cmd)
        ['wine', '/game.exe']
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

    def get_launch_command(
        self,
        executable_path: str,
        config: CompatibilityConfig,
    ) -> Optional[list[str]]:
        """
        Get the launch command for a Windows executable.

        Args:
            executable_path: Path to the Windows executable
            config: Compatibility layer configuration

        Returns:
            List of command arguments, or None if no compatibility needed

        Example:
            >>> cmd = manager.get_launch_command("/path/game.exe", config)
        """
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

        # Set up environment variables for Wine
        self._setup_wine_environment(config)

        command.append(str(wine_path))
        command.append(executable_path)

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

        # Set up Proton environment
        self._setup_proton_environment(config, proton_path)

        proton_run = proton_path / "proton"
        return [str(proton_run), "run", executable_path]

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
                return [str(crossover_path), executable_path]

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
            return [str(whisky_wine), executable_path]

        logger.warning("Whisky not found")
        return self._get_wine_command(executable_path, config)

    def _get_gptk_command(
        self,
        executable_path: str,
        config: CompatibilityConfig,
    ) -> list[str]:
        """Build Apple Game Porting Toolkit command."""
        # GPTK on macOS
        gptk_wine = Path("/usr/local/opt/game-porting-toolkit/bin/wine64")
        if gptk_wine.exists():
            return [str(gptk_wine), executable_path]

        # Try Homebrew path
        gptk_wine = Path("$(brew --prefix game-porting-toolkit)/bin/wine64")
        return [str(gptk_wine), executable_path]

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

    def _setup_wine_environment(self, config: CompatibilityConfig) -> None:
        """Set up environment variables for Wine."""
        # Set Wine prefix
        if config.prefix_path:
            os.environ["WINEPREFIX"] = str(config.prefix_path)

        # Windows version
        os.environ["WINEARCH"] = "win64"

        # Esync/Fsync
        if config.esync_enabled:
            os.environ["WINEESYNC"] = "1"
        if config.fsync_enabled:
            os.environ["WINEFSYNC"] = "1"

        # DXVK
        if config.dxvk_enabled:
            os.environ["DXVK_LOG_LEVEL"] = "none"

        # VKD3D
        if config.vkd3d_enabled:
            os.environ["VKD3D_LOG_LEVEL"] = "none"

        # DLL overrides
        if config.dll_overrides:
            overrides = ";".join(
                f"{dll}={mode}" for dll, mode in config.dll_overrides.items()
            )
            os.environ["WINEDLLOVERRIDES"] = overrides

    def _setup_proton_environment(
        self,
        config: CompatibilityConfig,
        proton_path: Path,
    ) -> None:
        """Set up environment variables for Proton."""
        # Proton uses STEAM_COMPAT_DATA_PATH for prefix
        if config.prefix_path:
            os.environ["STEAM_COMPAT_DATA_PATH"] = str(config.prefix_path)
        else:
            # Default to proton data in profile
            os.environ["STEAM_COMPAT_DATA_PATH"] = str(
                Path.home() / ".proton" / "default"
            )

        # Ensure prefix directory exists
        prefix_path = Path(os.environ["STEAM_COMPAT_DATA_PATH"])
        prefix_path.mkdir(parents=True, exist_ok=True)

        # Steam runtime compatibility
        os.environ["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = str(
            Path.home() / ".steam" / "steam"
        )

        # Esync/Fsync
        if config.esync_enabled:
            os.environ["PROTON_NO_ESYNC"] = "0"
        else:
            os.environ["PROTON_NO_ESYNC"] = "1"

        if config.fsync_enabled:
            os.environ["PROTON_NO_FSYNC"] = "0"
        else:
            os.environ["PROTON_NO_FSYNC"] = "1"

        # DXVK
        if not config.dxvk_enabled:
            os.environ["PROTON_USE_WINED3D"] = "1"

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
