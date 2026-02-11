"""Script dependency management with isolated virtual environments."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VenvCreationError(Exception):
    """Raised when virtual environment creation fails."""


class DependencyManager:
    """Manages isolated virtual environments and package installation for scripts."""

    def __init__(self, venvs_dir: str):
        self._venvs_dir = Path(venvs_dir)
        self._venvs_dir.mkdir(parents=True, exist_ok=True)

    def get_venv_path(self, script_id: str) -> Path:
        """Return the virtual environment directory path for a script."""
        return self._venvs_dir / script_id

    def ensure_venv(self, script_id: str) -> Path:
        """Create virtual environment if it doesn't exist.

        Raises VenvCreationError if venv creation fails.
        """
        venv_path = self.get_venv_path(script_id)
        if venv_path.exists():
            # Validate that an existing venv is not corrupted by checking for
            # the python executable.
            python = self.get_python_executable(script_id)
            if os.path.exists(python):
                return venv_path
            # Corrupted venv — remove and recreate.
            logger.warning(
                "Venv for %s appears corrupted (missing python), recreating",
                script_id,
            )
            try:
                shutil.rmtree(str(venv_path))
            except OSError as e:
                raise VenvCreationError(
                    f"Cannot remove corrupted venv at {venv_path}: {e}"
                ) from e

        logger.info("Creating venv for script %s at %s", script_id, venv_path)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "venv", str(venv_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                # Clean up partial directory if it was created
                if venv_path.exists():
                    shutil.rmtree(str(venv_path), ignore_errors=True)
                raise VenvCreationError(
                    f"venv creation failed for '{script_id}' "
                    f"(exit code {result.returncode}): {result.stderr.strip()}"
                )
        except subprocess.TimeoutExpired:
            if venv_path.exists():
                shutil.rmtree(str(venv_path), ignore_errors=True)
            raise VenvCreationError(
                f"venv creation timed out for '{script_id}'"
            )
        except VenvCreationError:
            raise
        except Exception as e:
            if venv_path.exists():
                shutil.rmtree(str(venv_path), ignore_errors=True)
            raise VenvCreationError(
                f"venv creation failed for '{script_id}': {e}"
            ) from e

        # Verify the result
        python = self.get_python_executable(script_id)
        if not os.path.exists(python):
            if venv_path.exists():
                shutil.rmtree(str(venv_path), ignore_errors=True)
            raise VenvCreationError(
                f"venv created but python executable not found at {python}"
            )

        return venv_path

    def get_pip_executable(self, script_id: str) -> str:
        """Return the path to the pip executable in the script's venv."""
        venv_path = self.get_venv_path(script_id)
        if sys.platform == "win32":
            # Try with .exe first, then without
            exe_path = venv_path / "Scripts" / "pip.exe"
            if exe_path.exists():
                return str(exe_path)
            return str(venv_path / "Scripts" / "pip")
        return str(venv_path / "bin" / "pip")

    def get_python_executable(self, script_id: str) -> str:
        """Return the path to the Python executable in the script's venv."""
        venv_path = self.get_venv_path(script_id)
        if sys.platform == "win32":
            exe_path = venv_path / "Scripts" / "python.exe"
            if exe_path.exists():
                return str(exe_path)
            return str(venv_path / "Scripts" / "python")
        return str(venv_path / "bin" / "python")

    def install_dependencies(
        self, script_id: str, dependencies: list[str]
    ) -> dict[str, Any]:
        """Install dependencies into the script's isolated venv.

        Returns a result dict with 'success', 'installed', 'failed', and 'message'.
        Unlike ensure_venv(), this method never raises — all errors are captured
        in the returned dict so callers can decide how to proceed.
        """
        if not dependencies:
            return {"success": True, "installed": [], "message": "No dependencies"}

        try:
            self.ensure_venv(script_id)
        except VenvCreationError as e:
            logger.error("Cannot install deps for %s: %s", script_id, e)
            return {
                "success": False,
                "installed": [],
                "failed": list(dependencies),
                "message": f"Venv creation failed: {e}",
            }

        pip = self.get_pip_executable(script_id)
        if not os.path.exists(pip):
            logger.error("pip not found at %s for script %s", pip, script_id)
            return {
                "success": False,
                "installed": [],
                "failed": list(dependencies),
                "message": f"pip executable not found at {pip}",
            }

        # Validate that pip is functional before spending time on each package.
        try:
            probe = subprocess.run(
                [pip, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if probe.returncode != 0:
                logger.error(
                    "pip is non-functional for %s: %s", script_id, probe.stderr.strip()
                )
                return {
                    "success": False,
                    "installed": [],
                    "failed": list(dependencies),
                    "message": f"pip --version failed (exit {probe.returncode}): {probe.stderr.strip()}",
                }
        except Exception as e:
            logger.error("pip validation failed for %s: %s", script_id, e)
            return {
                "success": False,
                "installed": [],
                "failed": list(dependencies),
                "message": f"pip validation failed: {e}",
            }

        results: list[dict[str, Any]] = []
        failed = []

        for dep in dependencies:
            try:
                result = subprocess.run(
                    [pip, "install", dep],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                success = result.returncode == 0
                results.append({
                    "package": dep,
                    "success": success,
                    "output": result.stdout,
                    "error": result.stderr if not success else "",
                })
                if not success:
                    logger.warning(
                        "pip install %s failed for %s: %s",
                        dep, script_id, result.stderr.strip(),
                    )
                    failed.append(dep)
            except subprocess.TimeoutExpired:
                logger.warning("pip install %s timed out for %s", dep, script_id)
                results.append({
                    "package": dep,
                    "success": False,
                    "output": "",
                    "error": "Installation timed out (120s)",
                })
                failed.append(dep)
            except FileNotFoundError:
                logger.error("pip executable not found: %s", pip)
                results.append({
                    "package": dep,
                    "success": False,
                    "output": "",
                    "error": f"pip executable not found: {pip}",
                })
                failed.append(dep)
                break  # No point trying more packages
            except Exception as e:
                logger.error("pip install %s error for %s: %s", dep, script_id, e)
                results.append({
                    "package": dep,
                    "success": False,
                    "output": "",
                    "error": str(e),
                })
                failed.append(dep)

        return {
            "success": len(failed) == 0,
            "installed": results,
            "failed": failed,
            "message": "All dependencies installed" if not failed else f"Failed: {failed}",
        }

    def get_installed_packages(self, script_id: str) -> list[dict[str, str]]:
        """List packages installed in the script's venv."""
        venv_path = self.get_venv_path(script_id)
        if not venv_path.exists():
            return []

        pip = self.get_pip_executable(script_id)
        if not os.path.exists(pip):
            logger.warning("pip not found at %s for script %s", pip, script_id)
            return []

        try:
            result = subprocess.run(
                [pip, "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
            logger.warning(
                "pip list failed for %s (exit %d): %s",
                script_id, result.returncode, result.stderr.strip(),
            )
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse pip list output for %s: %s", script_id, e)
        except subprocess.TimeoutExpired:
            logger.warning("pip list timed out for %s", script_id)
        except FileNotFoundError:
            logger.warning("pip executable not found: %s", pip)
        except Exception as e:
            logger.warning("Failed to list packages for %s: %s", script_id, e)
        return []

    def get_site_packages_path(self, script_id: str) -> str | None:
        """Get the site-packages directory for a script's venv."""
        python = self.get_python_executable(script_id)
        if not os.path.exists(python):
            logger.debug("Python not found at %s for script %s", python, script_id)
            return None
        try:
            result = subprocess.run(
                [python, "-c", "import site; print(site.getsitepackages()[0])"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                path = result.stdout.strip()
                if path and os.path.isdir(path):
                    return path
                logger.warning(
                    "site-packages path does not exist for %s: %s",
                    script_id, path,
                )
                return None
            logger.warning(
                "site.getsitepackages() failed for %s (exit %d): %s",
                script_id, result.returncode, result.stderr.strip(),
            )
        except subprocess.TimeoutExpired:
            logger.warning("site-packages path query timed out for %s", script_id)
        except FileNotFoundError:
            logger.warning("Python executable not found: %s", python)
        except Exception as e:
            logger.warning("Failed to get site-packages for %s: %s", script_id, e)
        return None

    def cleanup_venv(self, script_id: str) -> bool:
        """Remove a script's virtual environment.

        Returns True if the venv was removed, False if it didn't exist.
        Logs errors but does not raise.
        """
        venv_path = self.get_venv_path(script_id)
        if not venv_path.exists():
            return False
        try:
            shutil.rmtree(str(venv_path))
            logger.info("Cleaned up venv for %s", script_id)
            return True
        except OSError as e:
            logger.error("Failed to clean up venv for %s at %s: %s", script_id, venv_path, e)
            return False
