from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import (
    CONF_API_KEY,
    CONF_DEVICES,
    CONF_PARAMS,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    UnitOfTemperature,
)
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM

from custom_components.goveelife.const import CONF_COORDINATORS, DOMAIN
from custom_components.goveelife.entities import GoveeLifePlatformEntity
from custom_components.goveelife.sensor import GoveeLifeSensor

DEVICE_RESPONSES_DIR = Path(__file__).parent / "fixtures" / "device_responses"


def _load_device_fixture(fixture_file):
    return json.loads((DEVICE_RESPONSES_DIR / fixture_file).read_text())


def _create_sensor(device_cfg, instance, unit_system=METRIC_SYSTEM):
    hass = MagicMock()
    hass.config.units = unit_system
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    coordinator = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    hass.data = {
        DOMAIN: {
            entry.entry_id: {
                CONF_DEVICES: [device_cfg],
                CONF_COORDINATORS: {device_cfg["device"]: coordinator},
                CONF_PARAMS: {
                    CONF_API_KEY: "fake-api-key",
                    CONF_SCAN_INTERVAL: 60,
                    CONF_TIMEOUT: 10,
                },
            }
        }
    }
    capability = next(c for c in device_cfg["capabilities"] if c.get("instance") == instance)
    sensor = GoveeLifeSensor(hass, entry, coordinator, device_cfg, platform="sensor", cap=capability)
    sensor.entity_id = f"sensor.test_{instance.lower()}"
    return sensor


def test_state_is_not_shadowed_by_the_base_entity():
    """SensorEntity.state performs the unit conversion, so nothing may shadow it."""
    assert "state" not in GoveeLifePlatformEntity.__dict__
    assert "state" not in GoveeLifeSensor.__dict__
    assert GoveeLifeSensor.state is SensorEntity.state


def test_temperature_is_converted_to_the_configured_unit():
    """The API reports °F; with a metric unit system 72 °F must display as 22 °C."""
    device_cfg = _load_device_fixture("h7130_2024-07-10.json")
    sensor = _create_sensor(device_cfg, "sensorTemperature")

    with patch("custom_components.goveelife.sensor.GoveeAPI_GetCachedStateValue", return_value=72):
        assert sensor.native_unit_of_measurement == UnitOfTemperature.FAHRENHEIT
        assert sensor.native_value == 72
        assert sensor.unit_of_measurement == UnitOfTemperature.CELSIUS
        assert float(sensor.state) == pytest.approx(22.2, abs=0.5)


def test_temperature_is_not_converted_for_a_fahrenheit_system():
    """With °F configured the native value must be passed through unchanged."""
    device_cfg = _load_device_fixture("h7130_2024-07-10.json")
    sensor = _create_sensor(device_cfg, "sensorTemperature", unit_system=US_CUSTOMARY_SYSTEM)

    with patch("custom_components.goveelife.sensor.GoveeAPI_GetCachedStateValue", return_value=72):
        assert sensor.unit_of_measurement == UnitOfTemperature.FAHRENHEIT
        assert float(sensor.state) == pytest.approx(72)


def test_temperature_follows_the_unit_chosen_in_the_entity_settings():
    """The C/F/K dropdown stores a per-entity unit override, which must convert too."""
    device_cfg = _load_device_fixture("h7130_2024-07-10.json")
    sensor = _create_sensor(device_cfg, "sensorTemperature", unit_system=US_CUSTOMARY_SYSTEM)
    sensor._sensor_option_unit_of_measurement = UnitOfTemperature.CELSIUS

    with patch("custom_components.goveelife.sensor.GoveeAPI_GetCachedStateValue", return_value=72):
        assert sensor.unit_of_measurement == UnitOfTemperature.CELSIUS
        assert float(sensor.state) == pytest.approx(22.2, abs=0.5)


@pytest.mark.parametrize(
    ("cached_value", "expected"),
    [
        (72, 72),
        (71.6, 71.6),
        ("72", 72),
        ("71.6", 71.6),
        ({"currentTemperature": 72}, 72),
        (None, None),
        ("", None),
        ("unavailable", None),
    ],
)
def test_native_value_is_numeric_or_none(cached_value, expected):
    """A non-numeric native value makes SensorEntity.state raise, so normalize it."""
    device_cfg = _load_device_fixture("h7130_2024-07-10.json")
    sensor = _create_sensor(device_cfg, "sensorTemperature")

    with patch("custom_components.goveelife.sensor.GoveeAPI_GetCachedStateValue", return_value=cached_value):
        assert sensor.native_value == expected
        # reading the state must not raise, whatever the API returned
        if expected is None:
            assert sensor.state is None
        else:
            assert float(sensor.state) == pytest.approx((expected - 32) * 5 / 9, abs=0.5)
