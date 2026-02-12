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
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from playnite_py.core.models.game import Game, GameAction, GameActionType
from playnite_py.core.models.configuration import (
    PlatformConfiguration,
    EnvironmentConfig,
    CompatibilityConfig,
)
from playnite_py.configurations.compatibility import CompatibilityManager

logger = logging.getLogger(__name__)


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
        self._original_env: dict[str, str] = {}
        self._temp_files: list[Path] = []

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
            # Run pre-launch script if configured
            if config and config.pre_launch_script:
                self._run_script(config.pre_launch_script, "pre-launch")

            # Set up environment
            if config:
                self._setup_environment(config.environment)

            # Build the launch command
            command = self._build_launch_command(game, action, config)
            if not command:
                result.error_message = "Failed to build launch command"
                return result

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
                    env=os.environ.copy(),
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

            # Restore environment
            self._restore_environment()

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

            # Add arguments
            if config and config.launch_args:
                # Get modified arguments from config
                action_args = action.arguments or ""
                config.launch_args.base_arguments = action_args
                final_args = config.launch_args.get_final_arguments()
                if final_args:
                    command.extend(final_args.split())
            elif action.arguments:
                command.extend(action.arguments.split())

        elif action.type == GameActionType.URL:
            if not action.path:
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

    def _setup_environment(self, env_config: EnvironmentConfig) -> None:
        """Set up the environment for game launch."""
        # Save original environment
        self._original_env = dict(os.environ)

        # Apply environment configuration
        env = env_config.get_environment()
        os.environ.update(env)

        logger.debug(f"Environment updated with {len(env_config.set_variables)} variables")

    def _restore_environment(self) -> None:
        """Restore the original environment."""
        if self._original_env:
            os.environ.clear()
            os.environ.update(self._original_env)
            self._original_env = {}
            logger.debug("Environment restored")

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
