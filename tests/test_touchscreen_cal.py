"""Validate the Waveshare touchscreen xorg.conf.d calibration file."""

from pathlib import Path

import pytest

CONF_PATH = Path(__file__).parent.parent / "systemd" / "99-waveshare-touchscreen.conf"


@pytest.fixture
def conf_content() -> str:
    return CONF_PATH.read_text()


def test_config_file_exists() -> None:
    assert CONF_PATH.exists(), f"Config file missing at {CONF_PATH}"


def test_config_has_input_class_section(conf_content: str) -> None:
    assert 'Section "InputClass"' in conf_content
    assert "EndSection" in conf_content


def test_config_has_transformation_matrix(conf_content: str) -> None:
    assert "TransformationMatrix" in conf_content


def test_transformation_matrix_has_nine_floats(conf_content: str) -> None:
    for line in conf_content.splitlines():
        if "TransformationMatrix" in line and "Option" in line:
            # Extract the quoted value after TransformationMatrix
            parts = line.split('"')
            # parts: ['...Option...', 'TransformationMatrix', ' ', '0 1 0 1 0 0 0 0 1', '']
            matrix_str = parts[-2]
            values = matrix_str.strip().split()
            assert len(values) == 9, f"Expected 9 matrix values, got {len(values)}: {values}"
            for v in values:
                float(v)  # raises ValueError if not a valid float
            return
    pytest.fail("No TransformationMatrix Option line found")


def test_config_matches_waveshare_device(conf_content: str) -> None:
    assert "MatchProduct" in conf_content


def test_install_script_exists() -> None:
    script = Path(__file__).parent.parent / "scripts" / "install-touchscreen-cal.sh"
    assert script.exists(), f"Install script missing at {script}"


def test_install_script_is_executable() -> None:
    script = Path(__file__).parent.parent / "scripts" / "install-touchscreen-cal.sh"
    assert script.stat().st_mode & 0o111, "Install script is not executable"
