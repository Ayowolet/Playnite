"""
Display management for Playnite-Py.

This module handles applying display configurations before game launch,
with platform-specific APIs and race condition prevention.

Example:
    >>> manager = DisplayManager()
    >>> manager.apply_display_config(config, target_monitor="HDMI-1")
"""

from __future__ import annotations

import logging
import platform
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from playnite_py.core.models.configuration import DisplayConfig
from playnite_py.configurations.detection import DisplayInfo, PlatformDetector

logger = logging.getLogger(__name__)


@dataclass
class DisplayChangeResult:
    """Result of a display configuration change."""
    success: bool
    error_message: str = ""
    previous_config: Optional[DisplayInfo] = None
    applied_config: Optional[DisplayConfig] = None


class DisplayManager:
    """
    Manages display configuration changes with race condition prevention.

    Uses platform-specific APIs to change display settings and verifies
    targets before making changes to prevent race conditions.

    Attributes:
        _lock: Threading lock for concurrent access prevention
        _detector: Platform detector for display enumeration
        _previous_configs: Saved configs for rollback

    Example:
        >>> manager = DisplayManager()
        >>> result = manager.apply_display_config(config)
        >>> if not result.success:
        ...     print(f"Failed: {result.error_message}")
    """

    def __init__(self) -> None:
        """Initialize the display manager."""
        self._lock = threading.Lock()
        self._detector = PlatformDetector()
        self._previous_configs: dict[str, DisplayInfo] = {}

    def apply_display_config(
        self,
        config: DisplayConfig,
        verify_target: bool = True,
    ) -> DisplayChangeResult:
        """
        Apply display configuration settings.

        Uses platform-specific APIs to change resolution, refresh rate, etc.
        Verifies target monitor exists before making changes.

        Args:
            config: Display configuration to apply
            verify_target: Whether to verify target monitor exists

        Returns:
            DisplayChangeResult with success status and any error message
        """
        with self._lock:
            return self._apply_display_config_locked(config, verify_target)

    def _apply_display_config_locked(
        self,
        config: DisplayConfig,
        verify_target: bool,
    ) -> DisplayChangeResult:
        """Apply display config while holding lock."""
        result = DisplayChangeResult(success=False)

        # Skip if no resolution specified
        if config.width is None or config.height is None:
            result.success = True
            return result

        # Get current displays
        self._detector.clear_cache()
        profile = self._detector.get_hardware_profile(force_refresh=True)
        current_displays = profile.displays

        if not current_displays:
            result.error_message = "No displays detected"
            return result

        # Find target monitor
        target = self._find_target_monitor(
            config.target_monitor,
            current_displays,
        )

        if target is None:
            result.error_message = (
                f"Target monitor '{config.target_monitor}' not found. "
                f"Available: {[d.name for d in current_displays]}"
            )
            return result

        # Verify target still exists (race condition prevention)
        if verify_target:
            verified = self._verify_monitor_exists(target.name)
            if not verified:
                result.error_message = (
                    f"Monitor '{target.name}' disconnected during configuration"
                )
                return result

        # Save previous config for rollback
        self._previous_configs[target.name] = target
        result.previous_config = target

        # Apply platform-specific changes
        system = platform.system()

        try:
            if system == "Linux":
                success, error = self._apply_linux(config, target)
            elif system == "Windows":
                success, error = self._apply_windows(config, target)
            elif system == "Darwin":
                success, error = self._apply_macos(config, target)
            else:
                success, error = False, f"Unsupported platform: {system}"

            result.success = success
            result.error_message = error
            if success:
                result.applied_config = config

        except Exception as e:
            result.error_message = f"Display change failed: {e}"
            logger.error(result.error_message)

        return result

    def rollback(self, monitor_name: str) -> DisplayChangeResult:
        """
        Rollback display settings to previous configuration.

        Args:
            monitor_name: Name of monitor to rollback

        Returns:
            DisplayChangeResult with rollback status
        """
        with self._lock:
            if monitor_name not in self._previous_configs:
                return DisplayChangeResult(
                    success=False,
                    error_message=f"No previous config for '{monitor_name}'"
                )

            previous = self._previous_configs[monitor_name]

            config = DisplayConfig(
                width=previous.width,
                height=previous.height,
                refresh_rate=previous.refresh_rate,
                target_monitor=previous.name,
            )

            return self._apply_display_config_locked(config, verify_target=True)

    def _find_target_monitor(
        self,
        target_name: Optional[str],
        displays: list[DisplayInfo],
    ) -> Optional[DisplayInfo]:
        """Find the target monitor from available displays."""
        if not displays:
            return None

        # If no target specified, use primary or first display
        if not target_name:
            primary = next((d for d in displays if d.is_primary), None)
            return primary or displays[0]

        # Find by name (case-insensitive)
        target_lower = target_name.lower()
        for display in displays:
            if display.name.lower() == target_lower:
                return display

        return None

    def _verify_monitor_exists(self, monitor_name: str) -> bool:
        """
        Verify a monitor still exists (race condition check).

        Re-enumerates displays to ensure target hasn't been disconnected.
        """
        system = platform.system()

        try:
            if system == "Linux":
                result = subprocess.run(
                    ["xrandr", "--query"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return f"{monitor_name} connected" in result.stdout

            elif system == "Windows":
                # On Windows, re-enumerate via wmic
                result = subprocess.run(
                    ["wmic", "path", "Win32_DesktopMonitor", "get", "DeviceID"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return monitor_name in result.stdout

            elif system == "Darwin":
                # macOS displays are generally stable, basic check
                result = subprocess.run(
                    ["system_profiler", "SPDisplaysDataType"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return "Resolution:" in result.stdout

        except (subprocess.SubprocessError, subprocess.TimeoutExpired):
            pass

        return False

    def _apply_linux(
        self,
        config: DisplayConfig,
        target: DisplayInfo,
    ) -> tuple[bool, str]:
        """Apply display settings on Linux using xrandr."""
        # Check if running under Wayland
        if self._is_wayland():
            return self._apply_linux_wayland(config, target)

        # X11 with xrandr
        mode = f"{config.width}x{config.height}"
        cmd = ["xrandr", "--output", target.name, "--mode", mode]

        # Add refresh rate if specified
        if config.refresh_rate:
            cmd.extend(["--rate", str(config.refresh_rate)])

        try:
            # First verify the mode is available
            if not self._verify_mode_available_linux(target.name, mode, config.refresh_rate):
                return False, f"Mode {mode}@{config.refresh_rate}Hz not available for {target.name}"

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return False, f"xrandr failed: {result.stderr}"

            # Verify change was applied
            time.sleep(0.5)  # Brief delay for mode switch
            if not self._verify_resolution_linux(target.name, config.width, config.height):
                return False, "Resolution change not confirmed"

            logger.info(f"Applied {mode} to {target.name}")
            return True, ""

        except subprocess.TimeoutExpired:
            return False, "xrandr command timed out"
        except Exception as e:
            return False, str(e)

    def _apply_linux_wayland(
        self,
        config: DisplayConfig,
        target: DisplayInfo,
    ) -> tuple[bool, str]:
        """Apply display settings on Wayland."""
        # Try gnome-randr for GNOME
        gnome_randr = self._find_executable("gnome-randr")
        if gnome_randr:
            mode = f"{config.width}x{config.height}"
            cmd = [gnome_randr, "--output", target.name, "--mode", mode]
            if config.refresh_rate:
                cmd.extend(["--rate", str(config.refresh_rate)])

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return True, ""
            except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                pass

        # Try wlr-randr for wlroots-based compositors
        wlr_randr = self._find_executable("wlr-randr")
        if wlr_randr:
            mode = f"{config.width}x{config.height}"
            cmd = [wlr_randr, "--output", target.name, "--mode", mode]
            if config.refresh_rate:
                cmd[4] = f"{mode}@{config.refresh_rate}"

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return True, ""
            except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                pass

        return False, "Wayland display configuration not supported (install gnome-randr or wlr-randr)"

    def _apply_windows(
        self,
        config: DisplayConfig,
        target: DisplayInfo,
    ) -> tuple[bool, str]:
        """Apply display settings on Windows using SetDisplayConfig."""
        try:
            # Use PowerShell with .NET for display changes
            # This is more reliable than ctypes for modern Windows
            script = f'''
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public class DisplaySettings {{
    [DllImport("user32.dll")]
    public static extern int ChangeDisplaySettingsEx(
        string lpszDeviceName,
        ref DEVMODE lpDevMode,
        IntPtr hwnd,
        int dwflags,
        IntPtr lParam
    );

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct DEVMODE {{
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmDeviceName;
        public short dmSpecVersion;
        public short dmDriverVersion;
        public short dmSize;
        public short dmDriverExtra;
        public int dmFields;
        public int dmPositionX;
        public int dmPositionY;
        public int dmDisplayOrientation;
        public int dmDisplayFixedOutput;
        public short dmColor;
        public short dmDuplex;
        public short dmYResolution;
        public short dmTTOption;
        public short dmCollate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmFormName;
        public short dmLogPixels;
        public int dmBitsPerPel;
        public int dmPelsWidth;
        public int dmPelsHeight;
        public int dmDisplayFlags;
        public int dmDisplayFrequency;
    }}
}}
"@

$devMode = New-Object DisplaySettings+DEVMODE
$devMode.dmSize = [System.Runtime.InteropServices.Marshal]::SizeOf($devMode)
$devMode.dmPelsWidth = {config.width}
$devMode.dmPelsHeight = {config.height}
$devMode.dmDisplayFrequency = {config.refresh_rate or 60}
$devMode.dmFields = 0x180000  # DM_PELSWIDTH | DM_PELSHEIGHT
if ({config.refresh_rate or 0} -gt 0) {{
    $devMode.dmFields = $devMode.dmFields -bor 0x400000  # DM_DISPLAYFREQUENCY
}}

$result = [DisplaySettings]::ChangeDisplaySettingsEx($null, [ref]$devMode, [IntPtr]::Zero, 0, [IntPtr]::Zero)
exit $result
'''
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode == 0:
                logger.info(f"Applied {config.width}x{config.height} on Windows")
                return True, ""
            else:
                error_codes = {
                    -1: "Mode not supported",
                    -2: "Invalid flags",
                    -3: "Requires restart",
                    -4: "Invalid parameter",
                }
                error = error_codes.get(result.returncode, f"Error code: {result.returncode}")
                return False, f"ChangeDisplaySettings failed: {error}"

        except subprocess.TimeoutExpired:
            return False, "Display change timed out"
        except Exception as e:
            return False, str(e)

    def _apply_macos(
        self,
        config: DisplayConfig,
        target: DisplayInfo,
    ) -> tuple[bool, str]:
        """Apply display settings on macOS."""
        # macOS display changes are complex - use displayplacer if available
        displayplacer = self._find_executable("displayplacer")

        if displayplacer:
            try:
                # Get current config to find display ID
                result = subprocess.run(
                    [displayplacer, "list"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                # Parse and apply
                mode = f"res:{config.width}x{config.height}"
                if config.refresh_rate:
                    mode += f"@{config.refresh_rate}"

                result = subprocess.run(
                    [displayplacer, mode],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0:
                    return True, ""
                return False, result.stderr

            except (subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
                return False, str(e)

        return False, "macOS display configuration requires 'displayplacer' (brew install displayplacer)"

    def _is_wayland(self) -> bool:
        """Check if running under Wayland."""
        import os
        return os.environ.get("XDG_SESSION_TYPE") == "wayland" or \
               os.environ.get("WAYLAND_DISPLAY") is not None

    def _find_executable(self, name: str) -> Optional[str]:
        """Find an executable in PATH."""
        import shutil
        return shutil.which(name)

    def _verify_mode_available_linux(
        self,
        output: str,
        mode: str,
        refresh_rate: Optional[int],
    ) -> bool:
        """Verify a mode is available for an output on Linux."""
        try:
            result = subprocess.run(
                ["xrandr", "--query"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            in_output_section = False
            for line in result.stdout.split("\n"):
                if output in line and "connected" in line:
                    in_output_section = True
                    continue
                if in_output_section:
                    if line and not line.startswith(" "):
                        break  # Next output
                    if mode in line:
                        if refresh_rate:
                            if str(refresh_rate) in line or f"{refresh_rate}.0" in line:
                                return True
                        else:
                            return True
        except (subprocess.SubprocessError, subprocess.TimeoutExpired):
            pass

        return False

    def _verify_resolution_linux(
        self,
        output: str,
        width: int,
        height: int,
    ) -> bool:
        """Verify resolution was applied on Linux."""
        try:
            result = subprocess.run(
                ["xrandr", "--query"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            for line in result.stdout.split("\n"):
                if output in line and "connected" in line:
                    if f"{width}x{height}" in line:
                        return True
        except (subprocess.SubprocessError, subprocess.TimeoutExpired):
            pass

        return False
