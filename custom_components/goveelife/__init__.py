"""Init for the Govee Life integration."""

from __future__ import annotations

import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICES,
    CONF_PARAMS,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_COORDINATORS,
    DOMAIN,
    FUNC_OPTION_UPDATES,
    SUPPORTED_PLATFORMS,
)
from .entities import (
    GoveeAPIUpdateCoordinator,
)
from .services import (
    async_registerService,
    async_service_SetPollInterval,
)
from .utils import (
    async_GoveeAPI_GetDeviceState,
    async_GoveeAPI_GETRequest,
)

_LOGGER: Final = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up cloud resource from the config entry."""
    _LOGGER.debug("Setting up config entry: %s", entry.entry_id)

    try:
        _LOGGER.debug("%s - async_setup_entry: Creating data store: %s.%s ", entry.entry_id, DOMAIN, entry.entry_id)
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN].setdefault(entry.entry_id, {})
        entry_data = hass.data[DOMAIN][entry.entry_id]
        entry_data[CONF_PARAMS] = entry.data
        entry_data[CONF_SCAN_INTERVAL] = None
    except Exception as e:
        _LOGGER.error(
            "%s - async_setup_entry: Creating data store failed: %s (%s.%s)",
            entry.entry_id,
            str(e),
            e.__class__.__module__,
            type(e).__name__,
        )
        return False

    try:
        _LOGGER.debug("%s - async_setup_entry: Receiving cloud devices..", entry.entry_id)
        api_devices = await async_GoveeAPI_GETRequest(hass, entry.entry_id, "user/devices")
        if api_devices is None:
            return False
        entry_data[CONF_DEVICES] = api_devices
    except Exception as e:
        _LOGGER.error(
            "%s - async_setup_entry: Receiving cloud devices failed: %s (%s.%s)",
            entry.entry_id,
            str(e),
            e.__class__.__module__,
            type(e).__name__,
        )
        return False

    try:
        _LOGGER.debug("%s - async_setup_entry: Reconciling stale devices in registry", entry.entry_id)
        api_device_ids = {d.get("device") for d in api_devices if d.get("device")}
        registry = dr.async_get(hass)
        for device_entry in dr.async_entries_for_config_entry(registry, entry.entry_id):
            for identifier in device_entry.identifiers:
                if identifier[0] == DOMAIN and identifier[1] not in api_device_ids:
                    _LOGGER.info(
                        "%s - async_setup_entry: Removing stale device from registry: %s",
                        entry.entry_id,
                        identifier[1],
                    )
                    registry.async_remove_device(device_entry.id)
                    break
    except Exception as e:
        _LOGGER.warning(
            "%s - async_setup_entry: Stale device reconciliation failed: %s (%s.%s)",
            entry.entry_id,
            str(e),
            e.__class__.__module__,
            type(e).__name__,
        )

    try:
        _LOGGER.debug("%s - async_setup_entry: Creating update coordinators per device..", entry.entry_id)
        entry_data.setdefault(CONF_COORDINATORS, {})
        for device_cfg in api_devices:
            await async_GoveeAPI_GetDeviceState(hass, entry.entry_id, device_cfg)
            coordinator = GoveeAPIUpdateCoordinator(hass, entry.entry_id, device_cfg)
            d = device_cfg.get("device")
            entry_data[CONF_COORDINATORS][d] = coordinator
    except Exception as e:
        _LOGGER.error(
            "%s - async_setup_entry: Creating update coordinators failed: %s (%s.%s)",
            entry.entry_id,
            str(e),
            e.__class__.__module__,
            type(e).__name__,
        )
        return False

    try:
        _LOGGER.debug(
            "%s - async_setup_entry: Register option updates listener: %s ", entry.entry_id, FUNC_OPTION_UPDATES
        )
        entry_data[FUNC_OPTION_UPDATES] = entry.add_update_listener(options_update_listener)
    except Exception as e:
        _LOGGER.error(
            "%s - async_setup_entry: Register option updates listener failed: %s (%s.%s)",
            entry.entry_id,
            str(e),
            e.__class__.__module__,
            type(e).__name__,
        )
        return False

    try:
        await hass.config_entries.async_forward_entry_setups(entry, SUPPORTED_PLATFORMS)
    except Exception as e:
        _LOGGER.error(
            "%s - async_setup_entry: Setup trigger for platform failed: %s (%s.%s)",
            entry.entry_id,
            str(e),
            e.__class__.__module__,
            type(e).__name__,
        )
        return False

    try:
        _LOGGER.debug("%s - async_setup_entry: register services", entry.entry_id)
        await async_registerService(hass, "set_poll_interval", async_service_SetPollInterval)
    except Exception as e:
        _LOGGER.error(
            "%s - async_setup_entry: register services failed: %s (%s.%s)",
            entry.entry_id,
            str(e),
            e.__class__.__module__,
            type(e).__name__,
        )
        return False

    _LOGGER.debug("%s - async_setup_entry: Completed", entry.entry_id)
    return True


async def options_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle options update."""
    _LOGGER.debug("Update options / reload config entry: %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        _LOGGER.debug("Unloading config entry: %s", entry.entry_id)

        # Unload all platforms at once using the modern HA API
        all_ok = await hass.config_entries.async_unload_platforms(entry, SUPPORTED_PLATFORMS)

        if all_ok:
            # Unload option updates listener
            _LOGGER.debug(
                "%s - async_unload_entry: Unload option updates listener: %s ", entry.entry_id, FUNC_OPTION_UPDATES
            )
            hass.data[DOMAIN][entry.entry_id][FUNC_OPTION_UPDATES]()

            # Remove data store
            _LOGGER.debug("%s - async_unload_entry: Remove data store: %s.%s ", entry.entry_id, DOMAIN, entry.entry_id)
            hass.data[DOMAIN].pop(entry.entry_id)

        return all_ok
    except Exception as e:
        _LOGGER.error(
            "%s - async_unload_entry: Unload device failed: %s (%s.%s)",
            entry.entry_id,
            str(e),
            e.__class__.__module__,
            type(e).__name__,
        )
        return False


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Allow removing a device from the UI if it is no longer returned by the Govee API.

    Returning True enables the Delete button on the device page.  We only
    permit deletion when the device is no longer present in the current API
    device list, preventing accidental removal of live devices.
    """
    try:
        entry_data = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {})
        api_devices = entry_data.get(CONF_DEVICES, [])
        api_device_ids = {d.get("device") for d in api_devices if d.get("device")}

        for identifier in device_entry.identifiers:
            if identifier[0] == DOMAIN:
                device_id = identifier[1]
                can_remove = device_id not in api_device_ids
                _LOGGER.debug(
                    "%s - async_remove_config_entry_device: device=%s can_remove=%s",
                    config_entry.entry_id,
                    device_id,
                    can_remove,
                )
                return can_remove

        # No goveelife identifier found — allow removal
        return True
    except Exception as e:
        _LOGGER.error(
            "%s - async_remove_config_entry_device: Failed: %s (%s.%s)",
            config_entry.entry_id,
            str(e),
            e.__class__.__module__,
            type(e).__name__,
        )
        return False
