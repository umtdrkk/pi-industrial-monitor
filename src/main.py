# asyncio - needed to run the OPC UA server (which is async)
import asyncio

# threading - lets us run multiple things "at the same time" in one program
import threading

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


def mqtt_loop():
    # This function runs in its own thread, handling the MQTT side of things
    connect()

    try:
        # Loop forever: read sensors, publish to MQTT, write to InfluxDB, wait, repeat
        while True:
            readings = read_sensors()

            # Publish all readings to MQTT broker so the dashboard receives them live
            # publish() handles looping through each sensor internally
            publish(readings)

            # Write each reading individually to InfluxDB for persistent historical storage
            # This is what allows us to query averages over 1h, 24h, 7d later
            for reading in readings:
                write_reading(reading)

            time.sleep(SENSOR_READ_INTERVAL)

    except KeyboardInterrupt:
        # If the program is stopped (Ctrl+C), disconnect cleanly
        disconnect()


def main():
    # Initialize InfluxDB — creates the database "sensor_data" if it doesn't exist yet
    # This runs once at startup before anything else starts
    init_db()

    # Start Flask API server in background thread
    # Serves historical data endpoints on port 5000
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    # Start MQTT loop in background thread so it doesn't block the OPC UA server
    # "daemon=True" means this thread automatically stops when the main program exits
    mqtt_thread = threading.Thread(target=mqtt_loop, daemon=True)
    mqtt_thread.start()

    # Run the OPC UA server on the main thread
    # We pass read_sensors so it can grab the latest readings whenever needed
    # asyncio.run() starts and manages the async event loop
    asyncio.run(start_opcua_server(read_sensors))


if __name__ == "__main__":
    main()