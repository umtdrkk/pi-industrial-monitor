import asyncio
import threading
import time
from src.sensors import read_sensors
from src.mqtt_client import connect, publish, disconnect
from src.opcua_server import start_opcua_server
from config.settings import SENSOR_READ_INTERVAL

def mqtt_loop():
    connect()
    try:
        while True:
            readings = read_sensors()
            publish(readings)
            time.sleep(SENSOR_READ_INTERVAL)
    except KeyboardInterrupt:
        disconnect()

def main():
    mqtt_thread = threading.Thread(target=mqtt_loop, daemon=True)
    mqtt_thread.start()

    asyncio.run(start_opcua_server(read_sensors))

if __name__ == "__main__":
    main()