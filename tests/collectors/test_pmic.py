"""Tests for PMICCollector — Pi 5 internal rail telemetry via vcgencmd."""

from unittest.mock import MagicMock, patch

from shitbox.collectors.pmic import PMICCollector, PMICRailReading


_VCGENCMD_SAMPLE = """\
3V7_WL_SW_A current(0)=0.00114980A
3V3_SYS_A current(1)=0.51914219A
1V8_SYS_A current(2)=0.27490430A
DDR_VDD2_A current(3)=0.36633398A
VDD_CORE_A current(7)=2.71789453A
HDMI_A current(22)=0.00585000A
3V7_WL_SW_V volt(8)=3.66093750V
3V3_SYS_V volt(9)=3.27734375V
1V8_SYS_V volt(10)=1.79296875V
DDR_VDD2_V volt(11)=1.10058594V
VDD_CORE_V volt(15)=0.85742188V
EXT5V_V volt(23)=5.07812500V
BATT_V volt(24)=0.00000000V
"""


def _make_config(enabled: bool = True) -> MagicMock:
    config = MagicMock()
    config.enabled = enabled
    config.sample_rate_hz = 1.0
    config.vcgencmd_path = "vcgencmd"
    return config


def test_parses_real_pmic_output() -> None:
    """Parser pairs _V and _A lines into one PMICRailReading per rail."""
    rails = PMICCollector._parse(_VCGENCMD_SAMPLE)

    by_rail = {r.rail: r for r in rails}

    # 3V3_SYS has both V and A
    assert by_rail["3V3_SYS"].voltage_v == 3.27734375
    assert abs(by_rail["3V3_SYS"].current_a - 0.51914219) < 1e-9

    # EXT5V is voltage-only (PMIC doesn't measure input current)
    assert by_rail["EXT5V"].voltage_v == 5.078125
    assert by_rail["EXT5V"].current_a is None

    # HDMI is current-only
    assert by_rail["HDMI"].current_a == 0.00585
    assert by_rail["HDMI"].voltage_v is None

    # VDD_CORE is the chunky one — confirm it parsed correctly
    assert by_rail["VDD_CORE"].voltage_v == 0.85742188
    assert by_rail["VDD_CORE"].current_a > 2.7


def test_parser_ignores_garbage_lines() -> None:
    """Non-matching lines (blank, non-PMIC vcgencmd stuff) are skipped silently."""
    output = (
        "\n"
        "Some unrelated header\n"
        "EXT5V_V volt(23)=5.07812500V\n"
        "garbage line that doesn't match the regex\n"
    )
    rails = PMICCollector._parse(output)
    assert len(rails) == 1
    assert rails[0].rail == "EXT5V"
    assert rails[0].voltage_v == 5.078125


def test_disabled_collector_does_not_shell_out() -> None:
    """When config.enabled=False the collector must not invoke subprocess."""
    config = _make_config(enabled=False)

    with patch("shitbox.collectors.pmic.subprocess") as mock_subproc, \
         patch("shitbox.collectors.pmic.shutil") as mock_shutil:
        collector = PMICCollector(config=config)
        collector.setup()
        result = collector.collect()

    mock_subproc.run.assert_not_called()
    mock_shutil.which.assert_not_called()
    assert result is None


def test_missing_vcgencmd_disables_gracefully() -> None:
    """If vcgencmd is not on PATH the collector logs once and stops trying."""
    config = _make_config(enabled=True)

    with patch("shitbox.collectors.pmic.shutil.which", return_value=None), \
         patch("shitbox.collectors.pmic.subprocess") as mock_subproc:
        collector = PMICCollector(config=config)
        collector.setup()  # must not raise
        result = collector.collect()

    mock_subproc.run.assert_not_called()
    assert result is None


def test_to_reading_lowercases_rail_for_sensor_id() -> None:
    """to_reading produces a Reading with the lowercase rail name as sensor_id."""
    config = _make_config(enabled=True)
    collector = PMICCollector(config=config)
    rail = PMICRailReading(rail="EXT5V", voltage_v=5.07, current_a=None)

    reading = collector.to_reading(rail)

    assert reading.sensor_id == "ext5v"
    assert reading.bus_voltage_v == 5.07
    assert reading.current_ma is None
