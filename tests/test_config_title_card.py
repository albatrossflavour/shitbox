"""Tests for TitleCardConfig dataclass and load_config round-trip (plan 26-02)."""

import textwrap
from pathlib import Path

import pytest

from shitbox.utils.config import CaptureConfig, TitleCardConfig, load_config


class TestTitleCardConfigDefaults:
    """Test 1: TitleCardConfig default values."""

    def test_enabled_default(self):
        cfg = TitleCardConfig()
        assert cfg.enabled is True

    def test_duration_seconds_default(self):
        cfg = TitleCardConfig()
        assert cfg.duration_seconds == 3.0

    def test_show_driver_default(self):
        cfg = TitleCardConfig()
        assert cfg.show_driver is True

    def test_whimsy_lines_default_is_empty_list(self):
        cfg = TitleCardConfig()
        assert cfg.whimsy_lines == []

    def test_whimsy_lines_default_is_a_list(self):
        cfg = TitleCardConfig()
        assert isinstance(cfg.whimsy_lines, list)


class TestCaptureConfigTitleCardField:
    """Test 2: CaptureConfig.title_card is a TitleCardConfig with defaults."""

    def test_title_card_field_exists(self):
        cfg = CaptureConfig()
        assert hasattr(cfg, "title_card")

    def test_title_card_is_title_card_config_instance(self):
        cfg = CaptureConfig()
        assert isinstance(cfg.title_card, TitleCardConfig)

    def test_title_card_has_default_enabled(self):
        cfg = CaptureConfig()
        assert cfg.title_card.enabled is True

    def test_title_card_has_default_duration(self):
        cfg = CaptureConfig()
        assert cfg.title_card.duration_seconds == 3.0

    def test_title_card_has_default_show_driver(self):
        cfg = CaptureConfig()
        assert cfg.title_card.show_driver is True

    def test_title_card_has_empty_whimsy_lines(self):
        cfg = CaptureConfig()
        assert cfg.title_card.whimsy_lines == []


class TestLoadConfigYamlRoundTrip:
    """Test 3: load_config round-trip with full overrides."""

    def test_round_trip_with_overrides(self, tmp_path: Path):
        yaml_text = textwrap.dedent("""\
            capture:
              title_card:
                enabled: false
                duration_seconds: 2.5
                show_driver: false
                whimsy_lines:
                  - "Line one"
                  - "Line two"
        """)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_text)

        cfg = load_config(config_file)
        tc = cfg.capture.title_card

        assert tc.enabled is False
        assert tc.duration_seconds == 2.5
        assert tc.show_driver is False
        assert tc.whimsy_lines == ["Line one", "Line two"]

    def test_round_trip_enabled_override(self, tmp_path: Path):
        yaml_text = textwrap.dedent("""\
            capture:
              title_card:
                enabled: false
        """)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_text)

        cfg = load_config(config_file)
        assert cfg.capture.title_card.enabled is False

    def test_round_trip_whimsy_lines_order_preserved(self, tmp_path: Path):
        yaml_text = textwrap.dedent("""\
            capture:
              title_card:
                whimsy_lines:
                  - "Alpha"
                  - "Beta"
                  - "Gamma"
        """)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_text)

        cfg = load_config(config_file)
        assert cfg.capture.title_card.whimsy_lines == ["Alpha", "Beta", "Gamma"]


class TestLoadConfigEmptyCaptureBlock:
    """Test 4: Empty capture block yields TitleCardConfig defaults."""

    def test_empty_capture_block(self, tmp_path: Path):
        yaml_text = textwrap.dedent("""\
            capture: {}
        """)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_text)

        cfg = load_config(config_file)
        tc = cfg.capture.title_card

        assert tc.enabled is True
        assert tc.duration_seconds == 3.0
        assert tc.show_driver is True
        assert tc.whimsy_lines == []


class TestLoadConfigMissingTitleCardKey:
    """Test 5: Missing title_card key under capture yields TitleCardConfig defaults."""

    def test_missing_title_card_key(self, tmp_path: Path):
        yaml_text = textwrap.dedent("""\
            capture:
              enabled: true
              gpio_pin: 17
        """)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_text)

        cfg = load_config(config_file)
        tc = cfg.capture.title_card

        assert tc.enabled is True
        assert tc.duration_seconds == 3.0
        assert tc.show_driver is True
        assert tc.whimsy_lines == []

    def test_no_capture_key_at_all(self, tmp_path: Path):
        yaml_text = textwrap.dedent("""\
            app:
              name: shitbox-telemetry
        """)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_text)

        cfg = load_config(config_file)
        tc = cfg.capture.title_card

        assert tc.enabled is True
        assert tc.duration_seconds == 3.0
        assert tc.show_driver is True
        assert tc.whimsy_lines == []
