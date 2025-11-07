"""Tests for services."""
from __future__ import annotations

from datetime import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.marstek_local_api.const import (
    DATA_COORDINATOR,
    DOMAIN,
    MODE_MANUAL,
    MODE_PASSIVE,
)
from custom_components.marstek_local_api.services import (
    _get_coordinator_from_device_id,
    async_setup_services,
)


async def test_set_manual_schedule_service(mock_hass, mock_coordinator, mock_device_registry):
    """Test set_manual_schedule service."""
    # Setup
    mock_hass.data[DOMAIN] = {
        "test_entry_id": {DATA_COORDINATOR: mock_coordinator}
    }
    
    await async_setup_services(mock_hass)
    
    # Get the registered service handler
    call_args = mock_hass.services.async_register.call_args_list
    set_manual_handler = None
    for call in call_args:
        if call[0][1] == "set_manual_schedule":
            set_manual_handler = call[0][2]
            break
    
    assert set_manual_handler is not None
    
    # Create a mock service call
    service_call = Mock()
    service_call.data = {
        "device_id": "test_device_id",
        "time_num": 0,
        "start_time": time(8, 0),
        "end_time": time(20, 0),
        "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        "power": 100,
        "enabled": True,
    }
    
    # Call the service
    await set_manual_handler(service_call)
    
    # Verify API was called with correct config
    expected_config = {
        "mode": MODE_MANUAL,
        "manual_cfg": {
            "time_num": 0,
            "start_time": "08:00",
            "end_time": "20:00",
            "week_set": 127,  # All days
            "power": 100,
            "enable": 1,
        },
    }
    mock_coordinator.api.set_es_mode.assert_called_once_with(expected_config)


async def test_set_passive_mode_service(mock_hass, mock_coordinator, mock_device_registry):
    """Test set_passive_mode service."""
    # Setup
    mock_hass.data[DOMAIN] = {
        "test_entry_id": {DATA_COORDINATOR: mock_coordinator}
    }
    
    await async_setup_services(mock_hass)
    
    # Get the registered service handler
    call_args = mock_hass.services.async_register.call_args_list
    set_passive_handler = None
    for call in call_args:
        if call[0][1] == "set_passive_mode":
            set_passive_handler = call[0][2]
            break
    
    assert set_passive_handler is not None
    
    # Create a mock service call
    service_call = Mock()
    service_call.data = {
        "device_id": "test_device_id",
        "power": 500,
        "duration": 7200,
    }
    
    # Call the service
    await set_passive_handler(service_call)
    
    # Verify API was called with correct config
    expected_config = {
        "mode": MODE_PASSIVE,
        "passive_cfg": {
            "power": 500,
            "cd_time": 7200,
        },
    }
    mock_coordinator.api.set_es_mode.assert_called_once_with(expected_config)


async def test_set_manual_schedule_service_failure(mock_hass, mock_coordinator, mock_device_registry):
    """Test set_manual_schedule service with API failure."""
    # Setup
    mock_hass.data[DOMAIN] = {
        "test_entry_id": {DATA_COORDINATOR: mock_coordinator}
    }
    mock_coordinator.api.set_es_mode = AsyncMock(return_value=False)
    
    await async_setup_services(mock_hass)
    
    # Get the registered service handler
    call_args = mock_hass.services.async_register.call_args_list
    set_manual_handler = None
    for call in call_args:
        if call[0][1] == "set_manual_schedule":
            set_manual_handler = call[0][2]
            break
    
    # Create a mock service call
    service_call = Mock()
    service_call.data = {
        "device_id": "test_device_id",
        "time_num": 0,
        "start_time": time(8, 0),
        "end_time": time(20, 0),
        "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        "power": 100,
        "enabled": True,
    }
    
    # Should raise HomeAssistantError
    with pytest.raises(HomeAssistantError):
        await set_manual_handler(service_call)


async def test_get_coordinator_from_device_id(mock_hass, mock_coordinator, mock_device_registry):
    """Test helper function to get coordinator from device_id."""
    # Setup
    mock_hass.data[DOMAIN] = {
        "test_entry_id": {DATA_COORDINATOR: mock_coordinator}
    }
    
    coordinator, mac = _get_coordinator_from_device_id(mock_hass, "test_device_id")
    
    assert coordinator == mock_coordinator
    assert mac == "112233445566"


async def test_get_coordinator_from_device_id_not_found(mock_hass, mock_device_registry):
    """Test helper function with device not found."""
    # Setup with no coordinator
    mock_hass.data[DOMAIN] = {}
    
    with pytest.raises(HomeAssistantError, match="No coordinator found"):
        _get_coordinator_from_device_id(mock_hass, "test_device_id")


async def test_set_system_schedule_service(mock_hass, mock_coordinator, mock_api):
    """Test set_system_schedule service for multi-device setup."""
    from custom_components.marstek_local_api.coordinator import MarstekMultiDeviceCoordinator
    
    # Create a second mock API with mode tracking
    second_api = AsyncMock()
    second_current_mode = {"mode": "Auto"}
    
    async def second_get_es_mode():
        return {
            "mode": second_current_mode["mode"],
            "ongrid_power": 100,
            "offgrid_power": 0,
            "bat_soc": 80,
        }
    
    async def second_set_es_mode(config):
        if isinstance(config, dict) and "mode" in config:
            second_current_mode["mode"] = config["mode"]
        return True
    
    second_api.get_es_mode = AsyncMock(side_effect=second_get_es_mode)
    second_api.set_es_mode = AsyncMock(side_effect=second_set_es_mode)
    
    # Create a second coordinator
    second_coordinator = Mock()
    second_coordinator.api = second_api
    second_coordinator.async_request_refresh = AsyncMock()
    
    # Create a mock multi-device coordinator
    multi_coordinator = Mock(spec=MarstekMultiDeviceCoordinator)
    multi_coordinator.device_coordinators = {
        "112233445566": mock_coordinator,
        "AABBCCDDEEFF": second_coordinator,
    }
    multi_coordinator.async_request_refresh = AsyncMock()
    
    mock_hass.data[DOMAIN] = {
        "test_entry_id": {DATA_COORDINATOR: multi_coordinator}
    }
    
    await async_setup_services(mock_hass)
    
    # Get the registered service handler
    call_args = mock_hass.services.async_register.call_args_list
    set_system_handler = None
    for call in call_args:
        if call[0][1] == "set_system_schedule":
            set_system_handler = call[0][2]
            break
    
    assert set_system_handler is not None
    
    # Create a mock service call
    service_call = Mock()
    service_call.data = {
        "entry_id": "test_entry_id",
        "schedule": {
            "time_num": 0,
            "start_time": "08:00",
            "end_time": "20:00",
            "week_set": 127,
            "power": 100,
            "enable": 1,
        },
    }
    
    # Call the service
    await set_system_handler(service_call)
    
    # Verify API was called for both devices
    expected_config = {
        "mode": MODE_MANUAL,
        "manual_cfg": service_call.data["schedule"],
    }
    mock_coordinator.api.set_es_mode.assert_called_once_with(expected_config)
    second_coordinator.api.set_es_mode.assert_called_once_with(expected_config)
    multi_coordinator.async_request_refresh.assert_called_once()


