# Marstek Local API for Home Assistant

Home Assistant integration that talks directly to Marstek Venus C/D/E batteries over the official Local API. It delivers local-only telemetry, mode control, and fleet-wide aggregation without relying on the Marstek cloud.

---

## 1. Enable the Local API

1. Make sure your batteries are on the latest firmware.
2. Use the [Marstek Venus Monitor](https://rweijnen.github.io/marstek-venus-monitor/latest/) tool to enable *Local API / Open API* on each device.
3. Note the UDP port (default `30000`) and confirm the devices respond on your LAN.

<img width="230" height="129" alt="afbeelding" src="https://github.com/user-attachments/assets/035de357-fbe6-4224-8249-03abb3078fa1" />

---

## 2. Install the Integration

### Via HACS
1. Click this button:

[![Open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jaapp&repository=ha-marstek-local-api&category=integration)

Or:
1. Open **HACS → Integrations → Custom repositories**.
2. Add `https://github.com/jaapp/ha-marstek-local-api` as an *Integration*.
3. Install **Marstek Local API** and restart Home Assistant.

### Manual copy
1. Drop `custom_components/marstek_local_api` into your Home Assistant `custom_components` folder.
2. Restart Home Assistant.

---

## 3. Add Devices

1. Go to **Settings → Devices & Services → Add Integration** and search for **Marstek Local API**.
2. The discovery step lists every battery it finds on your network. Select one device or pick **All devices** to build a single multi-battery entry.
3. If discovery misses a unit, choose **Manual IP entry** and provide the host/port you noted earlier.

After setup you can return to **Settings → Devices & Services → Marstek Local API → Configure** to:
- Rename devices, adjust the polling interval, or add/remove batteries to the existing multi-device entry.
- Trigger discovery again when new batteries join the network.

> **Important:** If you want all batteries to live under the same config entry (and keep the virtual **Marstek System** device), use the integration’s **Configure** button to add/remove batteries. The default Home Assistant “Add Device” button creates a brand-new config entry and a separate virtual system device.


<img width="442" height="442" alt="afbeelding" src="https://github.com/user-attachments/assets/45001642-412e-4c85-aace-b495639959ff" />

---

## 4. Single Entry vs. Virtual System Battery

- **Single-device entry**: created when you add an individual battery. Each entry exposes the battery’s entities and optional operating-mode controls.
- **Multi-device entry**: created when you pick *All devices* or add more batteries through the options flow. The integration keeps one config entry containing all members and exposes a synthetic device called **“Marstek System”**.  
  - The “system” device aggregates fleet metrics (total capacity, total grid import/export, combined state, etc.).  
  - Every physical battery still appears as its own device with per-pack entities.

<img width="1037" height="488" alt="afbeelding" src="https://github.com/user-attachments/assets/40bcb48a-02e6-4c85-85a4-73751265c6f8" />

---

## 5. Entities

| Category | Sensor (entity suffix) | Unit | Notes | Polling multiplier | Default interval (s) |
| --- | --- | --- | --- | ---: | ---: |
| **Battery** | `battery_soc` | % | State of charge | 1x | 60 |
|  | `battery_temperature` | °C | Pack temperature | 1x | 60 |
|  | `battery_capacity` | kWh | Remaining capacity | 1x | 60 |
|  | `battery_rated_capacity` | kWh | Rated pack capacity | 1x | 60 |
|  | `battery_available_capacity` | kWh | Estimated energy still available before full charge | 1x | 60 |
|  | `battery_voltage` | V | Pack voltage | 1x | 60 |
|  | `battery_current` | A | Pack current (positive = charge) | 1x | 60 |
| **Energy system (ES)** | `battery_power` | W | Pack power (positive = charge) | 1x | 60 |
|  | `battery_power_in` / `battery_power_out` | W | Split charge/discharge power | 1x | 60 |
|  | `battery_state` | text | `charging` / `discharging` / `idle` | 1x | 60 |
|  | `grid_power` | W | Grid import/export (positive = import) | 1x | 60 |
|  | `offgrid_power` | W | Off-grid load | 1x | 60 |
|  | `pv_power_es` | W | Solar production reported via ES | 1x | 60 |
|  | `total_pv_energy` | kWh | Lifetime PV energy | 1x | 60 |
|  | `total_grid_import` / `total_grid_export` | kWh | Lifetime grid counters | 1x | 60 |
|  | `total_load_energy` | kWh | Lifetime load energy | 1x | 60 |
| **Energy meter / CT** | `ct_phase_a_power`, `ct_phase_b_power`, `ct_phase_c_power` | W | Per-phase measurements (if CTs installed) | 5x | 300 |
|  | `ct_total_power` | W | CT aggregate | 5x | 300 |
| **Mode** | `operating_mode` | text | Auto / AI / Manual / Passive | 5x | 300 |
| **PV (Venus D only)** | `pv_power`, `pv_voltage`, `pv_current` | W / V / A | MPPT telemetry | 5x | 300 |
| **Network** | `wifi_rssi` | dBm | Wi-Fi signal | 10x | 600 |
|  | `wifi_ssid`, `wifi_ip`, `wifi_gateway`, `wifi_subnet`, `wifi_dns` | text | Wi-Fi configuration | 10x | 600 |
| **Device info** | `device_model`, `firmware_version`, `ble_mac`, `wifi_mac`, `device_ip` | text | Identification fields | 10x | 600 |
| **Diagnostics** | `last_message_received` | seconds | Time since the last successful poll | 1x | 60 |

Every sensor listed above also exists in an aggregated form under the **Marstek System** device whenever you manage multiple batteries together (prefixed with `system_`).

---

## 6. Services

### Data Management

| Service | Description | Parameters |
| --- | --- | --- |
| `marstek_local_api.request_data_sync` | Triggers an immediate poll of every configured coordinator. | Optional `entry_id` to refresh a specific config entry. |

### Manual Mode Control

| Service | Description | Parameters |
| --- | --- | --- |
| `marstek_local_api.set_manual_schedule` | Configure Manual mode schedule for a device. | `device_id` (required), `schedule` (required, JSON object) |
| `marstek_local_api.set_system_schedule` | Apply the same schedule to all batteries in a system. | `entry_id` (required), `schedule` (required, JSON object) |

**Schedule JSON Format:**
```json
{
  "time_num": 0,
  "start_time": "08:30",
  "end_time": "20:30",
  "week_set": 127,
  "power": 100,
  "enable": 1
}
```

- `time_num`: Slot index 0-9 (Venus C/E supports 10 time slots)
- `start_time`, `end_time`: Time in "HH:MM" format
- `week_set`: 7-bit mask for days of week (1=Mon, 2=Tue, 4=Wed, 8=Thu, 16=Fri, 32=Sat, 64=Sun, 127=all days)
- `power`: Target power in watts (positive=charge, negative=discharge)
- `enable`: 1=active, 0=inactive

### Passive Mode Control

| Service | Description | Parameters |
| --- | --- | --- |
| `marstek_local_api.set_passive_mode` | Set Passive mode with custom power and countdown. | `device_id` (required), `power` (required, W), `countdown` (required, seconds) |

**Example: Set passive mode to charge at 500W for 2 hours:**
```yaml
service: marstek_local_api.set_passive_mode
data:
  device_id: abcd1234efgh5678ijkl9012mnop3456
  power: 500
  countdown: 7200
```

You can call these services from **Developer Tools → Services** for advanced battery control.

### UDP Reliability & Verification

Marstek batteries communicate via UDP, which can drop packets. To ensure reliable operation, all control services automatically:

1. **Send the command** to the battery
2. **Wait 2 seconds** for the battery to process the command
3. **Query the actual mode** from the battery to verify the change
4. **Retry up to 3 times** if verification fails
5. **Report success** only after confirming the battery actually changed state

This ensures commands aren't silently lost due to packet drops. Each service call may take up to 12 seconds if multiple retries are needed, but this guarantees reliable control.

### Future Controls

The following control features are planned but not yet available due to API limitations:

**Schedule Management:**
- Retrieval of manual mode schedules (ES.GetMode API doesn't return schedule details)
- Copy schedules between devices (requires schedule retrieval)

**Power Management:**
- Power limiting settings (API methods not documented)
- Current limiting configuration (API methods not documented)

These features will be added if/when Marstek extends the Local API to support them.

---

## 7. HA-Controlled Mode

**HA-Controlled Mode** enables direct grid power control from Home Assistant, allowing you to create sophisticated automations that respond to dynamic electricity pricing, solar production, or other conditions.

> **Important:** HA-Controlled mode is NOT an official Marstek operating mode. It's a Home Assistant construct that uses the undocumented Passive mode to give you direct control over battery charge/discharge power.

### How It Works

1. Enable "HA-Controlled Mode" in the integration's options
2. A "Target Grid Power" number entity appears for each device
3. Set the target wattage (negative=discharge, positive=charge)
4. The integration automatically maintains this power level by:
   - Sending Passive mode commands **every 2 minutes**
   - Setting a **2-hour countdown** on each command
   - The long countdown ensures the battery effectively always follows HA's target power
   - If HA crashes or loses connection, the battery continues with the last command until the countdown expires
   - Continuously refreshing to maintain tight control

### Enabling HA-Controlled Mode

1. Go to **Settings → Devices & Services → Marstek Local API**
2. Click **Configure** on your integration entry
3. Enable **"HA-Controlled Mode"**
4. Restart or reload the integration

### Usage Example

**Dynamic pricing automation:**
```yaml
automation:
  - alias: "Battery: Charge during off-peak"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      - service: number.set_value
        target:
          entity_id: number.marstek_venuse_target_grid_power
        data:
          value: 2000  # Charge at 2000W

  - alias: "Battery: Discharge during peak"
    trigger:
      - platform: time
        at: "17:00:00"
    action:
      - service: number.set_value
        target:
          entity_id: number.marstek_venuse_target_grid_power
        data:
          value: -1500  # Discharge at 1500W

  - alias: "Battery: Idle during normal hours"
    trigger:
      - platform: time
        at: "09:00:00"
    action:
      - service: number.set_value
        target:
          entity_id: number.marstek_venuse_target_grid_power
        data:
          value: 0  # Idle
```

**Solar-based automation:**
```yaml
automation:
  - alias: "Battery: Follow solar excess"
    trigger:
      - platform: state
        entity_id: sensor.solar_excess_power
    action:
      - service: number.set_value
        target:
          entity_id: number.marstek_venuse_target_grid_power
        data:
          value: "{{ states('sensor.solar_excess_power') | int }}"
```

### Important Notes

- **Not an official mode:** HA-Controlled is a Home Assistant construct using the undocumented Passive mode
- **Uses Passive mode internally:** You'll see "Passive" in the operating mode sensor while HA-Controlled is active
- **Manual override:** If you manually change the mode (via the mode select), HA control automatically pauses
- **Power range:** -2500W (discharge) to +2500W (charge) - may vary by device model
- **Update frequency:** Commands sent every 2 minutes to ensure that the passive mode setting matches what HA expects
- **Long countdown:** 2-hour countdown ensures battery follows HA setting even if connection is temporarily lost
- **Ideal use case:** Dynamic automations responding to pricing, solar, or load conditions
- **Not for manual control:** If you need simple time-based schedules or want your battery to function without HA, use Manual mode instead

---

## 8. Tips & Troubleshooting

- Keep the standard polling interval (60 s) unless you have explicit reasons to slow it down. Faster intervals than 60s can lead to the battery becoming unresponsive.
- If discovery fails, double-check that the Local API remains enabled after firmware upgrades and that UDP port `30000` is accessible from Home Assistant.
- For verbose logging, append the following to `configuration.yaml`:
  ```yaml
  logger:
    logs:
      custom_components.marstek_local_api: debug
  ```

## API maturity & known issues

Note: the Marstek Local API is still relatively new and evolving. Behavior can vary between hardware revisions (v2/v3) and firmware versions (EMS and BMS). When reporting issues, always include diagnostic data (logs and the integration's diagnostic fields).

Known issues (brief):
- Battery temperature may read 10× too high on older BMS versions.
- API call timeouts (shown as warnings in the log).
- Some API calls are not supported on older firmware — please ensure devices are updated before filing issues.
- Polling faster than 60s is not advised; devices have been reported to become unstable (e.g. losing CT003 connection).
 - Energy counters / capacity fields may be reported in Wh instead of kWh on certain firmware (values appear 1000× off).
 - `ES.GetStatus` can be unresponsive on some Venus E v3 firmwares (reported on v137 / v139).
 - CT connection state may be reported as "disconnected" / power values might not be updated even when a CT is connected (appears fixed in HW v2 firmware v154+).

Most of these issues are resolved by updating the device to the latest firmware — Marstek staggers rollouts, so many systems still run older versions. The Local API is evolving quickly and should stabilise as updates are deployed.

Example warnings:

```
2025-10-21 10:01:34.986 WARNING (MainThread) [custom_components.marstek_local_api.api] Command ES.GetStatus timed out after 15s (attempt 1/3, host=192.168.0.47)
2025-10-21 10:02:28.693 ERROR (MainThread) [custom_components.marstek_local_api.api] Command EM.GetStatus failed after 3 attempt(s); returning no result
```

Quick note for issue reports (EN): always attach the integration diagnostics export and relevant HA logs when filing a bug — it is required for effective troubleshooting.


### Standalone connectivity test

In the repository you'll find `manual_tests/test_discovery.py`, a small CLI that reuses the integration code to probe connectivity outside Home Assistant:

```bash
cd manual_tests
python3 test_discovery.py              # broadcast discovery
python3 test_discovery.py 192.168.7.101  # target a specific battery
```

It discovers all reachable batteries, exercises every Local API method, and highlights network issues before you wire the devices into your HA instance.

---

## 9. Testing

### Integration Tests

Run the standalone integration test to verify connectivity and control functionality:

```bash
cd manual_tests
python3 test_discovery.py              # Auto-discover and test all devices
python3 test_discovery.py 192.168.1.100  # Test specific device
```

The test script now includes:
- All sensor data retrieval
- Passive mode control with verification
- Manual mode schedule configuration
- Mode restoration after tests

### Unit Tests

Run pytest unit tests for services, number entities, and HA control:

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_services.py

# Run with coverage
pytest tests/ --cov=custom_components.marstek_local_api
```

---

## 10. Release Notes

Version **1.1.0** adds limited control capabilities:
- **New Services**: Manual mode schedule management, Passive mode control, system-wide schedule application
- **HA-Controlled Mode**: Direct grid power control via number entity with automated Passive mode maintenance
- **Control Tests**: Integration tests for mode switching and schedule configuration
- **Unit Tests**: Comprehensive pytest coverage for all control functionality

Version **1.0.0** focused on stable multi-device experience:
- kWh-based energy reporting aligned with the Marstek UI
- Options flow for renaming, adding, and removing devices after initial setup
- `marstek_local_api.request_data_sync` service for immediate refreshes
- Aggregated **Marstek System** device for fleet-wide KPIs

Enjoy full local control of your Marstek batteries! Pull requests and feedback are welcome.
