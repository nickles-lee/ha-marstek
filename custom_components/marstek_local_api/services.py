"""Service helpers for the Marstek Local API integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    DATA_COORDINATOR,
    DOMAIN,
    MODE_MANUAL,
    MODE_PASSIVE,
    MODE_VERIFY_DELAY,
    MODE_VERIFY_MAX_RETRIES,
    MODE_VERIFY_RETRY_DELAY,
    SERVICE_REQUEST_SYNC,
    SERVICE_SET_MANUAL_SCHEDULE,
    SERVICE_SET_PASSIVE_MODE,
    SERVICE_SET_SYSTEM_SCHEDULE,
)
from .coordinator import MarstekDataUpdateCoordinator, MarstekMultiDeviceCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_REQUEST_SYNC_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
    }
)

# Manual schedule schema for validation
MANUAL_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("time_num"): vol.All(int, vol.Range(min=0, max=9)),
        vol.Required("start_time"): cv.string,  # Format: "HH:MM"
        vol.Required("end_time"): cv.string,  # Format: "HH:MM"
        vol.Required("week_set"): vol.All(int, vol.Range(min=0, max=127)),
        vol.Required("power"): int,
        vol.Required("enable"): vol.In([0, 1]),
    }
)

SERVICE_SET_MANUAL_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("schedule"): MANUAL_SCHEDULE_SCHEMA,
    }
)

SERVICE_SET_SYSTEM_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("entry_id"): cv.string,
        vol.Required("schedule"): MANUAL_SCHEDULE_SCHEMA,
    }
)

SERVICE_SET_PASSIVE_MODE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("power"): int,
        vol.Required("countdown"): vol.All(int, vol.Range(min=0)),
    }
)


def _get_coordinator_from_device_id(hass: HomeAssistant, device_id: str) -> tuple[MarstekDataUpdateCoordinator | None, str | None]:
    """Get coordinator and MAC address from device_id."""
    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get(device_id)
    
    if not device_entry:
        raise HomeAssistantError(f"Device {device_id} not found")
    
    # Find the config entry for this device
    for entry_id in device_entry.config_entries:
        if entry_id not in hass.data.get(DOMAIN, {}):
            continue
            
        entry_data = hass.data[DOMAIN][entry_id]
        coordinator = entry_data.get(DATA_COORDINATOR)
        
        if not coordinator:
            continue
        
        # Extract MAC from device identifiers
        for identifier in device_entry.identifiers:
            if identifier[0] == DOMAIN:
                mac = identifier[1]
                
                # For multi-device coordinator, get the device coordinator
                if isinstance(coordinator, MarstekMultiDeviceCoordinator):
                    if mac in coordinator.device_coordinators:
                        return coordinator.device_coordinators[mac], mac
                else:
                    # Single device coordinator
                    return coordinator, mac
    
    raise HomeAssistantError(f"No coordinator found for device {device_id}")


async def _async_set_mode_with_verification(
    coordinator: MarstekDataUpdateCoordinator,
    config: dict,
    expected_mode: str,
    max_retries: int = MODE_VERIFY_MAX_RETRIES,
    verify_delay: float = MODE_VERIFY_DELAY,
    retry_delay: float = MODE_VERIFY_RETRY_DELAY,
) -> bool:
    """Set ES mode and verify battery actually changed.
    
    UDP can drop packets, so we verify the battery actually changed state
    after sending the command. Retries if verification fails.
    
    Args:
        coordinator: Device coordinator with API client
        config: ES.SetMode configuration dict
        expected_mode: Expected mode after change ("Manual", "Passive", etc)
        max_retries: Maximum attempts before giving up (default from const)
        verify_delay: Seconds to wait after command before verification (default from const)
        retry_delay: Seconds to wait between retries (default from const)
    
    Returns:
        True if mode verified, False if all retries exhausted
    """
    for attempt in range(1, max_retries + 1):
        # Send command
        success = await coordinator.api.set_es_mode(config)
        
        if not success:
            _LOGGER.warning("Command failed (attempt %d/%d)", attempt, max_retries)
            if attempt < max_retries:
                await asyncio.sleep(retry_delay)
            continue
        
        # Wait for battery to process
        await asyncio.sleep(verify_delay)
        
        # Verify actual mode
        try:
            mode_data = await coordinator.api.get_es_mode()
            if mode_data and mode_data.get("mode") == expected_mode:
                _LOGGER.debug("Mode verified as %s (attempt %d)", expected_mode, attempt)
                return True
            else:
                actual_mode = mode_data.get("mode") if mode_data else "unknown"
                _LOGGER.warning(
                    "Mode verification failed: expected=%s, actual=%s (attempt %d/%d)",
                    expected_mode, actual_mode, attempt, max_retries
                )
        except Exception as err:
            _LOGGER.warning("Error verifying mode (attempt %d/%d): %s", attempt, max_retries, err)
        
        # Retry if not last attempt
        if attempt < max_retries:
            await asyncio.sleep(retry_delay)
    
    return False


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration level services."""

    if hass.services.has_service(DOMAIN, SERVICE_REQUEST_SYNC):
        return

    async def _async_request_sync(call: ServiceCall) -> None:
        """Trigger an on-demand refresh across configured coordinators."""
        entry_id: str | None = call.data.get("entry_id")
        domain_data = hass.data.get(DOMAIN)

        if not domain_data:
            _LOGGER.debug("Request sync skipped - integration has no active entries")
            return

        if entry_id:
            entry_payload = domain_data.get(entry_id)
            if not entry_payload:
                _LOGGER.warning(
                    "request_data_sync service received unknown entry_id: %s",
                    entry_id,
                )
                return
            await _async_refresh_entry(entry_id, entry_payload)
            return

        for current_entry_id, entry_payload in domain_data.items():
            await _async_refresh_entry(current_entry_id, entry_payload)

    async def _async_set_manual_schedule(call: ServiceCall) -> None:
        """Set Manual mode schedule for a device."""
        device_id = call.data["device_id"]
        schedule = call.data["schedule"]
        
        coordinator, mac = _get_coordinator_from_device_id(hass, device_id)
        if not coordinator:
            raise HomeAssistantError(f"Could not find coordinator for device {device_id}")
        
        # Build ES.SetMode config
        config = {
            "mode": MODE_MANUAL,
            "manual_cfg": schedule,
        }
        
        # Use verification to ensure command succeeded despite UDP reliability issues
        success = await _async_set_mode_with_verification(
            coordinator, config, MODE_MANUAL
        )
        if not success:
            raise HomeAssistantError(
                f"Failed to set manual schedule for device {mac} after verification retries"
            )
        
        _LOGGER.info("Successfully set manual schedule for device %s", mac)
        await coordinator.async_request_refresh()
    
    async def _async_set_system_schedule(call: ServiceCall) -> None:
        """Set Manual mode schedule for all devices in a system."""
        entry_id = call.data["entry_id"]
        schedule = call.data["schedule"]
        
        if entry_id not in hass.data.get(DOMAIN, {}):
            raise HomeAssistantError(f"Config entry {entry_id} not found")
        
        coordinator = hass.data[DOMAIN][entry_id].get(DATA_COORDINATOR)
        if not isinstance(coordinator, MarstekMultiDeviceCoordinator):
            raise HomeAssistantError("Config entry is not a multi-device system")
        
        # Build ES.SetMode config
        config = {
            "mode": MODE_MANUAL,
            "manual_cfg": schedule,
        }
        
        failed_devices = []
        for mac, device_coordinator in coordinator.device_coordinators.items():
            try:
                # Use verification to ensure command succeeded despite UDP reliability issues
                success = await _async_set_mode_with_verification(
                    device_coordinator, config, MODE_MANUAL
                )
                if not success:
                    failed_devices.append(mac)
                    _LOGGER.error("Failed to verify manual schedule for device %s", mac)
            except Exception as err:
                failed_devices.append(mac)
                _LOGGER.error("Error setting schedule for device %s: %s", mac, err)
        
        if failed_devices:
            raise HomeAssistantError(f"Failed to set schedule for devices: {', '.join(failed_devices)}")
        
        _LOGGER.info("Successfully set system schedule for %d devices", len(coordinator.device_coordinators))
        await coordinator.async_request_refresh()
    
    async def _async_set_passive_mode(call: ServiceCall) -> None:
        """Set Passive mode with custom power and countdown."""
        device_id = call.data["device_id"]
        power = call.data["power"]
        countdown = call.data["countdown"]
        
        coordinator, mac = _get_coordinator_from_device_id(hass, device_id)
        if not coordinator:
            raise HomeAssistantError(f"Could not find coordinator for device {device_id}")
        
        # Build ES.SetMode config for Passive mode
        config = {
            "mode": MODE_PASSIVE,
            "passive_cfg": {
                "power": power,
                "cd_time": countdown,
            },
        }
        
        # Use verification to ensure command succeeded despite UDP reliability issues
        success = await _async_set_mode_with_verification(
            coordinator, config, MODE_PASSIVE
        )
        if not success:
            raise HomeAssistantError(
                f"Failed to set passive mode for device {mac} after verification retries"
            )
        
        _LOGGER.info("Successfully set passive mode for device %s (power=%dW, countdown=%ds)", mac, power, countdown)
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_REQUEST_SYNC,
        _async_request_sync,
        schema=SERVICE_REQUEST_SYNC_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_MANUAL_SCHEDULE,
        _async_set_manual_schedule,
        schema=SERVICE_SET_MANUAL_SCHEDULE_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SYSTEM_SCHEDULE,
        _async_set_system_schedule,
        schema=SERVICE_SET_SYSTEM_SCHEDULE_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PASSIVE_MODE,
        _async_set_passive_mode,
        schema=SERVICE_SET_PASSIVE_MODE_SCHEMA,
    )

    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_REQUEST_SYNC)
    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_SET_MANUAL_SCHEDULE)
    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_SET_SYSTEM_SCHEDULE)
    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_SET_PASSIVE_MODE)


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unregister integration level services."""
    services_to_remove = [
        SERVICE_REQUEST_SYNC,
        SERVICE_SET_MANUAL_SCHEDULE,
        SERVICE_SET_SYSTEM_SCHEDULE,
        SERVICE_SET_PASSIVE_MODE,
    ]
    
    for service in services_to_remove:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
            _LOGGER.debug("Unregistered service %s.%s", DOMAIN, service)


async def _async_refresh_entry(entry_id: str, payload: dict) -> None:
    """Refresh a single config entry."""
    coordinator = payload.get(DATA_COORDINATOR)
    if coordinator is None:
        _LOGGER.debug("No coordinator stored for entry %s", entry_id)
        return

    if isinstance(coordinator, MarstekMultiDeviceCoordinator):
        _LOGGER.debug("Requesting multi-device sync for entry %s", entry_id)
        await coordinator.async_request_refresh()
        for mac, device_coordinator in coordinator.device_coordinators.items():
            if isinstance(device_coordinator, MarstekDataUpdateCoordinator):
                await device_coordinator.async_request_refresh()
                _LOGGER.debug("Requested device-level sync for %s (%s)", mac, entry_id)
    elif isinstance(coordinator, MarstekDataUpdateCoordinator):
        _LOGGER.debug("Requesting single-device sync for entry %s", entry_id)
        await coordinator.async_request_refresh()
    else:
        _LOGGER.debug(
            "Coordinator type %s not recognised for entry %s",
            type(coordinator),
            entry_id,
        )
