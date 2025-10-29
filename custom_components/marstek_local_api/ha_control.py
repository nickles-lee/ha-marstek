"""HA-Controlled mode coordinator for Marstek Local API.

HA-Controlled mode is NOT an official Marstek operating mode. It's a Home Assistant
construct that uses the undocumented Passive mode to give HA direct control over
battery charge/discharge power.

How it works:
- Monitors the "Target Grid Power" number entity for user/automation changes
- Every 2 minutes, sends a Passive mode command with:
  * Current target power from the number entity
  * 2-hour countdown timer
- The long countdown ensures the battery effectively always follows HA's target power
- If HA crashes or loses connection, battery continues last command until countdown expires
- If user manually changes mode away from Passive, HA control automatically pauses

This enables sophisticated automations like dynamic pricing response, solar following,
and custom load management strategies.
"""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    HA_CONTROL_COUNTDOWN,
    HA_CONTROL_UPDATE_INTERVAL,
    MODE_PASSIVE,
    MODE_VERIFY_DELAY,
    MODE_VERIFY_RETRY_DELAY,
)
from .coordinator import MarstekDataUpdateCoordinator, MarstekMultiDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


class MarstekHAControlCoordinator:
    """Coordinator for HA-Controlled mode automation.
    
    This coordinator monitors the "Target Grid Power" number entities and
    periodically (every 2 minutes) pushes Passive mode commands to maintain control.
    The long countdown (2 hours) ensures the battery effectively always follows HA's
    target power, even if HA temporarily loses connection to the device.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        coordinator: MarstekDataUpdateCoordinator | MarstekMultiDeviceCoordinator,
    ) -> None:
        """Initialize the HA control coordinator."""
        self.hass = hass
        self.entry_id = entry_id
        self.coordinator = coordinator
        self._remove_interval = None
        self._device_states: dict[str, dict[str, Any]] = {}
        self._is_multi_device = isinstance(coordinator, MarstekMultiDeviceCoordinator)

    async def async_start(self) -> None:
        """Start the HA control coordinator."""
        _LOGGER.info("Starting HA-Controlled mode coordinator for entry %s", self.entry_id)
        
        # Set up periodic updates
        self._remove_interval = async_track_time_interval(
            self.hass,
            self._async_update_passive_mode,
            timedelta(seconds=HA_CONTROL_UPDATE_INTERVAL),
        )
        
        # Do an initial update
        await self._async_update_passive_mode(None)

    async def async_stop(self) -> None:
        """Stop the HA control coordinator."""
        _LOGGER.info("Stopping HA-Controlled mode coordinator for entry %s", self.entry_id)
        
        if self._remove_interval:
            self._remove_interval()
            self._remove_interval = None

    async def _async_update_passive_mode(self, _now=None) -> None:
        """Update passive mode for all controlled devices."""
        if self._is_multi_device:
            await self._async_update_multi_device()
        else:
            await self._async_update_single_device()

    async def _async_update_single_device(self) -> None:
        """Update passive mode for a single device."""
        # Get the target power from the number entity
        device_mac = None
        for key in self.coordinator.data.keys():
            if "device" in self.coordinator.data:
                device_mac = self.coordinator.data["device"].get("ble_mac") or self.coordinator.data["device"].get("wifi_mac")
                break
        
        if not device_mac:
            _LOGGER.debug("Could not determine device MAC for HA control")
            return
        
        entity_id = f"number.{DOMAIN}_{device_mac}_target_grid_power".replace(":", "_").lower()
        state = self.hass.states.get(entity_id)
        
        if not state:
            _LOGGER.debug("Number entity %s not found", entity_id)
            return
        
        try:
            target_power = int(float(state.state))
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid target power value: %s", state.state)
            return
        
        # Check if mode was manually changed
        mode_data = self.coordinator.data.get("mode", {})
        current_mode = mode_data.get("mode")
        
        # If user manually changed mode away from Passive, stop HA control
        if device_mac in self._device_states:
            if self._device_states[device_mac].get("last_mode") == MODE_PASSIVE and current_mode != MODE_PASSIVE:
                _LOGGER.info("Device mode manually changed from Passive, pausing HA control")
                return
        
        # Set passive mode with target power
        config = {
            "mode": MODE_PASSIVE,
            "passive_cfg": {
                "power": target_power,
                "cd_time": HA_CONTROL_COUNTDOWN,
            },
        }
        
        try:
            # Import verification helper (lazy import to avoid circular dependency)
            from .services import _async_set_mode_with_verification
            
            # Use verification with fewer retries for background task
            success = await _async_set_mode_with_verification(
                self.coordinator, config, MODE_PASSIVE,
                max_retries=2,  # Fewer retries since we run every 2 minutes
                verify_delay=1.5,  # Slightly faster for frequent updates
                retry_delay=MODE_VERIFY_RETRY_DELAY,
            )
            if success:
                _LOGGER.debug("Updated HA-Controlled mode: power=%dW", target_power)
                self._device_states[device_mac] = {
                    "last_power": target_power,
                    "last_mode": MODE_PASSIVE,
                }
            else:
                _LOGGER.warning(
                    "Failed to verify HA-Controlled mode update, will retry next cycle"
                )
                # Don't raise error - will retry on next interval (2 minutes)
        except Exception as err:
            _LOGGER.error("Error updating HA-Controlled mode: %s", err)

    async def _async_update_multi_device(self) -> None:
        """Update passive mode for multiple devices."""
        if not isinstance(self.coordinator, MarstekMultiDeviceCoordinator):
            return
        
        for mac, device_coordinator in self.coordinator.device_coordinators.items():
            # Get the target power from the number entity
            entity_id = f"number.{DOMAIN}_{mac}_target_grid_power".replace(":", "_").lower()
            state = self.hass.states.get(entity_id)
            
            if not state:
                _LOGGER.debug("Number entity %s not found for device %s", entity_id, mac)
                continue
            
            try:
                target_power = int(float(state.state))
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid target power value for device %s: %s", mac, state.state)
                continue
            
            # Check if mode was manually changed
            device_data = self.coordinator.get_device_data(mac)
            mode_data = device_data.get("mode", {})
            current_mode = mode_data.get("mode")
            
            # If user manually changed mode away from Passive, stop HA control for this device
            if mac in self._device_states:
                if self._device_states[mac].get("last_mode") == MODE_PASSIVE and current_mode != MODE_PASSIVE:
                    _LOGGER.info("Device %s mode manually changed from Passive, pausing HA control", mac)
                    continue
            
            # Set passive mode with target power
            config = {
                "mode": MODE_PASSIVE,
                "passive_cfg": {
                    "power": target_power,
                    "cd_time": HA_CONTROL_COUNTDOWN,
                },
            }
            
            try:
                # Import verification helper (lazy import to avoid circular dependency)
                from .services import _async_set_mode_with_verification
                
                # Use verification with fewer retries for background task
                success = await _async_set_mode_with_verification(
                    device_coordinator, config, MODE_PASSIVE,
                    max_retries=2,  # Fewer retries since we run every 2 minutes
                    verify_delay=1.5,  # Slightly faster for frequent updates
                    retry_delay=MODE_VERIFY_RETRY_DELAY,
                )
                if success:
                    _LOGGER.debug("Updated HA-Controlled mode for device %s: power=%dW", mac, target_power)
                    self._device_states[mac] = {
                        "last_power": target_power,
                        "last_mode": MODE_PASSIVE,
                    }
                else:
                    _LOGGER.warning(
                        "Failed to verify HA-Controlled mode update for device %s, will retry next cycle", mac
                    )
                    # Don't raise error - will retry on next interval (2 minutes)
            except Exception as err:
                _LOGGER.error("Error updating HA-Controlled mode for device %s: %s", mac, err)

