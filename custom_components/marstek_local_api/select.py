"""Select platform for Marstek Local API."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import entity_registry as er

from .const import (
    DATA_COORDINATOR,
    DOMAIN,
    HA_CONTROL_COUNTDOWN,
    MAX_RETRIES,
    MODE_AI,
    MODE_AUTO,
    MODE_MANUAL,
    MODE_PASSIVE,
    OPERATING_MODES,
    RETRY_DELAY,
)
from .coordinator import MarstekDataUpdateCoordinator, MarstekMultiDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Marstek select based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities = []

    # Check if multi-device or single-device mode
    if isinstance(coordinator, MarstekMultiDeviceCoordinator):
        # Multi-device mode - create select entities for each device
        for mac in coordinator.get_device_macs():
            device_coordinator = coordinator.device_coordinators[mac]
            device_data = next(d for d in coordinator.devices if (d.get("ble_mac") or d.get("wifi_mac")) == mac)

            entities.append(
                MarstekMultiDeviceOperatingModeSelect(
                    coordinator=coordinator,
                    device_coordinator=device_coordinator,
                    device_mac=mac,
                    device_data=device_data,
                )
            )
    else:
        # Single device mode (legacy)
        entities.append(MarstekOperatingModeSelect(coordinator, entry))

    async_add_entities(entities)


class MarstekOperatingModeSelect(CoordinatorEntity, SelectEntity):
    """Representation of Marstek operating mode select."""

    _attr_options = OPERATING_MODES

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        device_mac = entry.data.get("ble_mac") or entry.data.get("wifi_mac")
        self._attr_unique_id = f"{device_mac}_operating_mode_select"
        self._attr_name = "Operating mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_mac)},
            name=f"Marstek {entry.data['device']}",
            manufacturer="Marstek",
            model=entry.data["device"],
            sw_version=str(entry.data.get("firmware", "Unknown")),
        )

    @property
    def current_option(self) -> str | None:
        """Return the current operating mode."""
        mode_data = self.coordinator.data.get("mode", {})
        return mode_data.get("mode")

    @property
    def available(self) -> bool:
        """Return if entity is available - keep available if we have data."""
        # Keep entity available if we have any data at all (prevents "unknown" on transient failures)
        return self.coordinator.data is not None and len(self.coordinator.data) > 0

    async def async_select_option(self, option: str) -> None:
        """Change the operating mode."""
        if option not in OPERATING_MODES:
            _LOGGER.error("Invalid operating mode: %s", option)
            return

        # Build config based on mode
        config = self._build_mode_config(option)
        
        _LOGGER.warning("📤 Setting operating mode to %s with config: %s", option, config)

        # Retry logic as per design document
        for attempt in range(MAX_RETRIES):
            try:
                success = await self.coordinator.api.set_es_mode(config)

                if success:
                    _LOGGER.info("✓ Successfully set operating mode to %s", option)
                    # Request immediate refresh
                    await self.coordinator.async_request_refresh()
                    return

                _LOGGER.warning(
                    "Device rejected mode change (attempt %d/%d)",
                    attempt + 1,
                    MAX_RETRIES,
                )

            except Exception as err:
                _LOGGER.error(
                    "Error setting mode (attempt %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    err,
                )

            # Wait before retry (except on last attempt)
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)

        _LOGGER.error("Failed to set operating mode after %d attempts", MAX_RETRIES)

    async def _refresh_mode_data(self) -> None:
        """Force a coordinator refresh so entities reflect the latest state."""
        try:
            await self.coordinator.async_refresh()
        except Exception as err:
            _LOGGER.warning("Failed to refresh data after mode change: %s", err)

    def _build_mode_config(self, mode: str) -> dict:
        """Build configuration for the selected mode."""
        if mode == MODE_AUTO:
            return {
                "mode": MODE_AUTO,
                "auto_cfg": {"enable": 1},
            }
        elif mode == MODE_AI:
            return {
                "mode": MODE_AI,
                "ai_cfg": {"enable": 1},
            }
        elif mode == MODE_MANUAL:
            # Default manual mode config (all week, no power limit)
            # Users can customize via service calls in the future
            return {
                "mode": MODE_MANUAL,
                "manual_cfg": {
                    "time_num": 0,
                    "start_time": "00:00",
                    "end_time": "23:59",
                    "week_set": 127,  # All days
                    "power": 0,
                    "enable": 1,
                },
            }
        elif mode == MODE_PASSIVE:
            # Get the current passive mode power from the number entity
            # Use relative reference: derive from this entity's unique_id
            target_power = 0  # Default to 0 if entity not found
            
            # This select entity has unique_id like "AA:BB:CC:DD:EE:FF_operating_mode_select"
            # The number entity has unique_id like "AA:BB:CC:DD:EE:FF_target_grid_power"
            # Extract the device prefix and construct the number entity's unique_id
            if self.unique_id and "_operating_mode_select" in self.unique_id:
                device_prefix = self.unique_id.replace("_operating_mode_select", "")
                number_unique_id = f"{device_prefix}_target_grid_power"
                
                entity_reg = er.async_get(self.hass)
                entity_id = entity_reg.async_get_entity_id("number", DOMAIN, number_unique_id)
                
                if entity_id:
                    state = self.hass.states.get(entity_id)
                    if state and state.state not in ('unknown', 'unavailable'):
                        try:
                            target_power = int(float(state.state))
                        except (ValueError, TypeError):
                            target_power = 0
            
            # Ensure integer value
            target_power = int(target_power)
            
            return {
                "mode": MODE_PASSIVE,
                "passive_cfg": {
                    "power": target_power,
                    "cd_time": int(HA_CONTROL_COUNTDOWN),  # 2 hour countdown
                },
            }

        return {}


class MarstekMultiDeviceOperatingModeSelect(CoordinatorEntity, SelectEntity):
    """Representation of Marstek operating mode select in multi-device mode."""

    _attr_options = OPERATING_MODES

    def __init__(
        self,
        coordinator: MarstekMultiDeviceCoordinator,
        device_coordinator: MarstekDataUpdateCoordinator,
        device_mac: str,
        device_data: dict,
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator)
        self.device_coordinator = device_coordinator
        self.device_mac = device_mac
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{device_mac}_operating_mode_select"
        self._attr_name = "Operating mode"

        # Extract last 4 chars of MAC for device name differentiation
        mac_suffix = device_mac.replace(":", "")[-4:]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_mac)},
            name=f"Marstek {device_data.get('device', 'Device')} {mac_suffix}",
            manufacturer="Marstek",
            model=device_data.get("device", "Unknown"),
            sw_version=str(device_data.get("firmware", "Unknown")),
        )

    @property
    def current_option(self) -> str | None:
        """Return the current operating mode."""
        device_data = self.coordinator.get_device_data(self.device_mac)
        mode_data = device_data.get("mode", {})
        return mode_data.get("mode")

    @property
    def available(self) -> bool:
        """Return if entity is available - keep available if we have data."""
        # Keep entity available if device has any data at all (prevents "unknown" on transient failures)
        device_data = self.coordinator.get_device_data(self.device_mac)
        return device_data is not None and len(device_data) > 0

    async def async_select_option(self, option: str) -> None:
        """Change the operating mode."""
        if option not in OPERATING_MODES:
            _LOGGER.error("Invalid operating mode: %s", option)
            return

        # Build config based on mode
        config = self._build_mode_config(option)
        
        _LOGGER.warning("📤 Setting operating mode to %s for device %s with config: %s", option, self.device_mac, config)

        # Retry logic as per design document
        for attempt in range(MAX_RETRIES):
            try:
                success = await self.device_coordinator.api.set_es_mode(config)

                if success:
                    _LOGGER.info("✓ Successfully set operating mode to %s for device %s", option, self.device_mac)
                    # Request immediate refresh
                    await self.coordinator.async_request_refresh()
                    return

                _LOGGER.warning(
                    "Device %s rejected mode change (attempt %d/%d)",
                    self.device_mac,
                    attempt + 1,
                    MAX_RETRIES,
                )

            except Exception as err:
                _LOGGER.error(
                    "Error setting mode for device %s (attempt %d/%d): %s",
                    self.device_mac,
                    attempt + 1,
                    MAX_RETRIES,
                    err,
                )

            # Wait before retry (except on last attempt)
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)

        _LOGGER.error("Failed to set operating mode for device %s after %d attempts", self.device_mac, MAX_RETRIES)

    async def _refresh_mode_data(self) -> None:
        """Force a refresh on the device and aggregate coordinators."""
        try:
            await self.device_coordinator.async_refresh()
        except Exception as err:
            _LOGGER.warning(
                "Failed to refresh device %s data after mode change: %s",
                self.device_mac,
                err,
            )

        try:
            await self.coordinator.async_refresh()
        except Exception as err:
            _LOGGER.warning(
                "Failed to refresh aggregate data after mode change for %s: %s",
                self.device_mac,
                err,
            )

    def _build_mode_config(self, mode: str) -> dict:
        """Build configuration for the selected mode."""
        if mode == MODE_AUTO:
            return {
                "mode": MODE_AUTO,
                "auto_cfg": {"enable": 1},
            }
        elif mode == MODE_AI:
            return {
                "mode": MODE_AI,
                "ai_cfg": {"enable": 1},
            }
        elif mode == MODE_MANUAL:
            # Default manual mode config (all week, no power limit)
            # Users can customize via service calls in the future
            return {
                "mode": MODE_MANUAL,
                "manual_cfg": {
                    "time_num": 0,
                    "start_time": "00:00",
                    "end_time": "23:59",
                    "week_set": 127,  # All days
                    "power": 0,
                    "enable": 1,
                },
            }
        elif mode == MODE_PASSIVE:
            # Get the current passive mode power from the number entity
            # Use relative reference: derive from this entity's unique_id
            target_power = 0  # Default to 0 if entity not found
            
            # This select entity has unique_id like "AA:BB:CC:DD:EE:FF_operating_mode_select"
            # The number entity has unique_id like "AA:BB:CC:DD:EE:FF_target_grid_power"
            # Extract the device prefix and construct the number entity's unique_id
            if self.unique_id and "_operating_mode_select" in self.unique_id:
                device_prefix = self.unique_id.replace("_operating_mode_select", "")
                number_unique_id = f"{device_prefix}_target_grid_power"
                
                entity_reg = er.async_get(self.hass)
                entity_id = entity_reg.async_get_entity_id("number", DOMAIN, number_unique_id)
                
                if entity_id:
                    state = self.hass.states.get(entity_id)
                    if state and state.state not in ('unknown', 'unavailable'):
                        try:
                            target_power = int(float(state.state))
                        except (ValueError, TypeError):
                            target_power = 0
            
            # Ensure integer value
            target_power = int(target_power)
            
            return {
                "mode": MODE_PASSIVE,
                "passive_cfg": {
                    "power": target_power,
                    "cd_time": int(HA_CONTROL_COUNTDOWN),  # 2 hour countdown
                },
            }

        return {}
