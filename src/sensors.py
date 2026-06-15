# random - used to generate fake sensor values when not running on real hardware
import random

# time - used to get current timestamps
import time

# Import settings: a flag for whether we're on a real Raspberry Pi, and sensor channel configs
from config.settings import RUNNING_ON_PI, SENSOR_CHANNELS


def read_sensors():
    # Main entry point: choose real or fake sensor reading depending on the environment
    if RUNNING_ON_PI:
        return _read_real_sensors()
    else:
        return _read_fake_sensors()


def _read_fake_sensors():
    # Generates random but realistic-looking sensor data for testing/development
    readings = []

    for channel in SENSOR_CHANNELS:
        if channel["type"] == "voltage":
            # Random voltage between 0 and 10 volts, rounded to 3 decimals
            raw_voltage = round(random.uniform(0.0, 10.0), 3)
            readings.append({
                "id":        channel["id"],
                "name":      channel["name"],
                "type":      "voltage",
                "value":     raw_voltage,
                "unit":      "V",
                "timestamp": time.time()
            })

        elif channel["type"] == "current":
            # Random current between 4 and 20 mA (standard industrial sensor range)
            raw_current = round(random.uniform(4.0, 20.0), 3)

            # Convert to a percentage of the 4-20mA range (4mA = 0%, 20mA = 100%)
            percent = round((raw_current - 4.0) / 16.0 * 100, 1)

            readings.append({
                "id":        channel["id"],
                "name":      channel["name"],
                "type":      "current",
                "value":     raw_current,
                "percent":   percent,
                "unit":      "mA",
                "timestamp": time.time()
            })

    return readings


def _read_real_sensors():
    # spidev lets us talk to hardware over the SPI bus (used by the ADC chips)
    import spidev

    spi = spidev.SpiDev()
    readings = []

    for channel in SENSOR_CHANNELS:
        # The MCP3208 ADC chips have 8 channels each.
        # If channel id is 1-8, use chip 0; if 9+, use chip 1.
        chip   = 0 if channel["id"] <= 8 else 1

        # Convert channel id (1-based) into the chip's internal channel number (0-7)
        ch_num = (channel["id"] - 1) % 8

        # Open communication with the correct chip on the SPI bus
        spi.open(0, chip)
        spi.max_speed_hz = 1350000  # SPI communication speed

        # Build the command bytes the MCP3208 expects to read a given channel.
        # This is the specific bit pattern required by the chip's datasheet.
        cmd = [0x06 | ((ch_num & 0x04) >> 2), (ch_num & 0x03) << 6, 0x00]

        # Send the command and receive the chip's response (3 bytes)
        response = spi.xfer2(cmd)

        # Extract the 12-bit reading from the response bytes
        raw = ((response[1] & 0x0F) << 8) | response[2]

        # Done talking to this chip for now
        spi.close()

        # Convert the raw 12-bit value (0-4095) into a voltage at the ADC pin (0-3.3V)
        voltage_at_adc = raw * (3.3 / 4096)

        if channel["type"] == "voltage":
            # Scale the ADC voltage back up to the real sensor voltage.
            # The sensor circuit divides the real voltage down to fit the ADC's 0-3.3V range,
            # so we multiply by the inverse of that divider (32.0 / 10.0) to undo it.
            real_value = round(voltage_at_adc * (32.0 / 10.0), 3)

            readings.append({
                "id":        channel["id"],
                "name":      channel["name"],
                "type":      "voltage",
                "value":     real_value,
                "unit":      "V",
                "timestamp": time.time()
            })

        elif channel["type"] == "current":
            # Convert the ADC voltage into mA using the value of the sense resistor (250 ohms)
            # I = V / R, then convert from A to mA (* 1000)
            current_ma = round(voltage_at_adc / 250 * 1000, 3)

            # Convert to percentage of the 4-20mA range, same as in the fake version
            percent    = round((current_ma - 4.0) / 16.0 * 100, 1)

            readings.append({
                "id":        channel["id"],
                "name":      channel["name"],
                "type":      "current",
                "value":     current_ma,
                "percent":   percent,
                "unit":      "mA",
                "timestamp": time.time()
            })

    return readings