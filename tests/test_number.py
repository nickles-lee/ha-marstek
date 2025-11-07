"""Tests for number entities."""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.marstek_local_api.const import (
    HA_CONTROL_MAX_POWER,
    HA_CONTROL_MIN_POWER,
)
from custom_components.marstek_local_api.number import MarstekTargetGridPowerNumber


async def test_number_entity_initialization(mock_coordinator, mock_config_entry):
    """Test number entity initialization."""
    number = MarstekTargetGridPowerNumber(mock_coordinator, mock_config_entry)
    
    assert number.native_min_value == HA_CONTROL_MIN_POWER
    assert number.native_max_value == HA_CONTROL_MAX_POWER
    assert number.native_step == 1
    assert number.native_value == 0  # Initial value


async def test_number_entity_set_value(mock_coordinator, mock_config_entry):
    """Test setting number entity value."""
    number = MarstekTargetGridPowerNumber(mock_coordinator, mock_config_entry)
    
    # Mock async_write_ha_state to avoid hass requirement
    with patch.object(number, 'async_write_ha_state'):
        # Set a new value
        await number.async_set_native_value(500.0)
    
    assert number.native_value == 500.0


async def test_number_entity_availability(mock_coordinator, mock_config_entry):
    """Test number entity availability."""
    number = MarstekTargetGridPowerNumber(mock_coordinator, mock_config_entry)
    
    # Should be available when coordinator has data
    assert number.available is True
    
    # Should be unavailable when coordinator has no data
    mock_coordinator.data = None
    assert number.available is False


async def test_number_entity_range_validation(mock_coordinator, mock_config_entry):
    """Test that number entity respects power range."""
    number = MarstekTargetGridPowerNumber(mock_coordinator, mock_config_entry)
    
    # Mock async_write_ha_state to avoid hass requirement
    with patch.object(number, 'async_write_ha_state'):
        # Test within range
        await number.async_set_native_value(1000.0)
        assert number.native_value == 1000.0
        
        # Test max value
        await number.async_set_native_value(HA_CONTROL_MAX_POWER)
        assert number.native_value == HA_CONTROL_MAX_POWER
        
        # Test min value (negative for discharge)
        await number.async_set_native_value(HA_CONTROL_MIN_POWER)
        assert number.native_value == HA_CONTROL_MIN_POWER


