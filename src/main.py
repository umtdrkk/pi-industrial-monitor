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
# init_db           - creates the database if it doesn't exist yet
# write_reading_udp - writes via UDP (fast, fire-and-forget)
# client            - raw InfluxDB client for batch fallback
from src.influx_client import init_db, write_reading_udp, client as influx_client

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
#                              writer thread → UDP write (fire and forget)
influx_queue = queue.Queue()


def influx_writer_thread():
    """
    Background thread that drains the influx_queue and writes to InfluxDB via UDP.

    UDP writing is much faster than HTTP:
        HTTP batch: ~20ms per request → ~47Hz max
        UDP:        ~0.1ms per write  → theoretically 100Hz+

    Strategy:
        1. Wait for at least one reading (blocks up to 1 second)
        2. Drain everything else currently in the queue (non-blocking)
        3. Write each reading via UDP — fire and forget, no waiting
        4. Repeat

    Occasional lost UDP packets are acceptable at high sample rates —
    the next reading arrives within milliseconds anyway.
    """
    while True:
        batch = []
        try:
            # Wait for the first item — blocks until something arrives
            first = influx_queue.get(timeout=1.0)
            batch.append(first)
            influx_queue.task_done()

            # Drain everything else currently in the queue (non-blocking)
            while not influx_queue.empty():
                item = influx_queue.get_nowait()
                batch.append(item)
                influx_queue.task_done()

        except queue.Empty:
            continue

        # Write each reading via UDP — extremely fast, no HTTP overhead
        if batch:
            for reading in batch:
                write_reading_udp(reading)

            if len(batch) > 20:
                print(f"[InfluxDB UDP] Wrote batch of {len(batch)} points")


def mqtt_loop():
    """
    Main sensor loop — runs in its own thread.

    Reads sensors at SENSOR_READ_INTERVAL, publishes to MQTT broker,
    and puts readings into the influx_queue for async UDP writing.
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
            # The influx_writer_thread picks them up and writes via UDP
            for reading in readings:
                influx_queue.put(reading)

            time.sleep(SENSOR_READ_INTERVAL)

    except KeyboardInterrupt:
        disconnect()


def main():
    # Initialize InfluxDB — creates the database "sensor_data" if it doesn't exist yet
    init_db()

    # Start async UDP InfluxDB writer thread
    # Drains influx_queue via UDP — fastest possible write method
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