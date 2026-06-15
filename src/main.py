# asyncio - needed to run the OPC UA server (which is async)
import asyncio

# threading - lets us run multiple things "at the same time" in one program
import threading

# time - used for the sleep/delay between sensor reads
import time

# Import our own modules: sensor reading, MQTT functions, and the OPC UA server
from src.sensors import read_sensors
from src.mqtt_client import connect, publish, disconnect
from src.opcua_server import start_opcua_server

# Import the configured delay (in seconds) between sensor reads
from config.settings import SENSOR_READ_INTERVAL


def mqtt_loop():
    # This function runs in its own thread, handling the MQTT side of things
    connect()

    try:
        # Loop forever: read sensors, publish to MQTT, wait, repeat
        while True:
            readings = read_sensors()
            publish(readings)
            time.sleep(SENSOR_READ_INTERVAL)

    except KeyboardInterrupt:
        # If the program is stopped (Ctrl+C), disconnect cleanly
        disconnect()


def main():
    # Create a separate thread to run the MQTT loop, so it doesn't block the OPC UA server.
    # "daemon=True" means this thread will automatically stop when the main program exits.
    mqtt_thread = threading.Thread(target=mqtt_loop, daemon=True)
    mqtt_thread.start()

    # Run the OPC UA server on the main thread.
    # We pass it "read_sensors" so it can grab the latest readings whenever it needs them.
    # asyncio.run() starts and manages the async event loop.
    asyncio.run(start_opcua_server(read_sensors))


if __name__ == "__main__":
    main()