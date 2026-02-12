"""
Unit tests for configuration models.

Tests the PlatformConfiguration, LaunchArguments, and related models.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from playnite_py.core.models.configuration import (
    PlatformConfiguration,
    ConfigurationTemplate,
    LaunchArguments,
    EnvironmentConfig,
    DisplayConfig,
    AudioConfig,
    CompatibilityConfig,
    ConfigurationUsageStats,
    PlatformType,
    GraphicsQuality,
)


class TestDisplayConfig:
    """Tests for DisplayConfig model."""

    def test_default_display(self):
        """Test default display values."""
        display = DisplayConfig()
        assert display.width is None
        assert display.height is None
        assert display.fullscreen is False
        assert display.vsync is True

    def test_custom_display(self):
        """Test custom display values."""
        display = DisplayConfig(
            width=2560,
            height=1440,
            refresh_rate=144,
            fullscreen=True,
            vsync=False,
        )
        assert display.width == 2560
        assert display.height == 1440
        assert display.refresh_rate == 144
        assert display.fullscreen is True
        assert display.vsync is False


class TestAudioConfig:
    """Tests for AudioConfig model."""

    def test_default_audio(self):
        """Test default audio values."""
        audio = AudioConfig()
        assert audio.volume == 100
        assert audio.speaker_config == "stereo"
        assert audio.sample_rate == 48000

    def test_custom_audio(self):
        """Test custom audio values."""
        audio = AudioConfig(
            output_device="Headphones",
            volume=80,
            speaker_config="5.1",
        )
        assert audio.output_device == "Headphones"
        assert audio.volume == 80
        assert audio.speaker_config == "5.1"


class TestLaunchArguments:
    """Tests for LaunchArguments model."""

    def test_default_arguments(self):
        """Test default argument values."""
        args = LaunchArguments()
        assert args.base_arguments == ""
        assert args.add_arguments == []
        assert args.remove_arguments == []
        assert args.get_final_arguments() == ""

    def test_add_arguments(self):
        """Test adding arguments."""
        args = LaunchArguments(
            base_arguments="-windowed",
            add_arguments=["-debug", "-console"],
        )
        result = args.get_final_arguments()
        assert "-windowed" in result
        assert "-debug" in result
        assert "-console" in result

    def test_remove_arguments(self):
        """Test removing arguments."""
        args = LaunchArguments(
            base_arguments="-windowed -vsync -fullscreen",
            remove_arguments=["-windowed"],
        )
        result = args.get_final_arguments()
        assert "-windowed" not in result
        assert "-vsync" in result
        assert "-fullscreen" in result

    def test_replace_arguments(self):
        """Test replacing arguments."""
        args = LaunchArguments(
            base_arguments="-original -args",
            replace_arguments="-completely -new -args",
        )
        result = args.get_final_arguments()
        assert result == "-completely -new -args"

    def test_combined_operations(self):
        """Test combined add and remove."""
        args = LaunchArguments(
            base_arguments="-windowed -old",
            add_arguments=["-new"],
            remove_arguments=["-old"],
        )
        result = args.get_final_arguments()
        assert "-windowed" in result
        assert "-new" in result
        assert "-old" not in result


class TestEnvironmentConfig:
    """Tests for EnvironmentConfig model."""

    def test_default_environment(self):
        """Test default environment values."""
        env = EnvironmentConfig()
        assert env.set_variables == {}
        assert env.unset_variables == []
        assert env.inherit_system is True

    def test_set_variables(self):
        """Test setting environment variables."""
        env = EnvironmentConfig(
            set_variables={"FOO": "bar", "BAZ": "qux"},
        )
        result = env.get_environment(base_env={})
        assert result["FOO"] == "bar"
        assert result["BAZ"] == "qux"

    def test_unset_variables(self):
        """Test unsetting environment variables."""
        env = EnvironmentConfig(
            unset_variables=["REMOVE_ME"],
        )
        result = env.get_environment(base_env={"REMOVE_ME": "value", "KEEP": "value"})
        assert "REMOVE_ME" not in result
        assert result["KEEP"] == "value"

    def test_no_inherit_system(self):
        """Test not inheriting system environment."""
        env = EnvironmentConfig(
            inherit_system=False,
            set_variables={"ONLY": "this"},
        )
        result = env.get_environment(base_env=None)
        assert result == {"ONLY": "this"}


class TestCompatibilityConfig:
    """Tests for CompatibilityConfig model."""

    def test_default_compatibility(self):
        """Test default compatibility values."""
        compat = CompatibilityConfig()
        assert compat.use_compatibility_layer is False
        assert compat.layer_type == "wine"
        assert compat.esync_enabled is True
        assert compat.fsync_enabled is True
        assert compat.dxvk_enabled is True

    def test_proton_config(self):
        """Test Proton configuration."""
        compat = CompatibilityConfig(
            use_compatibility_layer=True,
            layer_type="proton",
            layer_version="8.0",
            prefix_path=Path("/home/user/.proton/game"),
        )
        assert compat.layer_type == "proton"
        assert compat.layer_version == "8.0"

    def test_invalid_layer_type(self):
        """Test invalid layer type validation."""
        with pytest.raises(ValueError):
            CompatibilityConfig(layer_type="invalid")


class TestConfigurationUsageStats:
    """Tests for ConfigurationUsageStats model."""

    def test_default_stats(self):
        """Test default statistics values."""
        stats = ConfigurationUsageStats()
        assert stats.use_count == 0
        assert stats.success_count == 0
        assert stats.failure_count == 0
        assert stats.success_rate == 0.0

    def test_record_successful_launch(self):
        """Test recording successful launch."""
        stats = ConfigurationUsageStats()
        stats.record_launch(success=True, session_minutes=60)

        assert stats.use_count == 1
        assert stats.success_count == 1
        assert stats.failure_count == 0
        assert stats.success_rate == 1.0
        assert stats.total_playtime_minutes == 60
        assert stats.last_used is not None

    def test_record_failed_launch(self):
        """Test recording failed launch."""
        stats = ConfigurationUsageStats()
        stats.record_launch(success=False)

        assert stats.use_count == 1
        assert stats.success_count == 0
        assert stats.failure_count == 1
        assert stats.success_rate == 0.0

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        stats = ConfigurationUsageStats()
        stats.record_launch(success=True)
        stats.record_launch(success=True)
        stats.record_launch(success=False)

        assert stats.success_rate == pytest.approx(0.666, rel=0.01)


class TestPlatformConfiguration:
    """Tests for PlatformConfiguration model."""

    def test_configuration_creation(self):
        """Test basic configuration creation."""
        game_id = uuid4()
        config = PlatformConfiguration(
            name="Desktop",
            game_id=game_id,
        )

        assert config.name == "Desktop"
        assert config.game_id == game_id
        assert config.platform_type == PlatformType.DESKTOP
        assert config.graphics_quality == GraphicsQuality.MEDIUM
        assert config.is_default is False
        assert config.is_enabled is True

    def test_configuration_from_template(self):
        """Test configuration creation from template."""
        template = ConfigurationTemplate(
            name="Performance",
            platform_type=PlatformType.LAPTOP,
            graphics_quality=GraphicsQuality.LOW,
        )
        game_id = uuid4()
        config = PlatformConfiguration.from_template(template, game_id)

        assert config.game_id == game_id
        assert config.platform_type == PlatformType.LAPTOP
        assert config.graphics_quality == GraphicsQuality.LOW

    def test_configuration_validation(self):
        """Test configuration validation."""
        game_id = uuid4()
        config = PlatformConfiguration(
            name="Test",
            game_id=game_id,
            display=DisplayConfig(width=1920, height=1080),
        )

        is_valid, errors = config.validate_configuration()
        assert is_valid is True
        assert errors == []

    def test_configuration_validation_bad_resolution(self):
        """Test configuration validation with invalid resolution."""
        import pytest
        from pydantic import ValidationError

        game_id = uuid4()
        # DisplayConfig validates at creation time, so invalid resolution
        # should raise a ValidationError
        with pytest.raises(ValidationError):
            PlatformConfiguration(
                name="Test",
                game_id=game_id,
                display=DisplayConfig(width=100, height=100),
            )

    def test_configuration_serialization(self):
        """Test configuration serialization."""
        game_id = uuid4()
        config = PlatformConfiguration(
            name="Desktop",
            game_id=game_id,
            display=DisplayConfig(width=1920, height=1080),
        )

        data = config.to_dict()
        restored = PlatformConfiguration.from_dict(data)

        assert restored.name == config.name
        assert restored.display.width == 1920


class TestConfigurationTemplate:
    """Tests for ConfigurationTemplate model."""

    def test_template_creation(self):
        """Test template creation."""
        template = ConfigurationTemplate(
            name="Quality",
            description="High quality settings",
            graphics_quality=GraphicsQuality.ULTRA,
        )

        assert template.name == "Quality"
        assert template.graphics_quality == GraphicsQuality.ULTRA
        assert template.is_builtin is False

    def test_builtin_template(self):
        """Test builtin template flag."""
        template = ConfigurationTemplate(
            name="Performance",
            is_builtin=True,
        )

        assert template.is_builtin is True
