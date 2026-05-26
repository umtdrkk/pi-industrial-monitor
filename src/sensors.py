import random
import time
from config.settings import RUNNING_ON_PI, SENSOR_CHANNELS

def read_sensors():
    if RUNNING_ON_PI:
        return _read_real_sensors()
    else:
        return _read_fake_sensors()

def _read_fake_sensors():
    readings = []
    for channel in SENSOR_CHANNELS:
        if channel["type"] == "voltage":
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
            raw_current = round(random.uniform(4.0, 20.0), 3)
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
    import spidev
    spi = spidev.SpiDev()
    readings = []

    for channel in SENSOR_CHANNELS:
        chip   = 0 if channel["id"] <= 8 else 1
        ch_num = (channel["id"] - 1) % 8

        spi.open(0, chip)
        spi.max_speed_hz = 1350000

        cmd = [0x06 | ((ch_num & 0x04) >> 2), (ch_num & 0x03) << 6, 0x00]
        response = spi.xfer2(cmd)
        raw = ((response[1] & 0x0F) << 8) | response[2]

        spi.close()

        voltage_at_adc = raw * (3.3 / 4096)

        if channel["type"] == "voltage":
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
            current_ma = round(voltage_at_adc / 250 * 1000, 3)
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