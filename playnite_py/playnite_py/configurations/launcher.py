"""
Game launcher for Playnite-Py.

This module handles launching games with platform-specific configurations,
including environment setup, pre/post launch scripts, and compatibility layers.

Example:
    >>> launcher = GameLauncher()
    >>> result = launcher.launch_game(game, config)
    >>> if result.success:
    ...     print(f"Game ran for {result.duration_seconds} seconds")
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from playnite_py.core.models.game import Game, GameAction, GameActionType
from playnite_py.core.models.configuration import (
    PlatformConfiguration,
    CompatibilityConfig,
)
from playnite_py.configurations.compatibility import CompatibilityManager
from playnite_py.configurations.display import DisplayManager

logger = logging.getLogger(__name__)

# Security: Allowed URL protocols for URL actions (Gap 3 fix)
ALLOWED_URL_PROTOCOLS = frozenset({
    "http", "https",          # Web URLs
    "steam",                  # Steam protocol
    "uplay", "ubisoft",       # Ubisoft
    "origin",                 # EA/Origin
    "com.epicgames.launcher", # Epic Games
    "battlenet",              # Battle.net
    "gog",                    # GOG Galaxy
    "rungameid",              # Generic game launcher
})

# Security: Patterns that indicate potentially dangerous arguments
DANGEROUS_ARG_PATTERNS = re.compile(
    r'[;&|`$]|'           # Shell metacharacters
    r'\.\.[/\\]|'         # Path traversal
    r'^-[a-z]*n\b',       # Arguments that might enable "dry-run" bypass
    flags=re.IGNORECASE
)


def _sanitize_argument(arg: str) -> str:
    """
    Sanitize a single argument for safe execution.

    Removes or escapes potentially dangerous characters while
    preserving the argument's intended functionality.

    Args:
        arg: The argument to sanitize

    Returns:
        Sanitized argument string
    """
    # Remove null bytes
    arg = arg.replace('\x00', '')
    # Remove newlines/carriage returns (argument injection)
    arg = arg.replace('\n', '').replace('\r', '')
    return arg


def _validate_executable_path(path: str) -> tuple[bool, str]:
    """
    Validate an executable path for security issues.

    Args:
        path: The executable path to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not path:
        return False, "Empty executable path"

    # Check for path traversal
    if '..' in path:
        return False, "Path traversal detected in executable path"

    # Check for shell metacharacters in path
    if any(c in path for c in ';|&`$'):
        return False, "Shell metacharacters detected in executable path"

    # Resolve to absolute path and check existence
    resolved = Path(path).resolve()
    if not resolved.exists():
        return False, f"Executable not found: {path}"

    return True, ""


def _validate_url(url: str) -> tuple[bool, str]:
    """
    Validate a URL for allowed protocols.

    Args:
        url: The URL to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        parsed = urllib.parse.urlparse(url)
        protocol = parsed.scheme.lower()

        if not protocol:
            return False, "URL has no protocol scheme"

        if protocol not in ALLOWED_URL_PROTOCOLS:
            return False, f"URL protocol '{protocol}' not allowed. Allowed: {', '.join(sorted(ALLOWED_URL_PROTOCOLS))}"

        return True, ""
    except Exception as e:
        return False, f"Invalid URL: {e}"


@dataclass
class LaunchResult:
    """
    Result of a game launch attempt.

    Attributes:
        success: Whether the launch was successful
        game_id: ID of the launched game
        config_id: ID of the configuration used
        start_time: When the game was launched
        end_time: When the game exited
        duration_seconds: How long the game ran
        exit_code: Process exit code
        error_message: Error message if launch failed
        used_fallback: Whether fallback configuration was used
        fallback_config_id: ID of fallback configuration if used
    """
    success: bool
    game_id: UUID
    config_id: Optional[UUID] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: int = 0
    exit_code: Optional[int] = None
    error_message: str = ""
    used_fallback: bool = False
    fallback_config_id: Optional[UUID] = None


class GameLauncher:
    """
    Handles launching games with configurations.

    Manages the complete launch process including environment setup,
    pre-launch scripts, game execution, post-launch cleanup, and
    compatibility layers.

    Attributes:
        compatibility_manager: Compatibility layer manager

    Example:
        >>> launcher = GameLauncher()
        >>> result = launcher.launch_game(game, config)
    """

    def __init__(self) -> None:
        """Initialize the game launcher."""
        self.compatibility_manager = CompatibilityManager()
        self.display_manager = DisplayManager()
        self._temp_files: list[Path] = []
        self._display_changed: bool = False
        self._display_monitor: Optional[str] = None

    def launch_game(
        self,
        game: Game,
        config: Optional[PlatformConfiguration] = None,
        action: Optional[GameAction] = None,
        wait_for_exit: bool = True,
    ) -> LaunchResult:
        """
        Launch a game with the specified configuration.

        Args:
            game: Game to launch
            config: Platform configuration to use
            action: Specific game action (defaults to default action)
            wait_for_exit: Wait for game to exit before returning

        Returns:
            LaunchResult with launch status and timing information

        Example:
            >>> result = launcher.launch_game(game, config)
            >>> if result.success:
            ...     print(f"Played for {result.duration_seconds // 60} minutes")
        """
        result = LaunchResult(success=False, game_id=game.id)

        if config:
            result.config_id = config.id

        # Get the action to execute
        if action is None:
            action = game.get_default_action()
        if action is None:
            result.error_message = "No game action available"
            return result

        try:
            # Apply display configuration if specified (with race condition prevention)
            self._display_changed = False
            self._display_monitor = None
            if config and config.display:
                display_result = self.display_manager.apply_display_config(
                    config.display,
                    verify_target=True,  # Verify monitor exists before changing
                )
                if display_result.success and display_result.applied_config:
                    self._display_changed = True
                    self._display_monitor = config.display.target_monitor
                    logger.info(
                        f"Applied display config: {config.display.width}x{config.display.height}"
                    )
                elif display_result.error_message:
                    logger.warning(f"Display config failed: {display_result.error_message}")

            # Run pre-launch script if configured
            if config and config.pre_launch_script:
                self._run_script(config.pre_launch_script, "pre-launch")

            # Build the launch command (this also prepares compatibility env)
            command = self._build_launch_command(game, action, config)
            if not command:
                result.error_message = "Failed to build launch command"
                return result

            # Build the environment dict (without modifying os.environ)
            launch_env = self._build_launch_environment(config)

            # Launch the game
            result.start_time = datetime.now()
            logger.info(f"Launching game: {game.name}")
            logger.debug(f"Command: {' '.join(command)}")

            try:
                # Set working directory
                working_dir = self._get_working_directory(game, action, config)

                process = subprocess.Popen(
                    command,
                    cwd=working_dir,
                    env=launch_env,  # Pass explicit env dict, never modify os.environ
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                if wait_for_exit:
                    process.wait()
                    result.exit_code = process.returncode
                    result.end_time = datetime.now()
                    result.duration_seconds = int(
                        (result.end_time - result.start_time).total_seconds()
                    )
                    result.success = process.returncode == 0
                else:
                    # Non-blocking launch
                    result.success = True

            except FileNotFoundError as e:
                result.error_message = f"Executable not found: {e}"
                logger.error(result.error_message)

            except PermissionError as e:
                result.error_message = f"Permission denied: {e}"
                logger.error(result.error_message)

        except Exception as e:
            result.error_message = str(e)
            logger.error(f"Launch failed: {e}")

        finally:
            # Run post-launch script
            if config and config.post_launch_script:
                self._run_script(config.post_launch_script, "post-launch")

            # Rollback display settings if changed and game has exited
            if self._display_changed and wait_for_exit and self._display_monitor:
                rollback_result = self.display_manager.rollback(self._display_monitor)
                if rollback_result.success:
                    logger.info("Restored previous display settings")
                else:
                    logger.warning(f"Display rollback failed: {rollback_result.error_message}")

            # Clean up temp files
            self._cleanup_temp_files()

        # Handle fallback if launch failed
        if not result.success and config and config.fallback_config_id:
            logger.info(
                f"Primary configuration failed, trying fallback: "
                f"{config.fallback_config_id}"
            )
            # Note: In practice, we'd need to load the fallback config
            # This is handled by the ConfigurationManager
            result.used_fallback = True
            result.fallback_config_id = config.fallback_config_id

        return result

    def _build_launch_command(
        self,
        game: Game,
        action: GameAction,
        config: Optional[PlatformConfiguration],
    ) -> Optional[list[str]]:
        """
        Build the command to launch the game.

        Includes security validation for executable paths, arguments,
        and URLs to prevent injection attacks.

        Args:
            game: Game being launched
            action: Action to execute
            config: Platform configuration

        Returns:
            List of command arguments, or None if invalid
        """
        command: list[str] = []

        # Handle different action types
        if action.type == GameActionType.FILE:
            if not action.path:
                return None

            # Security: Validate executable path (Gap 2 fix)
            is_valid, error = _validate_executable_path(action.path)
            if not is_valid:
                logger.error(f"Security: {error}")
                return None

            # Check for compatibility layer on Linux
            if platform.system() == "Linux" and config:
                compat_cmd = self.compatibility_manager.get_launch_command(
                    action.path, config.compatibility
                )
                if compat_cmd:
                    command.extend(compat_cmd)
                else:
                    command.append(action.path)
            else:
                command.append(action.path)

            # Add arguments - use shlex.split for proper parsing (Gap 1 & 5 fix)
            if config and config.launch_args:
                action_args = action.arguments or ""
                config.launch_args.base_arguments = action_args
                final_args = config.launch_args.get_final_arguments()
                if final_args:
                    # Security: Use shlex.split to properly handle quoted arguments
                    # and prevent argument injection
                    try:
                        parsed_args = shlex.split(final_args)
                        # Sanitize each argument
                        command.extend(_sanitize_argument(arg) for arg in parsed_args)
                    except ValueError as e:
                        logger.warning(f"Failed to parse arguments '{final_args}': {e}")
                        # Fall back to simple split but sanitize
                        command.extend(_sanitize_argument(arg) for arg in final_args.split())
            elif action.arguments:
                try:
                    parsed_args = shlex.split(action.arguments)
                    command.extend(_sanitize_argument(arg) for arg in parsed_args)
                except ValueError:
                    command.extend(_sanitize_argument(arg) for arg in action.arguments.split())

        elif action.type == GameActionType.URL:
            if not action.path:
                return None

            # Security: Validate URL protocol (Gap 3 fix)
            is_valid, error = _validate_url(action.path)
            if not is_valid:
                logger.error(f"Security: {error}")
                return None

            # Open URL with system browser
            if platform.system() == "Linux":
                command = ["xdg-open", action.path]
            elif platform.system() == "Darwin":
                command = ["open", action.path]
            else:  # Windows
                command = ["start", action.path]

        elif action.type == GameActionType.SCRIPT:
            if not action.script_content:
                return None

            # Security warning for script execution (Gap 4 fix)
            logger.warning(
                "Security: Executing user-provided script. "
                "Script content should be reviewed for malicious code."
            )

            # Write script to temp file and execute
            script_path = self._write_temp_script(action.script_content)
            if platform.system() == "Windows":
                command = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
            else:
                command = ["bash", str(script_path)]

        elif action.type == GameActionType.EMULATOR:
            # Emulator launching would be handled by emulator subsystem
            logger.warning("Emulator launching not yet implemented")
            return None

        return command if command else None

    def _get_working_directory(
        self,
        game: Game,
        action: GameAction,
        config: Optional[PlatformConfiguration],
    ) -> Optional[str]:
        """
        Determine the working directory for launching.

        Priority:
        1. Configuration working directory
        2. Action working directory
        3. Game install directory
        4. Directory containing the executable
        """
        # Check config override
        if config and config.working_directory:
            return str(config.working_directory)

        # Check action working directory
        if action.working_directory:
            return str(action.working_directory)

        # Use game install directory
        if game.install_directory:
            return str(game.install_directory)

        # Use executable directory
        if action.path:
            exe_path = Path(action.path)
            if exe_path.parent.exists():
                return str(exe_path.parent)

        return None

    # Security: Variables that should never be expanded to prevent info disclosure (Gap 6 fix)
    SENSITIVE_ENV_VARS = frozenset({
        # Authentication/Secrets
        "PASSWORD", "SECRET", "TOKEN", "API_KEY", "APIKEY", "AUTH",
        "PRIVATE_KEY", "AWS_SECRET", "AZURE_SECRET", "GCP_SECRET",
        # SSH/Security
        "SSH_AUTH_SOCK", "SSH_AGENT_PID", "GPG_AGENT_INFO",
        # Database credentials
        "DATABASE_URL", "DB_PASSWORD", "MYSQL_PASSWORD", "PGPASSWORD",
        # Common sensitive patterns
        "CREDENTIAL", "PASS", "KEY", "CERT",
    })

    def _is_sensitive_var(self, var_name: str) -> bool:
        """Check if an environment variable name indicates sensitive data."""
        upper_name = var_name.upper()
        return any(sensitive in upper_name for sensitive in self.SENSITIVE_ENV_VARS)

    def _build_launch_environment(
        self,
        config: Optional[PlatformConfiguration],
    ) -> dict[str, str]:
        """
        Build the environment dict for launching a game.

        Creates an isolated environment dict without modifying os.environ.
        This ensures thread-safety and prevents pollution of the parent process.

        Security: Sensitive environment variables are excluded from expansion
        to prevent information disclosure (Gap 6 fix).

        Args:
            config: Platform configuration (may be None)

        Returns:
            Complete environment dict to pass to subprocess
        """
        # Start with a copy of the current environment
        env = os.environ.copy()

        # Apply user environment config if provided
        if config and config.environment:
            # Unset specified variables
            for var in config.environment.unset_variables:
                env.pop(var, None)

            # Set specified variables (with expansion if enabled)
            for name, value in config.environment.set_variables.items():
                if config.environment.expand_variables:
                    # Security: Only expand non-sensitive variables (Gap 6 fix)
                    for existing_name, existing_value in env.items():
                        # Skip sensitive variables to prevent info disclosure
                        if self._is_sensitive_var(existing_name):
                            continue
                        value = value.replace(f"${existing_name}", existing_value)
                        value = value.replace(f"${{{existing_name}}}", existing_value)
                env[name] = value

        # Add compatibility layer environment variables
        compat_env = self.compatibility_manager.get_launch_environment()
        env.update(compat_env)

        logger.debug(
            f"Built launch environment with "
            f"{len(config.environment.set_variables) if config and config.environment else 0} "
            f"user vars and {len(compat_env)} compatibility vars"
        )

        return env

    def _run_script(self, script_content: str, script_type: str) -> bool:
        """
        Run a pre or post launch script.

        Args:
            script_content: Script content to execute
            script_type: Type of script (for logging)

        Returns:
            True if script succeeded, False otherwise
        """
        try:
            script_path = self._write_temp_script(script_content)
            logger.debug(f"Running {script_type} script: {script_path}")

            if platform.system() == "Windows":
                result = subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
                    capture_output=True,
                    timeout=60,
                )
            else:
                result = subprocess.run(
                    ["bash", str(script_path)],
                    capture_output=True,
                    timeout=60,
                )

            if result.returncode != 0:
                logger.warning(
                    f"{script_type} script failed with code {result.returncode}"
                )
                return False

            return True

        except subprocess.TimeoutExpired:
            logger.error(f"{script_type} script timed out")
            return False
        except Exception as e:
            logger.error(f"{script_type} script error: {e}")
            return False

    def _write_temp_script(self, content: str) -> Path:
        """Write script content to a temporary file."""
        suffix = ".ps1" if platform.system() == "Windows" else ".sh"
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)

        script_path = Path(path)
        script_path.write_text(content)

        # Make executable on Unix
        if platform.system() != "Windows":
            script_path.chmod(0o755)

        self._temp_files.append(script_path)
        return script_path

    def _cleanup_temp_files(self) -> None:
        """Clean up temporary files created during launch."""
        for path in self._temp_files:
            try:
                if path.exists():
                    path.unlink()
            except OSError as e:
                logger.warning(f"Failed to clean up temp file {path}: {e}")
        self._temp_files.clear()

    def validate_launch(
        self,
        game: Game,
        action: Optional[GameAction] = None,
    ) -> tuple[bool, list[str]]:
        """
        Validate that a game can be launched.

        Checks that the executable exists and is accessible.

        Args:
            game: Game to validate
            action: Action to validate (defaults to default action)

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        if action is None:
            action = game.get_default_action()

        if action is None:
            errors.append("No game action available")
            return False, errors

        if action.type == GameActionType.FILE:
            if not action.path:
                errors.append("No executable path specified")
            else:
                exe_path = Path(action.path)
                if not exe_path.exists():
                    errors.append(f"Executable not found: {action.path}")
                elif not os.access(exe_path, os.X_OK) and platform.system() != "Windows":
                    errors.append(f"Executable not accessible: {action.path}")

        elif action.type == GameActionType.URL:
            if not action.path:
                errors.append("No URL specified")

        elif action.type == GameActionType.SCRIPT:
            if not action.script_content:
                errors.append("No script content specified")

        return len(errors) == 0, errors

    def get_effective_environment(
        self,
        config: PlatformConfiguration,
    ) -> dict[str, str]:
        """
        Get the effective environment for a configuration.

        Returns the environment that would be used when launching
        with this configuration.

        Args:
            config: Configuration to get environment for

        Returns:
            Dictionary of environment variables
        """
        return config.environment.get_environment()
