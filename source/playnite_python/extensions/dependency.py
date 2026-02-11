"""
Script dependency management.

Each script that declares ``dependencies`` in its YAML config gets its own
isolated virtual environment under::

    <venv_root>/<script_name>/

Packages are installed with ``pip`` into that venv.  Scripts in the venv's
``site-packages`` are then prepended to ``sys.path`` before the script is
executed, and removed afterwards.

This approach:

* Prevents version conflicts between scripts.
* Keeps extension packages separate from the host Python environment.
* Supports offline checks (avoids reinstalling already-satisfied packages).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import venv
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Generator, List, Optional

# Module-level lock: all sys.path mutations go through this lock so that
# concurrent script loads cannot interleave their venv path entries.
_PATH_LOCK = threading.Lock()

# PEP 508 package name: alphanumeric + internal hyphens/underscores/dots.
# Matches the bare name at the start of a specifier before any extras
# ([...]) or version operators (>=, ==, ~=, etc.).
_SPEC_NAME_RE = re.compile(r"^([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)")


def _normalize_name(name: str) -> str:
    """Normalise a package name per PEP 503 (lowercase, collapse [-_.] to -)."""
    return re.sub(r"[-_.]+", "-", name).lower()


class DependencyError(Exception):
    """Raised when package installation fails."""


class DependencyManager:
    """
    Manages per-script virtual environments.

    Parameters
    ----------
    venv_root:
        Directory under which per-script venvs are created.
    """

    def __init__(self, venv_root: str = "venvs/scripts") -> None:
        self._venv_root = Path(venv_root)
        try:
            self._venv_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DependencyError(
                f"Cannot create venv root directory '{venv_root}': {exc}"
            ) from exc
        # Cache: script_name → list of installed package names (normalised)
        self._installed_cache: Dict[str, List[str]] = {}
        self._cache_lock = threading.Lock()
        # Per-script locks for ensure_venv(): serialises the check→rmtree→create
        # sequence so that concurrent calls for the same script name do not race.
        self._venv_locks: Dict[str, threading.Lock] = {}
        self._venv_locks_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Venv paths
    # ------------------------------------------------------------------

    def venv_path(self, script_name: str) -> Path:
        return self._venv_root / script_name

    def site_packages_path(self, script_name: str) -> Optional[Path]:
        """
        Return the ``site-packages`` directory for *script_name*'s venv, or
        *None* if the venv has not been created yet.
        """
        venv_dir = self.venv_path(script_name)
        if not venv_dir.exists():
            return None
        # Discover site-packages location (platform-dependent)
        for candidate in venv_dir.glob("lib/python*/site-packages"):
            return candidate
        # Windows
        win_sp = venv_dir / "Lib" / "site-packages"
        if win_sp.exists():
            return win_sp
        return None

    def python_executable(self, script_name: str) -> Path:
        """Return the Python interpreter inside *script_name*'s venv.

        Raises
        ------
        DependencyError
            If neither the Unix nor the Windows venv Python executable exists,
            indicating the venv is missing or corrupt.
        """
        venv_dir = self.venv_path(script_name)
        # Unix
        unix_py = venv_dir / "bin" / "python"
        if unix_py.exists():
            return unix_py
        # Windows
        win_py = venv_dir / "Scripts" / "python.exe"
        if win_py.exists():
            return win_py
        raise DependencyError(
            f"No Python executable found in venv for '{script_name}' "
            f"(checked {unix_py} and {win_py}). "
            "The venv may be missing or corrupt; delete it and retry."
        )

    # ------------------------------------------------------------------
    # Environment creation & package installation
    # ------------------------------------------------------------------

    def _get_venv_lock(self, script_name: str) -> threading.Lock:
        """Return the per-script lock used to serialise ensure_venv() calls."""
        with self._venv_locks_lock:
            if script_name not in self._venv_locks:
                self._venv_locks[script_name] = threading.Lock()
            return self._venv_locks[script_name]

    def ensure_venv(self, script_name: str) -> Path:
        """Create the venv for *script_name* if it doesn't already exist.

        If the venv directory already exists but is missing its Python
        executable (partial/corrupt creation), the directory is removed and
        the venv is recreated.

        Thread-safe: concurrent calls for the same *script_name* are
        serialised so that exactly one thread performs the
        check→rmtree→recreate sequence; all others wait and then find a
        functional venv already in place.

        Raises
        ------
        DependencyError
            If venv creation fails (e.g. permission denied, disk full).
        """
        import shutil

        with self._get_venv_lock(script_name):
            venv_dir = self.venv_path(script_name)
            if venv_dir.exists():
                try:
                    self.python_executable(script_name)
                    return venv_dir  # functional venv — nothing to do
                except DependencyError:
                    # Corrupt or partial venv — remove and recreate
                    shutil.rmtree(str(venv_dir))

            try:
                venv.create(str(venv_dir), with_pip=True)
            except Exception as exc:
                raise DependencyError(
                    f"Failed to create virtual environment for '{script_name}' "
                    f"at {venv_dir}: {exc}"
                ) from exc
            return venv_dir

    def install_dependencies(
        self,
        script_name: str,
        dependencies: List[str],
        force: bool = False,
        quiet: bool = True,
    ) -> List[str]:
        """
        Install *dependencies* (pip-install specifiers) into *script_name*'s venv.

        Parameters
        ----------
        script_name:
            Identifier of the script.
        dependencies:
            pip specifiers, e.g. ``["requests>=2.28", "Pillow"]``.
        force:
            If *True*, reinstall even if already present.
        quiet:
            Suppress pip output.

        Returns
        -------
        list[str]
            The specifiers that were actually installed (i.e. were missing or
            force was *True*).

        Raises
        ------
        DependencyError
            If ``pip install`` exits with a non-zero status.
        """
        if not dependencies:
            return []

        self.ensure_venv(script_name)
        python = self.python_executable(script_name)

        to_install = dependencies if force else self._filter_missing(script_name, dependencies)
        if not to_install:
            return []

        cmd = [str(python), "-m", "pip", "install"] + to_install
        if quiet:
            cmd += ["--quiet"]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise DependencyError(
                f"pip install failed for '{script_name}':\n{result.stderr}"
            )

        # Invalidate cache
        with self._cache_lock:
            self._installed_cache.pop(script_name, None)
        return to_install

    def _filter_missing(self, script_name: str, specs: List[str]) -> List[str]:
        """Return only the specs that are not already installed.

        Package names are extracted and normalised per PEP 503 before
        comparison, so ``requests[security]>=2.28`` and ``my-pkg`` are
        both handled correctly.
        """
        installed = self._get_installed(script_name)
        missing = []
        for spec in specs:
            m = _SPEC_NAME_RE.match(spec.strip())
            if m:
                pkg_name = _normalize_name(m.group(1))
            else:
                # Fallback: split on any version operator or bracket
                pkg_name = _normalize_name(re.split(r"[><=!~\[@]", spec.strip())[0])
            if pkg_name not in installed:
                missing.append(spec)
        return missing

    def _get_installed(self, script_name: str) -> List[str]:
        """Return list of installed package names (normalised) in *script_name*'s venv."""
        with self._cache_lock:
            if script_name in self._installed_cache:
                return self._installed_cache[script_name]

        try:
            python = self.python_executable(script_name)
        except DependencyError:
            # Venv not yet created or corrupt — treat as empty
            return []

        result = subprocess.run(
            [str(python), "-m", "pip", "list", "--format=json"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return []
        try:
            pkgs = [_normalize_name(p["name"]) for p in json.loads(result.stdout)]
        except (json.JSONDecodeError, KeyError):
            pkgs = []
        with self._cache_lock:
            self._installed_cache[script_name] = pkgs
        return pkgs

    def list_installed(self, script_name: str) -> List[str]:
        """Return the list of installed packages in *script_name*'s venv."""
        return self._get_installed(script_name)

    # ------------------------------------------------------------------
    # sys.path context manager
    # ------------------------------------------------------------------

    @contextmanager
    def activated(self, script_name: str) -> Generator[None, None, None]:
        """
        Context manager that temporarily prepends *script_name*'s
        ``site-packages`` to ``sys.path``.

        Thread-safe: all sys.path mutations are serialised through
        ``_PATH_LOCK`` so concurrent script loads cannot interleave their
        venv path entries.

        Usage::

            with dep_mgr.activated("my_script"):
                exec(script_code, script_globals)
        """
        sp = self.site_packages_path(script_name)
        inserted = False
        if sp is not None:
            sp_str = str(sp)
            with _PATH_LOCK:
                if sp_str not in sys.path:
                    sys.path.insert(0, sp_str)
                    inserted = True
        try:
            yield
        finally:
            if inserted:
                with _PATH_LOCK:
                    try:
                        sys.path.remove(sp_str)  # type: ignore[possibly-undefined]
                    except ValueError:
                        pass  # removed by another thread or cleanup

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def remove_venv(self, script_name: str) -> None:
        """Delete *script_name*'s virtual environment directory."""
        import shutil
        venv_dir = self.venv_path(script_name)
        if venv_dir.exists():
            shutil.rmtree(str(venv_dir))
        with self._cache_lock:
            self._installed_cache.pop(script_name, None)
        with self._venv_locks_lock:
            self._venv_locks.pop(script_name, None)

    def venv_exists(self, script_name: str) -> bool:
        return self.venv_path(script_name).exists()
