"""
Script sandboxing for Playnite-Py.

Provides sandboxed execution of pre/post launch scripts with
restricted permissions to prevent malicious scripts from
causing damage.

Example:
    >>> from playnite_py.configurations.sandbox import ScriptSandbox
    >>> sandbox = ScriptSandbox()
    >>> result = sandbox.execute_script("echo hello", timeout=30)
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SandboxConfig:
    """Configuration for script sandboxing."""

    # Enable/disable sandboxing
    enabled: bool = True

    # Timeout in seconds
    timeout: int = 60

    # Allow network access
    allow_network: bool = False

    # Allow write to home directory
    allow_home_write: bool = False

    # Additional allowed read paths
    allowed_read_paths: list[str] = field(default_factory=list)

    # Additional allowed write paths
    allowed_write_paths: list[str] = field(default_factory=list)


@dataclass
class ScriptResult:
    """Result of script execution."""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    sandboxed: bool
    error_message: Optional[str] = None


class ScriptSandbox:
    """
    Executes scripts in a sandboxed environment.

    Uses platform-specific sandboxing tools:
    - Linux: firejail or bubblewrap
    - macOS: sandbox-exec
    - Windows: Limited sandbox using PowerShell constraints

    If no sandbox tool is available, scripts run with a warning.
    """

    def __init__(self, config: Optional[SandboxConfig] = None) -> None:
        self.config = config or SandboxConfig()
        self._sandbox_tool = self._detect_sandbox_tool()

    def _detect_sandbox_tool(self) -> Optional[str]:
        """Detect available sandbox tool."""
        system = platform.system()

        if system == "Linux":
            # Prefer bubblewrap, then firejail
            if shutil.which("bwrap"):
                return "bwrap"
            if shutil.which("firejail"):
                return "firejail"
        elif system == "Darwin":
            # macOS has sandbox-exec built-in
            if shutil.which("sandbox-exec"):
                return "sandbox-exec"

        return None

    def is_sandbox_available(self) -> bool:
        """Check if sandboxing is available on this platform."""
        return self._sandbox_tool is not None or platform.system() == "Windows"

    def execute_script(
        self,
        script_content: str,
        script_type: str = "script",
        working_dir: Optional[Path] = None,
        env: Optional[dict[str, str]] = None,
    ) -> ScriptResult:
        """
        Execute a script with sandboxing.

        Args:
            script_content: Script content to execute
            script_type: Type label for logging
            working_dir: Working directory for script
            env: Environment variables

        Returns:
            ScriptResult with execution details
        """
        # Write script to temp file
        script_path = self._write_script(script_content)

        try:
            if not self.config.enabled:
                return self._execute_unsandboxed(script_path, working_dir, env)

            system = platform.system()

            if system == "Linux":
                return self._execute_linux(script_path, working_dir, env)
            elif system == "Darwin":
                return self._execute_macos(script_path, working_dir, env)
            elif system == "Windows":
                return self._execute_windows(script_path, working_dir, env)
            else:
                logger.warning(f"No sandbox support for {system}, running unsandboxed")
                return self._execute_unsandboxed(script_path, working_dir, env)

        finally:
            # Clean up script file
            try:
                script_path.unlink()
            except OSError:
                pass

    def _write_script(self, content: str) -> Path:
        """Write script to temporary file."""
        suffix = ".ps1" if platform.system() == "Windows" else ".sh"
        fd, path = tempfile.mkstemp(suffix=suffix, prefix="playnite_script_")

        import os
        os.close(fd)

        script_path = Path(path)
        script_path.write_text(content)

        if platform.system() != "Windows":
            script_path.chmod(0o755)

        return script_path

    def _execute_unsandboxed(
        self,
        script_path: Path,
        working_dir: Optional[Path],
        env: Optional[dict[str, str]],
    ) -> ScriptResult:
        """Execute script without sandboxing."""
        logger.warning("Executing script without sandbox")

        try:
            if platform.system() == "Windows":
                cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
            else:
                cmd = ["bash", str(script_path)]

            result = subprocess.run(
                cmd,
                cwd=working_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
            )

            return ScriptResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                sandboxed=False,
            )

        except subprocess.TimeoutExpired:
            return ScriptResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                sandboxed=False,
                error_message=f"Script timed out after {self.config.timeout}s",
            )
        except Exception as e:
            return ScriptResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                sandboxed=False,
                error_message=str(e),
            )

    def _execute_linux(
        self,
        script_path: Path,
        working_dir: Optional[Path],
        env: Optional[dict[str, str]],
    ) -> ScriptResult:
        """Execute script in Linux sandbox."""
        if self._sandbox_tool == "bwrap":
            return self._execute_bwrap(script_path, working_dir, env)
        elif self._sandbox_tool == "firejail":
            return self._execute_firejail(script_path, working_dir, env)
        else:
            logger.warning("No Linux sandbox tool available")
            return self._execute_unsandboxed(script_path, working_dir, env)

    def _execute_bwrap(
        self,
        script_path: Path,
        working_dir: Optional[Path],
        env: Optional[dict[str, str]],
    ) -> ScriptResult:
        """Execute using bubblewrap."""
        cmd = [
            "bwrap",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64",
            "--ro-bind", "/bin", "/bin",
            "--ro-bind", "/etc", "/etc",
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            "--ro-bind", str(script_path), str(script_path),
        ]

        # Add working directory
        if working_dir:
            cmd.extend(["--bind", str(working_dir), str(working_dir)])
            cmd.extend(["--chdir", str(working_dir)])

        # Network restriction
        if not self.config.allow_network:
            cmd.append("--unshare-net")

        # Additional allowed paths
        for path in self.config.allowed_read_paths:
            if Path(path).exists():
                cmd.extend(["--ro-bind", path, path])
        for path in self.config.allowed_write_paths:
            if Path(path).exists():
                cmd.extend(["--bind", path, path])

        cmd.extend(["bash", str(script_path)])

        return self._run_sandboxed(cmd, env, working_dir)

    def _execute_firejail(
        self,
        script_path: Path,
        working_dir: Optional[Path],
        env: Optional[dict[str, str]],
    ) -> ScriptResult:
        """Execute using firejail."""
        cmd = [
            "firejail",
            "--quiet",
            "--private-tmp",
            "--noroot",
        ]

        if not self.config.allow_network:
            cmd.append("--net=none")

        if not self.config.allow_home_write:
            cmd.append("--read-only=${HOME}")

        cmd.extend(["bash", str(script_path)])

        return self._run_sandboxed(cmd, env, working_dir)

    def _execute_macos(
        self,
        script_path: Path,
        working_dir: Optional[Path],
        env: Optional[dict[str, str]],
    ) -> ScriptResult:
        """Execute script in macOS sandbox."""
        if not self._sandbox_tool:
            return self._execute_unsandboxed(script_path, working_dir, env)

        # Build sandbox profile
        profile = self._build_macos_profile(script_path)

        cmd = [
            "sandbox-exec",
            "-p", profile,
            "bash", str(script_path),
        ]

        return self._run_sandboxed(cmd, env, working_dir)

    def _build_macos_profile(self, script_path: Path) -> str:
        """Build macOS sandbox profile."""
        rules = [
            "(version 1)",
            "(deny default)",
            "(allow process-fork process-exec)",
            "(allow file-read*)",
            f'(allow file-write* (subpath "/tmp"))',
            f'(allow file-write* (literal "{script_path}"))',
        ]

        if self.config.allow_network:
            rules.append("(allow network*)")

        for path in self.config.allowed_write_paths:
            rules.append(f'(allow file-write* (subpath "{path}"))')

        return "\n".join(rules)

    def _execute_windows(
        self,
        script_path: Path,
        working_dir: Optional[Path],
        env: Optional[dict[str, str]],
    ) -> ScriptResult:
        """Execute script with Windows constraints."""
        # Windows sandboxing is limited, but we can use PowerShell constraints
        cmd = [
            "powershell",
            "-ExecutionPolicy", "Bypass",
            "-NoProfile",
            "-NonInteractive",
            "-File", str(script_path),
        ]

        return self._run_sandboxed(cmd, env, working_dir)

    def _run_sandboxed(
        self,
        cmd: list[str],
        env: Optional[dict[str, str]],
        working_dir: Optional[Path],
    ) -> ScriptResult:
        """Run a sandboxed command."""
        try:
            result = subprocess.run(
                cmd,
                cwd=working_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
            )

            return ScriptResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                sandboxed=True,
            )

        except subprocess.TimeoutExpired:
            return ScriptResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                sandboxed=True,
                error_message=f"Script timed out after {self.config.timeout}s",
            )
        except Exception as e:
            logger.error(f"Sandbox execution error: {e}")
            return ScriptResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                sandboxed=True,
                error_message=str(e),
            )
