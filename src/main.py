# asyncio - needed to run the OPC UA server (which is async)
import asyncio

# threading - lets us run multiple things "at the same time" in one program
import threading

# queue - thread-safe queue for passing readings to the InfluxDB writer thread
import queue

# time - used for the sleep/delay between sensor reads
import time

# Import Flask starter function
from src.flask_api import start_flask

# Import our own modules: sensor reading, MQTT functions, and the OPC UA server
from src.sensors import read_sensors
from src.mqtt_client import connect, publish, disconnect
from src.opcua_server import start_opcua_server

# Import InfluxDB functions:
# init_db       - creates the database if it doesn't exist yet
# write_reading - writes a single sensor reading to InfluxDB
from src.influx_client import init_db, write_reading

# Import the configured delay (in seconds) between sensor reads
from config.settings import SENSOR_READ_INTERVAL


# ── ASYNC INFLUXDB WRITER ────────────────────────────────────────────────────
# A thread-safe queue that receives sensor readings from the MQTT loop.
# The InfluxDB writer thread drains this queue independently,
# so slow InfluxDB writes never block the sensor reading loop.
#
# Without this: read → publish → write (sequential, slow)
# With this:    read → publish → queue.put() (fast)
#                                     ↓
#                              writer thread → write (background, doesn't block)
influx_queue = queue.Queue()


def influx_writer_thread():
    """
    Background thread that drains the influx_queue and writes to InfluxDB.

    Runs forever as a daemon thread. If InfluxDB is slow or temporarily
    unavailable, readings accumulate in the queue instead of blocking
    the sensor reading loop. Errors are caught and logged without crashing.
    """
    while True:
        try:
            # Block until a reading is available (timeout allows clean shutdown)
            reading = influx_queue.get(timeout=1.0)
            write_reading(reading)
            influx_queue.task_done()
        except queue.Empty:
            # No readings in queue — just wait for the next one
            continue
        except Exception as e:
            # InfluxDB write failed — log it but keep running
            print(f"[InfluxDB] Write error: {e}")


def mqtt_loop():
    """
    Main sensor loop — runs in its own thread.

    Reads sensors at SENSOR_READ_INTERVAL, publishes to MQTT broker,
    and puts readings into the influx_queue for async writing.
    The actual InfluxDB write happens in a separate background thread,
    so this loop is never blocked by slow database writes.
    """
    connect()

    try:
        while True:
            readings = read_sensors()

            # Publish all readings to MQTT broker so the dashboard receives them live
            publish(readings)

            # Put readings into the queue — returns instantly, never blocks
            # The influx_writer_thread picks them up and writes to InfluxDB
            for reading in readings:
                influx_queue.put(reading)

            time.sleep(SENSOR_READ_INTERVAL)

    except KeyboardInterrupt:
        disconnect()


def main():
    # Initialize InfluxDB — creates the database "sensor_data" if it doesn't exist yet
    init_db()

    # Start async InfluxDB writer thread
    # Drains influx_queue in the background without blocking the sensor loop
    writer_thread = threading.Thread(target=influx_writer_thread, daemon=True)
    writer_thread.start()

    # Start Flask API server in background thread
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    # Start MQTT loop in background thread
    mqtt_thread = threading.Thread(target=mqtt_loop, daemon=True)
    mqtt_thread.start()

    # Run the OPC UA server on the main thread
    asyncio.run(start_opcua_server(read_sensors))


if __name__ == "__main__":
    main()