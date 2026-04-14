"""Tests for config loading."""
from __future__ import annotations

from shitbox.utils.config import load_config


def test_load_config_drivers_list(tmp_path):
    yaml_text = "drivers:\n  - Tony\n  - Smithy\n  - Nav\n"
    cfg_path = tmp_path / "c.yaml"
    cfg_path.write_text(yaml_text)
    cfg = load_config(cfg_path)
    assert cfg.drivers == ["Tony", "Smithy", "Nav"]
