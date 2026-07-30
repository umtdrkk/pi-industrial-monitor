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
# client        - the raw InfluxDB client for batch writes
from src.influx_client import init_db, write_reading, client as influx_client

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
#                              writer thread → batch write (background)
influx_queue = queue.Queue()


def influx_writer_thread():
    """
    Background thread that drains the influx_queue and writes to InfluxDB in batches.

    Batch writing is significantly faster than individual writes:
        Individual: 1 HTTP request per point → ~37ms per write → ~27Hz max
        Batch:      1 HTTP request per N points → much lower overhead → higher throughput

    Strategy:
        1. Wait for at least one reading (blocks up to 1 second)
        2. Drain everything else currently in the queue (non-blocking)
        3. Write the entire batch in one HTTP request
        4. Repeat

    This keeps latency low while maximizing write throughput.
    If InfluxDB is unavailable, errors are caught and logged without crashing.
    """
    while True:
        batch = []
        try:
            # Wait for the first item — blocks until something arrives
            first = influx_queue.get(timeout=1.0)
            batch.append(first)
            influx_queue.task_done()

            # Drain everything else currently in the queue (non-blocking)
            # This collects all readings that accumulated since the last write cycle
            while not influx_queue.empty():
                item = influx_queue.get_nowait()
                batch.append(item)
                influx_queue.task_done()

        except queue.Empty:
            # Nothing in queue — just wait for the next cycle
            continue

        # Write the entire batch in one HTTP request to InfluxDB
        # One request for N points is much faster than N individual requests
        if batch:
            try:
                # Convert readings to InfluxDB point format
                points = [
                    {
                        "measurement": "sensor",
                        "tags": {
                            "sensor_id":   str(r["id"]),
                            "sensor_name": r["name"],
                            "sensor_type": r["type"],
                            "category":    r.get("category", "default"),
                        },
                        "fields": {
                            "value": float(r["value"]),
                            "unit":  r["unit"],
                        }
                    }
                    for r in batch
                ]

                # Single HTTP request for the whole batch
                influx_client.write_points(points)

                if len(batch) > 10:
                    # Log batch size when it's large — useful for tuning
                    print(f"[InfluxDB] Batch write: {len(batch)} points")

            except Exception as e:
                print(f"[InfluxDB] Batch write error ({len(batch)} points): {e}")


def mqtt_loop():
    """
    Main sensor loop — runs in its own thread.

    Reads sensors at SENSOR_READ_INTERVAL, publishes to MQTT broker,
    and puts readings into the influx_queue for async batch writing.
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
            # The influx_writer_thread picks them up and batch writes to InfluxDB
            for reading in readings:
                influx_queue.put(reading)

            time.sleep(SENSOR_READ_INTERVAL)

    except KeyboardInterrupt:
        disconnect()


def main():
    # Initialize InfluxDB — creates the database "sensor_data" if it doesn't exist yet
    init_db()

    # Start async batch InfluxDB writer thread
    # Drains influx_queue in the background without blocking the sensor loop
    # Uses batch writes for maximum throughput
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