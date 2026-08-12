# pi-industrial-monitor

# PMF Industrial Monitor

Embedded system for acquiring, processing, and visualizing sensor data
on a Raspberry Pi, developed as part of the PMF project (TU Berlin,
Fachgebiet Handhabungs- und Montagetechnik).

## Development Environment: RUNNING_ON_PI

`config/settings.py` contains a flag that controls whether the system
reads real sensor data (via SPI/ADC) or generates simulated test data:

```python
RUNNING_ON_PI = False  # Laptop / remote development
RUNNING_ON_PI = True   # Running directly on the Raspberry Pi
```

**Important:**

- **Laptop / remote development (no access to SPI/ADC hardware):**
  Set `RUNNING_ON_PI = False`.
  `sensors.py` will use `_read_fake_sensors()`, generating realistic
  simulated values through the same converter functions used for real
  hardware. MQTT, InfluxDB, the Flask API, and the OPC UA server all run
  normally — only the sensor values themselves are simulated.

- **On the Raspberry Pi (with the MCP3208 connected):**
  Set `RUNNING_ON_PI = True`.
  `sensors.py` will use `_read_real_sensors()` and read actual ADC
  values over SPI.

**Always double-check that `RUNNING_ON_PI = True` before deploying to
the Pi.** Otherwise the system will keep writing simulated random
values to the database even though real hardware is connected.

## Kiosk Mode (Dashboard Auto-Start)

The dashboard starts automatically whenever the Raspberry Pi is powered
on — no manual login or browser launch required.

- A `systemd` service starts the backend (`main.py`) on boot.
- Chromium is launched in kiosk mode, displaying the dashboard directly
  on the connected touchscreen.

Simply plugging in the Pi is enough to bring the full system up.

## SSH Access

To SSH into the Pi remotely, **both the Pi and your laptop need a
stable network connection** (same network/VPN, or however your setup
is configured) — SSH will fail or hang if either side drops off the
network mid-session.

```bash
ssh pi@<pi-ip-address>
```

Password: see team credentials doc / ask a team member.