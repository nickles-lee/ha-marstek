"""Tests for mode verification logic."""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.marstek_local_api.services import _async_set_mode_with_verification


async def test_set_mode_with_verification_success(mock_coordinator):
    """Test successful mode verification on first attempt."""
    mock_coordinator.api.set_es_mode = AsyncMock(return_value=True)
    mock_coordinator.api.get_es_mode = AsyncMock(
        return_value={"mode": "Passive"}
    )
    
    success = await _async_set_mode_with_verification(
        mock_coordinator,
        {"mode": "Passive", "passive_cfg": {"power": 100, "cd_time": 300}},
        "Passive",
    )
    
    assert success is True
    assert mock_coordinator.api.set_es_mode.call_count == 1
    assert mock_coordinator.api.get_es_mode.call_count == 1


async def test_set_mode_with_verification_retry_success(mock_coordinator):
    """Test mode verification succeeds on retry."""
    mock_coordinator.api.set_es_mode = AsyncMock(return_value=True)
    # First verification fails, second succeeds
    mock_coordinator.api.get_es_mode = AsyncMock(
        side_effect=[
            {"mode": "Auto"},  # Wrong mode on first check
            {"mode": "Passive"},  # Correct on second check
        ]
    )
    
    success = await _async_set_mode_with_verification(
        mock_coordinator,
        {"mode": "Passive", "passive_cfg": {"power": 100, "cd_time": 300}},
        "Passive",
        max_retries=3,
        verify_delay=0.1,  # Speed up test
        retry_delay=0.1,
    )
    
    assert success is True
    assert mock_coordinator.api.set_es_mode.call_count == 2
    assert mock_coordinator.api.get_es_mode.call_count == 2


async def test_set_mode_with_verification_failure(mock_coordinator):
    """Test mode verification fails after all retries."""
    mock_coordinator.api.set_es_mode = AsyncMock(return_value=True)
    # Always returns wrong mode
    mock_coordinator.api.get_es_mode = AsyncMock(
        return_value={"mode": "Auto"}
    )
    
    success = await _async_set_mode_with_verification(
        mock_coordinator,
        {"mode": "Passive", "passive_cfg": {"power": 100, "cd_time": 300}},
        "Passive",
        max_retries=3,
        verify_delay=0.1,  # Speed up test
        retry_delay=0.1,
    )
    
    assert success is False
    assert mock_coordinator.api.set_es_mode.call_count == 3
    assert mock_coordinator.api.get_es_mode.call_count == 3


async def test_set_mode_with_verification_handles_exceptions(mock_coordinator):
    """Test verification handles get_es_mode exceptions gracefully."""
    mock_coordinator.api.set_es_mode = AsyncMock(return_value=True)
    # First call raises exception, second succeeds
    mock_coordinator.api.get_es_mode = AsyncMock(
        side_effect=[
            Exception("UDP timeout"),
            {"mode": "Passive"},
        ]
    )
    
    success = await _async_set_mode_with_verification(
        mock_coordinator,
        {"mode": "Passive", "passive_cfg": {"power": 100, "cd_time": 300}},
        "Passive",
        max_retries=3,
        verify_delay=0.1,  # Speed up test
        retry_delay=0.1,
    )
    
    assert success is True
    assert mock_coordinator.api.set_es_mode.call_count == 2
    assert mock_coordinator.api.get_es_mode.call_count == 2


async def test_set_mode_with_verification_command_failure(mock_coordinator):
    """Test verification when set_es_mode initially fails."""
    # First command fails, second succeeds
    mock_coordinator.api.set_es_mode = AsyncMock(
        side_effect=[False, True]
    )
    mock_coordinator.api.get_es_mode = AsyncMock(
        return_value={"mode": "Passive"}
    )
    
    success = await _async_set_mode_with_verification(
        mock_coordinator,
        {"mode": "Passive", "passive_cfg": {"power": 100, "cd_time": 300}},
        "Passive",
        max_retries=3,
        verify_delay=0.1,  # Speed up test
        retry_delay=0.1,
    )
    
    assert success is True
    assert mock_coordinator.api.set_es_mode.call_count == 2
    assert mock_coordinator.api.get_es_mode.call_count == 1


async def test_set_mode_with_verification_none_mode_data(mock_coordinator):
    """Test verification when get_es_mode returns None."""
    mock_coordinator.api.set_es_mode = AsyncMock(return_value=True)
    # First returns None, second returns correct data
    mock_coordinator.api.get_es_mode = AsyncMock(
        side_effect=[None, {"mode": "Passive"}]
    )
    
    success = await _async_set_mode_with_verification(
        mock_coordinator,
        {"mode": "Passive", "passive_cfg": {"power": 100, "cd_time": 300}},
        "Passive",
        max_retries=3,
        verify_delay=0.1,  # Speed up test
        retry_delay=0.1,
    )
    
    assert success is True
    assert mock_coordinator.api.set_es_mode.call_count == 2
    assert mock_coordinator.api.get_es_mode.call_count == 2


async def test_set_mode_with_verification_manual_mode(mock_coordinator):
    """Test verification with Manual mode."""
    mock_coordinator.api.set_es_mode = AsyncMock(return_value=True)
    mock_coordinator.api.get_es_mode = AsyncMock(
        return_value={"mode": "Manual"}
    )
    
    success = await _async_set_mode_with_verification(
        mock_coordinator,
        {
            "mode": "Manual",
            "manual_cfg": {
                "time_num": 0,
                "start_time": "08:00",
                "end_time": "20:00",
                "week_set": 127,
                "power": 200,
                "enable": 1,
            }
        },
        "Manual",
    )
    
    assert success is True
    assert mock_coordinator.api.set_es_mode.call_count == 1
    assert mock_coordinator.api.get_es_mode.call_count == 1


async def test_set_mode_with_verification_custom_retries(mock_coordinator):
    """Test verification with custom retry settings."""
    mock_coordinator.api.set_es_mode = AsyncMock(return_value=True)
    # Always returns wrong mode
    mock_coordinator.api.get_es_mode = AsyncMock(
        return_value={"mode": "Auto"}
    )
    
    success = await _async_set_mode_with_verification(
        mock_coordinator,
        {"mode": "Passive", "passive_cfg": {"power": 100, "cd_time": 300}},
        "Passive",
        max_retries=2,  # Only 2 retries
        verify_delay=0.05,
        retry_delay=0.05,
    )
    
    assert success is False
    assert mock_coordinator.api.set_es_mode.call_count == 2  # Should be 2, not 3
    assert mock_coordinator.api.get_es_mode.call_count == 2


