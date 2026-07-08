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

    Hardware: Capacitive distance sensor (0-500mm range)
    Signal type: 0-10V analog output, configured in INVERSE mode (10V...0V)
        → 10V = no object detected (> 500mm away)
        → 0V  = object at minimum distance (15mm)

    Signal conditioning: 22kΩ + 10kΩ voltage divider
        → scales 0-10V sensor output down to 0-3.125V for the MCP3208 (max 3.3V)
        → reverse factor: 32/10 = 3.2

    Distance formula derived from datasheet (Erfassungsbereich: 15-500mm):
        real_voltage = voltage_at_adc × 3.2
        distance_mm  = (1 - real_voltage / 10) × 485 + 15
            where 485 = sensor span (500mm - 15mm)
                   15 = minimum detectable distance in mm
    """
    # Step 1: reverse the voltage divider to get the actual sensor output voltage
    real_voltage = round(voltage_at_adc * 3.2, 3)

    # Step 2: convert voltage to distance using inverse sensor characteristic
    # 10V → 15mm (closest), 0V → 500mm (furthest / nothing detected)
    distance_mm = round((1 - real_voltage / 10) * 485 + 15, 1)

    # Step 3: clamp to valid sensor range (15-500mm) to avoid out-of-range values
    # caused by noise or edge conditions
    distance_mm = max(15.0, min(500.0, distance_mm))

    return {
        "value": distance_mm,        # physical distance in mm
        "unit": "mm",
        "voltage": real_voltage,     # raw sensor voltage — useful for debugging
    }


def _convert_current(voltage_at_adc):
    """
    Converts ADC voltage to real-world current in milliamps (mA).

    Hardware: Pressure sensor with 4-20mA current loop output
    Signal type: 4-20mA industrial current loop
        → 4mA  = 0% (no pressure / minimum)
        → 20mA = 100% (maximum pressure)
        → <4mA = sensor not powered or fault condition

    Signal conditioning: 150Ω shunt resistor (no extra voltage divider)
        → Ohm's law: V = I × R → voltage_at_adc = current_A × 150
        → Reverse: current_A = voltage_at_adc / 150
        → In mA:   current_ma = voltage_at_adc / 150 × 1000

    Range check:
        4mA  → 0.6V at ADC
        20mA → 3.0V at ADC (safely within MCP3208's 3.3V max)

    Percent is clamped to 0% minimum so the display doesn't show
    negative values when the sensor is below the 4mA baseline.
    """
    # Convert ADC voltage to current using the 150Ω shunt
    current_ma = round(voltage_at_adc / 150 * 1000, 3)

    # Convert 4-20mA range to 0-100% — clamp at 0% minimum
    # (values below 4mA indicate no pressure or fault, not negative pressure)
    percent = round(max(0.0, (current_ma - 4.0) / 16.0 * 100), 1)

    return {
        "value": current_ma,   # current in milliamps
        "percent": percent,    # 0-100% within the 4-20mA range
        "unit": "mA",
    }


# Registry of all supported sensor types.
# Maps the "type" string from settings.py to the converter function.
# Adding a new sensor type = one new function above + one new entry here.
CONVERTERS = {
    "voltage": _convert_voltage,   # 0-10V analog sensors (e.g. distance, position)
    "current": _convert_current,   # 4-20mA current loop sensors (e.g. pressure, flow)
}

# Simulated ADC voltage ranges for each sensor type — used only when RUNNING_ON_PI = False.
# These represent realistic voltages AT the ADC input (after signal conditioning),
# not the raw sensor output voltages.
FAKE_ADC_RANGES = {
    "voltage": (0.0, 3.1),    # simulates 0-10V sensor through 22k/10k divider → 0-3.1V at ADC
    "current": (0.09, 3.0),   # simulates 4-20mA sensor through 150Ω shunt → 0.6-3.0V at ADC
                               # (0.09V = ~0.6mA noise floor, 3.0V = 20mA)
}


# ── FAKE DATA (Mac development, no hardware needed) ──────────────────────────

def _read_fake_sensors():
    """
    Generates realistic simulated sensor readings for development on Mac.
    Uses the same converter functions as real hardware — so the output format
    is identical. MQTT, OPC UA and the dashboard never know the difference.
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
            **result   # unpacks value, unit, and any extra fields from the converter
        })
    return readings


# ── REAL DATA (Raspberry Pi with MCP3208 ADC) ────────────────────────────────

def _read_real_sensors():
    """
    Reads real sensor data from the MCP3208 ADC chip via SPI.

    MCP3208 specs:
        - 12-bit resolution: raw values from 0 to 4095
        - Reference voltage: 3.3V
        - Voltage resolution: 3.3V / 4096 = ~0.8mV per step
        - 8 channels per chip, 2 chips supported (chip 0 = sensors 1-8, chip 1 = sensors 9-16)

    SPI command format (from MCP3208 datasheet):
        3 bytes sent, 3 bytes received simultaneously
        Byte 1: start bit + single/diff bit + channel MSB
        Byte 2: channel LSBs + padding
        Byte 3: padding (0x00)
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

        # Determine which MCP3208 chip and which channel on that chip
        # Sensors 1-8 → chip 0 (CE0), sensors 9-16 → chip 1 (CE1)
        chip = 0 if channel["id"] <= 8 else 1
        ch_num = (channel["id"] - 1) % 8  # 0-indexed channel number on the chip

        # Open SPI connection to the selected chip
        spi.open(0, chip)
        spi.max_speed_hz = 1350000  # 1.35 MHz — within MCP3208's 2.0 MHz max at 3.3V

        # Build the 3-byte SPI command for single-ended reading on ch_num
        # Format from MCP3208 datasheet Table 5-1
        cmd = [0x06 | ((ch_num & 0x04) >> 2), (ch_num & 0x03) << 6, 0x00]

        # Send command and simultaneously receive 3 bytes back
        response = spi.xfer2(cmd)

        # Extract the 12-bit result from the response bytes
        # response[1] contains the upper 4 bits, response[2] the lower 8 bits
        raw = ((response[1] & 0x0F) << 8) | response[2]

        # Close SPI connection — important to release for the next channel
        spi.close()

        # Convert raw 12-bit value to voltage at the ADC input
        # voltage = raw × (Vref / 2^12) = raw × (3.3 / 4096)
        voltage_at_adc = raw * (3.3 / 4096)

        # DEBUG — prints raw ADC value and voltage before conversion
        # Remove this line after validation is complete
        print(f"[DEBUG] Channel {channel['id']} | raw={raw} | voltage_at_adc={voltage_at_adc:.3f}V")

        # Run through the appropriate converter for this sensor type
        result = converter(voltage_at_adc)

        readings.append({
            "id": channel["id"],
            "name": channel["name"],
            "type": ch_type,
            "category": channel.get("category", "default"),
            "timestamp": time.time(),
            **result   # unpacks value, unit, voltage (for distance) or percent (for current)
        })

    return readings