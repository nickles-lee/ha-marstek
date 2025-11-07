"""Number platform for Marstek Local API."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_COORDINATOR,
    DOMAIN,
    HA_CONTROL_MAX_POWER,
    HA_CONTROL_MIN_POWER,
)
from .coordinator import MarstekDataUpdateCoordinator, MarstekMultiDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Marstek number entities based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities = []

    # Check if multi-device or single-device mode
    if isinstance(coordinator, MarstekMultiDeviceCoordinator):
        # Multi-device mode - create number entity for each device
        for mac in coordinator.get_device_macs():
            device_coordinator = coordinator.device_coordinators[mac]
            device_data = next(d for d in coordinator.devices if (d.get("ble_mac") or d.get("wifi_mac")) == mac)

            entities.append(
                MarstekMultiDeviceTargetGridPowerNumber(
                    coordinator=coordinator,
                    device_coordinator=device_coordinator,
                    device_mac=mac,
                    device_data=device_data,
                )
            )
    else:
        # Single device mode
        entities.append(MarstekTargetGridPowerNumber(coordinator, entry))

    async_add_entities(entities)


class MarstekTargetGridPowerNumber(CoordinatorEntity, NumberEntity):
    """Number entity for target grid power (HA-Controlled mode)."""

    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_min_value = HA_CONTROL_MIN_POWER
    _attr_native_max_value = HA_CONTROL_MAX_POWER
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:transmission-tower"

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        device_mac = entry.data.get("ble_mac") or entry.data.get("wifi_mac")
        self._attr_unique_id = f"{device_mac}_target_grid_power"
        self._attr_name = "Passive mode power"
        self._attr_entity_description = "Positive = discharge, negative = charge"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_mac)},
            name=f"Marstek {entry.data['device']}",
            manufacturer="Marstek",
            model=entry.data["device"],
            sw_version=str(entry.data.get("firmware", "Unknown")),
        )
        # Initialize with 0 (idle)
        self._attr_native_value = 0

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        """Set new target power value."""
        # Store as integer to ensure no decimal display
        self._attr_native_value = int(value)
        self.async_write_ha_state()
        _LOGGER.info("Target grid power set to %dW", int(value))

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Available if coordinator has data
        return self.coordinator.data is not None and len(self.coordinator.data) > 0


class MarstekMultiDeviceTargetGridPowerNumber(CoordinatorEntity, NumberEntity):
    """Number entity for target grid power in multi-device mode."""

    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_min_value = HA_CONTROL_MIN_POWER
    _attr_native_max_value = HA_CONTROL_MAX_POWER
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:transmission-tower"

    def __init__(
        self,
        coordinator: MarstekMultiDeviceCoordinator,
        device_coordinator: MarstekDataUpdateCoordinator,
        device_mac: str,
        device_data: dict,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.device_coordinator = device_coordinator
        self.device_mac = device_mac
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{device_mac}_target_grid_power"
        self._attr_name = "Passive mode power"
        self._attr_entity_description = "Positive = discharge, negative = charge"

        # Extract last 4 chars of MAC for device name differentiation
        mac_suffix = device_mac.replace(":", "")[-4:]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_mac)},
            name=f"Marstek {device_data.get('device', 'Device')} {mac_suffix}",
            manufacturer="Marstek",
            model=device_data.get("device", "Unknown"),
            sw_version=str(device_data.get("firmware", "Unknown")),
        )
        # Initialize with 0 (idle)
        self._attr_native_value = 0

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        """Set new target power value."""
        # Store as integer to ensure no decimal display
        self._attr_native_value = int(value)
        self.async_write_ha_state()
        _LOGGER.info("Target grid power set to %dW for device %s", int(value), self.device_mac)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Available if device has data
        device_data = self.coordinator.get_device_data(self.device_mac)
        return device_data is not None and len(device_data) > 0

