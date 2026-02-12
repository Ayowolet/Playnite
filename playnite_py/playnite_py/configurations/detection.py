"""
Platform detection for Playnite-Py.

This module provides automatic detection of the current platform
and hardware profile for selecting appropriate game configurations.

Example:
    >>> from playnite_py.configurations.detection import detect_current_platform
    >>> platform = detect_current_platform()
    >>> print(platform)
    PlatformType.DESKTOP
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import psutil

from playnite_py.core.models.configuration import PlatformType

logger = logging.getLogger(__name__)


class PowerSource(str, Enum):
    """System power source."""
    AC = "ac"
    BATTERY = "battery"
    UNKNOWN = "unknown"


class GPUVendor(str, Enum):
    """GPU vendor identification."""
    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    APPLE = "apple"
    OTHER = "other"
    UNKNOWN = "unknown"


@dataclass
class DisplayInfo:
    """
    Information about a connected display.

    Attributes:
        name: Display name/identifier
        width: Horizontal resolution
        height: Vertical resolution
        refresh_rate: Refresh rate in Hz
        is_primary: Whether this is the primary display
        is_hdr: Whether HDR is supported
    """
    name: str
    width: int
    height: int
    refresh_rate: int = 60
    is_primary: bool = False
    is_hdr: bool = False


@dataclass
class GPUInfo:
    """
    Information about a GPU.

    Attributes:
        name: GPU name
        vendor: GPU vendor
        vram_mb: VRAM in megabytes
        driver_version: Driver version string
    """
    name: str
    vendor: GPUVendor
    vram_mb: int = 0
    driver_version: str = ""


@dataclass
class HardwareProfile:
    """
    Complete hardware profile for the current system.

    Contains all detected hardware information used for
    automatic configuration selection.

    Attributes:
        platform: Detected platform type
        os_name: Operating system name
        os_version: Operating system version
        cpu_name: CPU name
        cpu_cores: Number of CPU cores
        cpu_threads: Number of CPU threads
        ram_mb: Total RAM in megabytes
        gpus: List of detected GPUs
        displays: List of connected displays
        power_source: Current power source
        is_laptop: Whether running on a laptop
        is_steam_deck: Whether running on Steam Deck
        hostname: System hostname
    """
    platform: PlatformType
    os_name: str = ""
    os_version: str = ""
    cpu_name: str = ""
    cpu_cores: int = 0
    cpu_threads: int = 0
    ram_mb: int = 0
    gpus: list[GPUInfo] = field(default_factory=list)
    displays: list[DisplayInfo] = field(default_factory=list)
    power_source: PowerSource = PowerSource.UNKNOWN
    is_laptop: bool = False
    is_steam_deck: bool = False
    hostname: str = ""


class PlatformDetector:
    """
    Detects the current platform and hardware profile.

    Uses various system APIs and commands to gather information
    about the current hardware configuration.

    Example:
        >>> detector = PlatformDetector()
        >>> profile = detector.get_hardware_profile()
        >>> print(profile.platform)
        PlatformType.DESKTOP
    """

    def __init__(self) -> None:
        """Initialize the platform detector."""
        self._cached_profile: Optional[HardwareProfile] = None

    def get_hardware_profile(self, force_refresh: bool = False) -> HardwareProfile:
        """
        Get the complete hardware profile.

        Results are cached for performance. Use force_refresh=True
        to re-detect hardware.

        Args:
            force_refresh: Force re-detection of hardware

        Returns:
            HardwareProfile with all detected information

        Example:
            >>> profile = detector.get_hardware_profile()
        """
        if self._cached_profile and not force_refresh:
            return self._cached_profile

        profile = HardwareProfile(platform=self.detect_platform_type())

        # Gather system information
        profile.os_name = platform.system()
        profile.os_version = platform.release()
        profile.hostname = platform.node()

        # CPU information
        try:
            profile.cpu_cores = psutil.cpu_count(logical=False) or 0
            profile.cpu_threads = psutil.cpu_count(logical=True) or 0
            profile.cpu_name = self._get_cpu_name()
        except Exception as e:
            logger.debug(f"Failed to get CPU info: {e}")

        # RAM information
        try:
            mem = psutil.virtual_memory()
            profile.ram_mb = mem.total // (1024 * 1024)
        except Exception as e:
            logger.debug(f"Failed to get RAM info: {e}")

        # GPU information
        profile.gpus = self._detect_gpus()

        # Display information
        profile.displays = self._detect_displays()

        # Power source
        profile.power_source = self._detect_power_source()

        # Laptop detection
        profile.is_laptop = self._detect_is_laptop()

        # Steam Deck detection
        profile.is_steam_deck = self._detect_steam_deck()

        self._cached_profile = profile
        return profile

    def detect_platform_type(self) -> PlatformType:
        """
        Detect the current platform type.

        Uses various heuristics to determine if the system is a
        desktop, laptop, handheld, etc.

        Returns:
            Detected PlatformType
        """
        # Check for Steam Deck
        if self._detect_steam_deck():
            return PlatformType.HANDHELD

        # Check for VM
        if self._detect_vm():
            return PlatformType.VM

        # Check power source and laptop indicators
        is_laptop = self._detect_is_laptop()
        power_source = self._detect_power_source()

        if is_laptop:
            # On battery means likely mobile use
            if power_source == PowerSource.BATTERY:
                return PlatformType.LAPTOP
            # Plugged in could be desktop mode
            return PlatformType.LAPTOP

        # Default to desktop
        return PlatformType.DESKTOP

    def _get_cpu_name(self) -> str:
        """Get the CPU name/model."""
        system = platform.system()

        if system == "Linux":
            try:
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if line.startswith("model name"):
                            return line.split(":")[1].strip()
            except (IOError, IndexError):
                pass

        elif system == "Darwin":
            try:
                result = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True,
                    text=True,
                )
                return result.stdout.strip()
            except (subprocess.SubprocessError, FileNotFoundError):
                pass

        elif system == "Windows":
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
                )
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0])
            except (ImportError, OSError):
                pass

        return platform.processor()

    def _detect_gpus(self) -> list[GPUInfo]:
        """Detect installed GPUs."""
        gpus = []
        system = platform.system()

        if system == "Linux":
            gpus.extend(self._detect_gpus_linux())
        elif system == "Darwin":
            gpus.extend(self._detect_gpus_macos())
        elif system == "Windows":
            gpus.extend(self._detect_gpus_windows())

        return gpus

    def _detect_gpus_linux(self) -> list[GPUInfo]:
        """Detect GPUs on Linux."""
        gpus = []

        try:
            # Try lspci first
            result = subprocess.run(
                ["lspci", "-v"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.split("\n"):
                if "VGA" in line or "3D" in line:
                    name = line.split(":")[-1].strip()
                    vendor = self._identify_gpu_vendor(name)
                    gpus.append(GPUInfo(name=name, vendor=vendor))
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return gpus

    def _detect_gpus_macos(self) -> list[GPUInfo]:
        """Detect GPUs on macOS."""
        gpus = []

        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
            )
            current_name = ""
            for line in result.stdout.split("\n"):
                if "Chipset Model:" in line:
                    current_name = line.split(":")[-1].strip()
                    vendor = self._identify_gpu_vendor(current_name)
                    gpus.append(GPUInfo(name=current_name, vendor=vendor))
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return gpus

    def _detect_gpus_windows(self) -> list[GPUInfo]:
        """Detect GPUs on Windows."""
        gpus = []

        try:
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "name"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.split("\n")[1:]:
                name = line.strip()
                if name:
                    vendor = self._identify_gpu_vendor(name)
                    gpus.append(GPUInfo(name=name, vendor=vendor))
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return gpus

    def _identify_gpu_vendor(self, name: str) -> GPUVendor:
        """Identify GPU vendor from name string."""
        name_lower = name.lower()
        if "nvidia" in name_lower or "geforce" in name_lower:
            return GPUVendor.NVIDIA
        if "amd" in name_lower or "radeon" in name_lower:
            return GPUVendor.AMD
        if "intel" in name_lower:
            return GPUVendor.INTEL
        if "apple" in name_lower:
            return GPUVendor.APPLE
        return GPUVendor.OTHER

    def _detect_displays(self) -> list[DisplayInfo]:
        """Detect connected displays."""
        displays = []
        system = platform.system()

        if system == "Linux":
            displays = self._detect_displays_linux()
        elif system == "Darwin":
            displays = self._detect_displays_macos()
        elif system == "Windows":
            displays = self._detect_displays_windows()

        return displays

    def _detect_displays_linux(self) -> list[DisplayInfo]:
        """Detect displays on Linux using xrandr."""
        displays = []

        try:
            result = subprocess.run(
                ["xrandr", "--query"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.split("\n"):
                if " connected" in line:
                    parts = line.split()
                    name = parts[0]
                    is_primary = "primary" in parts

                    # Find resolution
                    for part in parts:
                        if "x" in part and part[0].isdigit():
                            try:
                                res = part.split("+")[0]
                                width, height = map(int, res.split("x"))
                                displays.append(DisplayInfo(
                                    name=name,
                                    width=width,
                                    height=height,
                                    is_primary=is_primary,
                                ))
                                break
                            except ValueError:
                                pass
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return displays

    def _detect_displays_macos(self) -> list[DisplayInfo]:
        """Detect displays on macOS."""
        displays = []

        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
            )
            # Parse resolution from output
            for line in result.stdout.split("\n"):
                if "Resolution:" in line:
                    try:
                        res_part = line.split(":")[1].strip()
                        # Format: "2560 x 1440 Retina"
                        parts = res_part.split()
                        width = int(parts[0])
                        height = int(parts[2])
                        displays.append(DisplayInfo(
                            name="Display",
                            width=width,
                            height=height,
                            is_primary=len(displays) == 0,
                        ))
                    except (IndexError, ValueError):
                        pass
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return displays

    def _detect_displays_windows(self) -> list[DisplayInfo]:
        """Detect displays on Windows."""
        displays = []

        try:
            result = subprocess.run(
                ["wmic", "path", "Win32_VideoController", "get",
                 "CurrentHorizontalResolution,CurrentVerticalResolution"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.split("\n")[1:]:
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        width = int(parts[0])
                        height = int(parts[1])
                        displays.append(DisplayInfo(
                            name=f"Display {len(displays) + 1}",
                            width=width,
                            height=height,
                            is_primary=len(displays) == 0,
                        ))
                    except ValueError:
                        pass
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return displays

    def _detect_power_source(self) -> PowerSource:
        """Detect the current power source."""
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return PowerSource.AC  # No battery = desktop
            return PowerSource.BATTERY if not battery.power_plugged else PowerSource.AC
        except Exception:
            return PowerSource.UNKNOWN

    def _detect_is_laptop(self) -> bool:
        """Detect if running on a laptop."""
        # Check for battery
        try:
            battery = psutil.sensors_battery()
            if battery is not None:
                return True
        except Exception:
            pass

        # Check for laptop-specific files on Linux
        if platform.system() == "Linux":
            laptop_indicators = [
                "/sys/class/power_supply/BAT0",
                "/sys/class/power_supply/BAT1",
                "/sys/devices/platform/thinkpad_acpi",
            ]
            for indicator in laptop_indicators:
                if Path(indicator).exists():
                    return True

        return False

    def _detect_steam_deck(self) -> bool:
        """Detect if running on Steam Deck."""
        # Check for Steam Deck-specific identifiers
        if platform.system() == "Linux":
            # Check DMI product name
            try:
                with open("/sys/devices/virtual/dmi/id/product_name") as f:
                    if "Jupiter" in f.read():
                        return True
            except (IOError, FileNotFoundError):
                pass

            # Check for SteamOS
            try:
                with open("/etc/os-release") as f:
                    if "SteamOS" in f.read():
                        return True
            except (IOError, FileNotFoundError):
                pass

        return False

    def _detect_vm(self) -> bool:
        """Detect if running in a virtual machine."""
        system = platform.system()

        # Check for common VM indicators
        vm_indicators = [
            "VBOX",
            "VMWARE",
            "QEMU",
            "VIRTUAL",
            "XEN",
            "HYPERV",
        ]

        if system == "Linux":
            try:
                result = subprocess.run(
                    ["systemd-detect-virt"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0 and result.stdout.strip() != "none":
                    return True
            except (subprocess.SubprocessError, FileNotFoundError):
                pass

            # Check DMI
            try:
                with open("/sys/devices/virtual/dmi/id/product_name") as f:
                    content = f.read().upper()
                    for indicator in vm_indicators:
                        if indicator in content:
                            return True
            except (IOError, FileNotFoundError):
                pass

        return False

    def clear_cache(self) -> None:
        """Clear the cached hardware profile."""
        self._cached_profile = None


def detect_current_platform() -> PlatformType:
    """
    Convenience function to detect the current platform type.

    Returns:
        Detected PlatformType

    Example:
        >>> platform = detect_current_platform()
        >>> print(platform)
        PlatformType.DESKTOP
    """
    detector = PlatformDetector()
    return detector.detect_platform_type()
