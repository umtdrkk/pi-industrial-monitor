import random
import time
from config.settings import RUNNING_ON_PI, SENSOR_CHANNELS


def read_sensors():
    """
    Main entry point for sensor reading.
    Automatically switches between real hardware (Pi) and fake data (Mac development)
    based on the RUNNING_ON_PI flag in settings.
    """
    if RUNNING_ON_PI:
        return _read_real_sensors()
    else:
        return _read_fake_sensors()


# ── CONVERTERS ──────────────────────────────────────────────────────────────
# Each converter function takes the raw voltage at the ADC input and returns
# a dictionary with the real-world physical value, unit, and any extra fields.
#
# To add a new sensor type:
#   1. Write a new _convert_xxx(voltage_at_adc) function below
#   2. Register it in the CONVERTERS dictionary
#   3. Add the type name to FAKE_ADC_RANGES for development simulation
#   4. Add channels with that type in config/settings.py
# ─────────────────────────────────────────────────────────────────────────────

def _convert_voltage(voltage_at_adc):
    """
    Converts ADC voltage to real-world distance in mm.

    Hardware: Capacitive distance sensor (15-500mm range)
    Signal type: 0-10V analog output, NORMAL mode (0V...10V)
        0V   = object at minimum distance (15mm)
        10V  = no object detected (> 500mm away)

    Signal conditioning: 33kΩ + 10.5kΩ voltage divider
        scales 0-10V sensor output down to ~0-2.5V for MCP3208 (max 3.3V)
        reverse factor: (33 + 10.5) / 10.5 = 43.5 / 10.5 = 4.143

    Distance formula (linear, normal mode):
        real_voltage = voltage_at_adc × 4.143
        distance_mm  = (real_voltage / 10) × 485 + 15
            where 485 = sensor span (500mm - 15mm)
                   15 = minimum detectable distance in mm
    """
    # Step 1: reverse the voltage divider using actual measured resistor values
    # R1 = 33kΩ, R2 = 10.5kΩ → factor = (R1+R2)/R2 = 43.5/10.5 = 4.143
    real_voltage = round(voltage_at_adc * 4.143, 3)

    # Step 2: convert voltage to distance — normal mode (0V=close, 10V=far)
    # 0V → 15mm (closest), 10V → 500mm (furthest / nothing detected)
    distance_mm = round((real_voltage / 10) * 485 + 15, 1)

    # Step 3: clamp to valid sensor range (15-500mm)
    distance_mm = max(15.0, min(500.0, distance_mm))

    return {
        "value": distance_mm,    # physical distance in mm
        "unit": "mm",
        "voltage": real_voltage, # raw sensor voltage — shown as secondary info on dashboard
    }

def _convert_current(voltage_at_adc):
    """
    Converts ADC voltage to real-world pressure in bar.

    Hardware: Baumer PP20H pressure sensor (0-1 bar range)
    Signal type: 4-20mA industrial current loop
        4mA  = 0.0 bar (no pressure)
        20mA = 1.0 bar (maximum pressure)
        <4mA = sensor not powered or fault condition

    Signal conditioning: 150Ω shunt resistor (no extra voltage divider)
        Ohm's law: V = I × R → voltage_at_adc = current_A × 150
        Reverse: current_ma = voltage_at_adc / 150 × 1000

    Range check:
        4mA  → 0.6V at ADC (0 bar)
        20mA → 3.0V at ADC (1 bar) — safely within MCP3208 3.3V max

    Pressure formula:
        pressure_bar = (current_ma - 4.0) / 16.0 × 1.0
            where 16.0 = span (20mA - 4mA)
                   1.0 = max range in bar

    Percent and pressure are clamped at 0 minimum so the display never
    shows negative values when the sensor is below the 4mA baseline.
    """
    # Convert ADC voltage to current using the 150Ω shunt
    current_ma = round(voltage_at_adc / 150 * 1000, 3)

    # Convert 4-20mA to 0-1 bar — clamp at 0 minimum
    pressure_bar = round(max(0.0, (current_ma - 4.0) / 16.0 * 1.0), 4)

    # Percentage within 0-1 bar range — clamp at 0% minimum
    percent = round(max(0.0, (current_ma - 4.0) / 16.0 * 100), 1)

    return {
        "value": pressure_bar,     # pressure in bar
        "percent": percent,        # 0-100% within 0-1 bar range
        "unit": "bar",
        "current_ma": current_ma,  # raw current in mA — useful for debugging
    }


# Registry of all supported sensor types.
# Maps the "type" string from settings.py to the converter function.
CONVERTERS = {
    "voltage": _convert_voltage,   # 0-10V analog sensors (distance, position)
    "current": _convert_current,   # 4-20mA current loop sensors (pressure, flow)
}

# Simulated ADC voltage ranges for each sensor type — used only when RUNNING_ON_PI = False.
# These represent realistic voltages AT the ADC input (after signal conditioning).
FAKE_ADC_RANGES = {
    "voltage": (0.0, 3.1),   # simulates 0-10V sensor through 22k/10k divider → 0-3.1V at ADC
    "current": (0.6, 3.0),   # simulates 4-20mA sensor through 150Ω shunt → 0.6-3.0V at ADC
                              # 0.6V = 4mA (0 bar), 3.0V = 20mA (1 bar)
}


# ── FAKE DATA (Mac development, no hardware needed) ──────────────────────────

def _read_fake_sensors():
    """
    Generates realistic simulated sensor readings for development on Mac.
    Uses the same converter functions as real hardware so the output format
    is identical — MQTT, OPC UA and the dashboard never know the difference.
    """
    readings = []
    for channel in SENSOR_CHANNELS:
        ch_type = channel["type"]
        converter = CONVERTERS.get(ch_type)

        if converter is None:
            print(f"Warning: unknown sensor type '{ch_type}' for channel {channel['id']}, skipping")
            continue

        # Generate a random voltage within the realistic ADC range for this sensor type
        adc_range = FAKE_ADC_RANGES.get(ch_type, (0.0, 3.3))
        fake_voltage_at_adc = random.uniform(*adc_range)

        # Run through the same converter as real hardware
        result = converter(fake_voltage_at_adc)

        readings.append({
            "id": channel["id"],
            "name": channel["name"],
            "type": ch_type,
            "category": channel.get("category", "default"),
            "timestamp": time.time(),
            **result  # unpacks value, unit, voltage (distance) or percent (current)
        })
    return readings


# ── REAL DATA (Raspberry Pi with MCP3208 ADC) ────────────────────────────────

def _read_real_sensors():
    """
    Reads real sensor data from the MCP3208 ADC chip via SPI.

    MCP3208 specs:
        12-bit resolution: raw values 0 to 4095
        Reference voltage: 3.3V
        Voltage resolution: 3.3V / 4096 = ~0.8mV per step
        8 channels per chip, chip 0 = sensors 1-8, chip 1 = sensors 9-16

    SPI command format (MCP3208 datasheet):
        3 bytes sent, 3 bytes received simultaneously
        Result is in the lower 12 bits of the response
    """
    import spidev
    spi = spidev.SpiDev()
    readings = []

    for channel in SENSOR_CHANNELS:
        ch_type = channel["type"]
        converter = CONVERTERS.get(ch_type)

        if converter is None:
            print(f"Warning: unknown sensor type '{ch_type}' for channel {channel['id']}, skipping")
            continue

        # Sensors 1-8 → chip 0 (CE0), sensors 9-16 → chip 1 (CE1)
        chip = 0 if channel["id"] <= 8 else 1
        # 0-indexed channel number on the chip
        ch_num = (channel["id"] - 1) % 8

        # Open SPI connection to the selected chip
        spi.open(0, chip)
        spi.max_speed_hz = 1350000  # 1.35 MHz — within MCP3208 2.0 MHz max at 3.3V

        # Build the 3-byte SPI command for single-ended reading (MCP3208 datasheet Table 5-1)
        cmd = [0x06 | ((ch_num & 0x04) >> 2), (ch_num & 0x03) << 6, 0x00]

        # Send command and simultaneously receive 3 bytes back
        response = spi.xfer2(cmd)

        # Extract 12-bit result: upper 4 bits from response[1], lower 8 from response[2]
        raw = ((response[1] & 0x0F) << 8) | response[2]

        # Release SPI connection before next channel
        spi.close()

        # Convert raw 12-bit value to voltage: voltage = raw × (3.3 / 4096)
        voltage_at_adc = raw * (3.3 / 4096)

        # DEBUG — remove this line after sensor validation is complete
        print(f"[DEBUG] Channel {channel['id']} | raw={raw} | voltage_at_adc={voltage_at_adc:.3f}V")

        # Run through the appropriate converter for this sensor type
        result = converter(voltage_at_adc)

        readings.append({
            "id": channel["id"],
            "name": channel["name"],
            "type": ch_type,
            "category": channel.get("category", "default"),
            "timestamp": time.time(),
            **result  # unpacks value, unit, voltage (distance) or percent (current)
        })

    return readings