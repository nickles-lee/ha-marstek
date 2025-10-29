# Testing Guide for Marstek Control Features

This guide explains how to test all the new control features added to the Marstek Local API integration.

## Prerequisites

- Marstek Venus A/C/D/E device with Local API enabled
- Home Assistant with the integration installed
- Device discovered and configured in HA

## 1. Integration Tests (Automated)

Run the standalone test script to verify all control functionality:

```bash
cd test
python3 test_discovery.py
```

This will:
1. Discover all Marstek devices on your network
2. Test all read operations (sensors)
3. Test Passive mode control (100W for 5 minutes)
4. Test Manual mode with schedule configuration
5. Restore original operating mode
6. Print detailed results for each test

**Expected Output:**
- ✅ Success indicators for each control command
- Mode verification after each change
- No timeout errors or API failures

## 2. Unit Tests (Pytest)

Run the pytest suite to test services, number entities, and HA control:

```bash
# Install test dependencies (first time only)
pip install -r tests/requirements.txt

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=custom_components.marstek_local_api --cov-report=html
```

**Expected Results:**
- All tests pass
- Coverage > 80% for new code

## 3. Manual Testing in Home Assistant

### Test 1: Passive Mode Service

1. Go to **Developer Tools → Services**
2. Select service: `marstek_local_api.set_passive_mode`
3. Fill in the parameters:
   ```yaml
   device_id: <your-device-id>
   power: 500
   countdown: 3600
   ```
4. Click **Call Service**
5. Check the "Operating mode" sensor - should show "Passive"
6. Check battery power sensor - should show ~500W charging

### Test 2: Manual Mode Schedule

1. Go to **Developer Tools → Services**
2. Select service: `marstek_local_api.set_manual_schedule`
3. Fill in the parameters:
   ```yaml
   device_id: <your-device-id>
   schedule:
     time_num: 0
     start_time: "08:00"
     end_time: "20:00"
     week_set: 127
     power: 200
     enable: 1
   ```
4. Click **Call Service**
5. Check the "Operating mode" sensor - should show "Manual"
6. The schedule is now active for time slot 0

### Test 3: System-Wide Schedule (Multi-Device Only)

If you have multiple batteries configured as a system:

1. Go to **Developer Tools → Services**
2. Select service: `marstek_local_api.set_system_schedule`
3. Fill in the parameters:
   ```yaml
   entry_id: <your-config-entry-id>
   schedule:
     time_num: 0
     start_time: "22:00"
     end_time: "06:00"
     week_set: 127
     power: 1000
     enable: 1
   ```
4. Click **Call Service**
5. Verify all batteries in the system changed to Manual mode
6. Check that all batteries show the same schedule active

### Test 4: HA-Controlled Mode

1. Go to **Settings → Devices & Services → Marstek Local API**
2. Click **Configure** on your integration
3. Enable **"HA-Controlled Mode"** (if available in options)
4. Restart the integration
5. Find the new entity: `number.<device>_target_grid_power`
6. Set the value to `800` (charge at 800W)
7. Wait 2-3 seconds
8. Check that:
   - Operating mode changed to "Passive"
   - Battery power is approximately 800W
9. Change the number to `-500` (discharge at 500W)
10. Verify battery power changes to approximately -500W

### Test 5: HA-Controlled Mode with Automation

Create a simple automation to test dynamic control:

```yaml
automation:
  - alias: "Test: Battery Charge Schedule"
    trigger:
      - platform: time
        at: "20:00:00"
    action:
      - service: number.set_value
        target:
          entity_id: number.marstek_venuse_target_grid_power
        data:
          value: 2000
  
  - alias: "Test: Battery Idle Morning"
    trigger:
      - platform: time
        at: "08:00:00"
    action:
      - service: number.set_value
        target:
          entity_id: number.marstek_venuse_target_grid_power
        data:
          value: 0
```

Test by:
1. Manually triggering the automation
2. Verifying the number entity updates
3. Confirming battery power responds accordingly

### Test: Verification Retry Logic

To test that verification handles UDP packet loss correctly:

1. Monitor Home Assistant logs with debug logging enabled:
   ```yaml
   logger:
     logs:
       custom_components.marstek_local_api: debug
   ```

2. Call a control service (e.g., `set_passive_mode`)

3. Look for log messages like:
   - `"Mode verified as Passive (attempt 1)"` - Success on first try
   - `"Mode verification failed: expected=Passive, actual=Auto (attempt 1/3)"` - Verification mismatch
   - `"Command failed (attempt 1/3)"` - Command send failure
   - `"Error verifying mode (attempt 1/3): UDP timeout"` - Verification error

4. Service should succeed even if first attempt fails

5. Service should raise `HomeAssistantError` only after 3 failed verification attempts

6. Each retry adds ~4 seconds (2s verify + 2s retry delay)

This confirms that the verification retry logic is working correctly and handling UDP packet loss.

## 4. Edge Case Testing

### Test: Invalid Power Value

Try setting an invalid power value and verify error handling:

```yaml
service: marstek_local_api.set_passive_mode
data:
  device_id: <your-device-id>
  power: 10000  # Exceeds reasonable limit
  countdown: 300
```

**Expected:** Service should complete, but device may reject the value.

### Test: Mode Change Detection (HA-Controlled Mode)

With HA-Controlled mode active:

1. Set target power to 500W
2. Wait for at least one update cycle (2+ minutes) to confirm Passive mode is active
3. Manually change mode to "Auto" using the mode select entity
4. Wait 5+ minutes (2-3 update cycles)
5. Verify HA-Controlled mode does NOT override back to Passive
6. Check logs for "mode manually changed" message
7. This confirms the "pause on manual change" behavior works

### Test: Multi-Device Partial Failure

In a multi-device setup:

1. Disconnect one battery from the network
2. Try `set_system_schedule` service
3. Verify partial success is reported
4. Connected devices should update, disconnected device should error

## 5. Performance Testing

### Test: Rapid Mode Changes

1. Call `set_passive_mode` with different power values in quick succession (2-3 seconds apart)
2. Verify battery responds to each command
3. Check logs for timeout warnings

**Expected:** Some commands may timeout or be ignored due to UDP reliability issues. This is normal.

### Test: Long-Running HA-Controlled Mode

1. Enable HA-Controlled mode
2. Set a target power value
3. Leave running for 10+ minutes (at least 5 update cycles)
4. Verify:
   - Mode remains "Passive"
   - Battery power stays near target
   - Log shows periodic updates every 2 minutes
5. Optional: Leave running for 3+ hours to verify long-term stability

## 6. Verification Checklist

After testing, verify:

- [ ] All services appear in Developer Tools → Services
- [ ] Service descriptions and parameter hints are clear
- [ ] Passive mode accepts positive and negative power values
- [ ] Manual mode schedules can be configured
- [ ] System-wide schedule works for multi-device setups
- [ ] HA-Controlled mode number entity appears when enabled
- [ ] HA-Controlled mode maintains power level over time
- [ ] Mode changes are reflected in sensors within 60 seconds
- [ ] No Python errors in Home Assistant logs
- [ ] Integration tests pass completely
- [ ] Unit tests achieve > 80% coverage

## 7. Troubleshooting

### Service Call Fails

- Check device_id is correct (use Developer Tools → States to find entity IDs)
- Verify Local API is still enabled on the device
- Check Home Assistant logs for error details

### HA-Controlled Mode Not Working

- Verify option is enabled in integration config
- Check that number entity exists
- Look for "HA-Controlled mode coordinator" messages in logs
- Verify device responds to manual Passive mode commands

### Schedule Not Applied

- Manual mode schedules may not take effect until the scheduled time window
- Use Passive mode for immediate effect
- Verify time format is "HH:MM" (24-hour format)
- Check week_set bitmask is correct (127 = all days)

## 8. Reporting Issues

If you find issues, please provide:

1. Home Assistant version
2. Integration version
3. Device model and firmware version
4. Detailed steps to reproduce
5. Relevant log entries with debug logging enabled:
   ```yaml
   logger:
     logs:
       custom_components.marstek_local_api: debug
   ```
6. Results from integration test script
7. Results from unit tests (if applicable)

## Success Criteria

All features are working correctly if:

✅ Integration tests complete without errors  
✅ Unit tests all pass  
✅ All services callable from Developer Tools  
✅ Passive mode commands change battery power immediately  
✅ Manual mode schedules can be configured  
✅ HA-Controlled mode maintains target power for extended periods  
✅ No Python exceptions in logs during normal operation  
✅ Battery responds to mode changes within expected timeframe  

