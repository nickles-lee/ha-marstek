"""HA-Controlled mode coordinator for Marstek Local API.

HA-Controlled mode is NOT an official Marstek operating mode. It's a Home Assistant
construct that uses the undocumented Passive mode to give HA direct control over
battery charge/discharge power.

How it works:
- Monitors the "Target Grid Power" number entity for user/automation changes
- Periodically (using UPDATE_INTERVAL_MEDIUM), sends a Passive mode command with:
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

from homeassistant.core import HomeAssistant, Event
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers import entity_registry as er

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HA_CONTROL_COUNTDOWN,
    MODE_PASSIVE,
    MODE_VERIFY_RETRY_DELAY,
    UPDATE_INTERVAL_MEDIUM,
)
from .coordinator import MarstekDataUpdateCoordinator, MarstekMultiDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


class MarstekHAControlCoordinator:
    """Coordinator for HA-Controlled mode automation.
    
    This coordinator monitors the "Target Grid Power" number entities and
    periodically (using UPDATE_INTERVAL_MEDIUM) pushes Passive mode commands to maintain control.
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
        self._remove_state_listeners = []
        self._device_states: dict[str, dict[str, Any]] = {}
        self._is_multi_device = isinstance(coordinator, MarstekMultiDeviceCoordinator)

    async def async_start(self) -> None:
        """Start the HA control coordinator."""
        _LOGGER.warning("🚀 Starting HA Battery control coordinator for entry %s (multi-device: %s)", 
                       self.entry_id, self._is_multi_device)
        
        # Set up periodic updates using UPDATE_INTERVAL_MEDIUM (as backup to immediate state changes)
        update_interval = UPDATE_INTERVAL_MEDIUM * DEFAULT_SCAN_INTERVAL
        self._remove_interval = async_track_time_interval(
            self.hass,
            self._async_update_passive_mode,
            timedelta(seconds=update_interval),
        )
        _LOGGER.warning("📅 Periodic battery control update interval set to %d seconds (UPDATE_INTERVAL_MEDIUM)", update_interval)
        
        # Set up state change listeners for immediate updates
        self._setup_state_listeners()
        
        # Do an initial update
        _LOGGER.warning("🔄 Performing initial HA Battery control update")
        await self._async_update_passive_mode(None)
        _LOGGER.warning("✅ HA Battery control coordinator startup complete")

    async def async_stop(self) -> None:
        """Stop the HA control coordinator."""
        _LOGGER.info("Stopping HA Battery control coordinator for entry %s", self.entry_id)
        
        if self._remove_interval:
            self._remove_interval()
            self._remove_interval = None
        
        # Remove state listeners
        for remove_listener in self._remove_state_listeners:
            remove_listener()
        self._remove_state_listeners.clear()

    def _setup_state_listeners(self) -> None:
        """Set up state change listeners for Target Grid Power entities."""
        entity_reg = er.async_get(self.hass)
        
        if self._is_multi_device:
            # Multi-device: listen to each device's number entity
            _LOGGER.warning("🎧 Setting up state listeners for %d devices", len(self.coordinator.device_coordinators))
            for mac in self.coordinator.device_coordinators.keys():
                unique_id = f"{mac}_target_grid_power"
                entity_id = entity_reg.async_get_entity_id("number", DOMAIN, unique_id)
                
                if entity_id:
                    _LOGGER.warning("   👂 Listening to: %s (unique_id: %s)", entity_id, unique_id)
                    remove = async_track_state_change_event(
                        self.hass,
                        entity_id,
                        self._handle_state_change,
                    )
                    self._remove_state_listeners.append(remove)
                else:
                    _LOGGER.error("❌ Could not find entity for device %s (unique_id: %s)", mac, unique_id)
        else:
            # Single device: get the MAC and set up listener
            device_mac = None
            if "device" in self.coordinator.data:
                device_mac = self.coordinator.data["device"].get("ble_mac") or self.coordinator.data["device"].get("wifi_mac")
            
            if device_mac:
                unique_id = f"{device_mac}_target_grid_power"
                entity_id = entity_reg.async_get_entity_id("number", DOMAIN, unique_id)
                
                if entity_id:
                    _LOGGER.warning("🎧 Setting up state listener for single device: %s (unique_id: %s)", entity_id, unique_id)
                    remove = async_track_state_change_event(
                        self.hass,
                        entity_id,
                        self._handle_state_change,
                    )
                    self._remove_state_listeners.append(remove)
                else:
                    _LOGGER.error("❌ Could not find entity (unique_id: %s)", unique_id)
            else:
                _LOGGER.error("❌ Could not determine device MAC for state listener setup!")

    async def _handle_state_change(self, event: Event) -> None:
        """Handle Target Grid Power state changes."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        
        if not new_state or not old_state:
            return
        
        # Ignore if value hasn't actually changed
        if new_state.state == old_state.state:
            return
        
        _LOGGER.warning(
            "⚡ Target Grid Power changed on %s: %s → %s (triggering immediate update)",
            entity_id,
            old_state.state,
            new_state.state,
        )
        
        # Call the async update directly (we're already in an async context)
        await self._async_update_passive_mode(None)

    async def _async_update_passive_mode(self, _now=None) -> None:
        """Update passive mode for all controlled devices."""
        _LOGGER.warning("⏰ HA Battery control update triggered (periodic or immediate)")
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
            _LOGGER.debug("Could not determine device MAC for HA Battery control")
            return
        
        # Find entity by unique_id using entity registry
        entity_reg = er.async_get(self.hass)
        unique_id = f"{device_mac}_target_grid_power"
        entity_id = entity_reg.async_get_entity_id("number", DOMAIN, unique_id)
        
        if not entity_id:
            _LOGGER.debug("Number entity not found for unique_id %s", unique_id)
            return
        
        state = self.hass.states.get(entity_id)
        if not state:
            _LOGGER.debug("Number entity %s not found in state registry", entity_id)
            return
        
        try:
            target_power = int(float(state.state))
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid target power value: %s", state.state)
            return
        
        # Check current mode - only control if in Passive mode
        mode_data = self.coordinator.data.get("mode", {})
        current_mode = mode_data.get("mode")
        
        # Only maintain Passive mode when device is already in Passive mode
        if current_mode != MODE_PASSIVE:
            _LOGGER.debug("Device not in Passive mode (current: %s), skipping HA Battery control", current_mode)
            return
        
        # Set passive mode with target power (ensure integers)
        config = {
            "mode": MODE_PASSIVE,
            "passive_cfg": {
                "power": int(target_power),
                "cd_time": int(HA_CONTROL_COUNTDOWN),
            },
        }
        
        _LOGGER.info(
            "Sending Passive mode command: power=%dW, countdown=%ds (2 hours)",
            target_power,
            HA_CONTROL_COUNTDOWN,
        )
        
        try:
            # Import verification helper (lazy import to avoid circular dependency)
            from .services import _async_set_mode_with_verification
            
            # Use verification with fewer retries for background task
            success = await _async_set_mode_with_verification(
                self.coordinator, config, MODE_PASSIVE,
                max_retries=2,  # Fewer retries since we run periodically (UPDATE_INTERVAL_MEDIUM)
                verify_delay=1.5,  # Slightly faster for frequent updates
                retry_delay=MODE_VERIFY_RETRY_DELAY,
            )
            if success:
                _LOGGER.info("✓ HA Battery control updated successfully: power=%dW", target_power)
                self._device_states[device_mac] = {
                    "last_power": target_power,
                    "last_mode": MODE_PASSIVE,
                }
            else:
                _LOGGER.warning(
                    "Failed to verify HA-Controlled mode update, will retry next cycle"
                )
                # Don't raise error - will retry on next interval (UPDATE_INTERVAL_MEDIUM)
        except Exception as err:
            _LOGGER.error("Error updating HA Battery control: %s", err)

    async def _async_update_multi_device(self) -> None:
        """Update passive mode for multiple devices."""
        if not isinstance(self.coordinator, MarstekMultiDeviceCoordinator):
            return
        
        entity_reg = er.async_get(self.hass)
        
        for mac, device_coordinator in self.coordinator.device_coordinators.items():
            # Get the target power from the number entity for this device
            unique_id = f"{mac}_target_grid_power"
            entity_id = entity_reg.async_get_entity_id("number", DOMAIN, unique_id)
            
            if not entity_id:
                _LOGGER.debug("Number entity not found for device %s (unique_id: %s)", mac, unique_id)
                continue
            
            state = self.hass.states.get(entity_id)
            if not state:
                _LOGGER.debug("Number entity %s not found in state registry for device %s", entity_id, mac)
                continue
            
            try:
                target_power = int(float(state.state))
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid target power value for device %s: %s", mac, state.state)
                continue
            
            # Check current mode - only control if in Passive mode
            device_data = self.coordinator.get_device_data(mac)
            mode_data = device_data.get("mode", {})
            current_mode = mode_data.get("mode")
            
            # Only maintain Passive mode when device is already in Passive mode
            if current_mode != MODE_PASSIVE:
                _LOGGER.debug("Device %s not in Passive mode (current: %s), skipping HA Battery control", mac, current_mode)
                continue
            
            # Set passive mode with target power (ensure integers)
            config = {
                "mode": MODE_PASSIVE,
                "passive_cfg": {
                    "power": int(target_power),
                    "cd_time": int(HA_CONTROL_COUNTDOWN),
                },
            }
            
            _LOGGER.info(
                "Sending Passive mode command to device %s: power=%dW, countdown=%ds (2 hours)",
                mac,
                target_power,
                HA_CONTROL_COUNTDOWN,
            )
            
            try:
                # Import verification helper (lazy import to avoid circular dependency)
                from .services import _async_set_mode_with_verification
                
                # Use verification with fewer retries for background task
                success = await _async_set_mode_with_verification(
                    device_coordinator, config, MODE_PASSIVE,
                    max_retries=2,  # Fewer retries since we run periodically (UPDATE_INTERVAL_MEDIUM)
                    verify_delay=1.5,  # Slightly faster for frequent updates
                    retry_delay=MODE_VERIFY_RETRY_DELAY,
                )
                if success:
                    _LOGGER.info("✓ HA Battery control updated successfully for device %s: power=%dW", mac, target_power)
                    self._device_states[mac] = {
                        "last_power": target_power,
                        "last_mode": MODE_PASSIVE,
                    }
                else:
                    _LOGGER.warning(
                        "Failed to verify HA-Controlled mode update for device %s, will retry next cycle", mac
                    )
                    # Don't raise error - will retry on next interval (UPDATE_INTERVAL_MEDIUM)
            except Exception as err:
                _LOGGER.error("Error updating HA Battery control for device %s: %s", mac, err)

