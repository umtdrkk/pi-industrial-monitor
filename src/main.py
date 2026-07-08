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

    # Create a separate thread to run the MQTT loop so it doesn't block the OPC UA server
    # "daemon=True" means this thread automatically stops when the main program exits
    mqtt_thread = threading.Thread(target=mqtt_loop, daemon=True)
    mqtt_thread.start()

    # Run the OPC UA server on the main thread
    # We pass read_sensors so it can grab the latest readings whenever needed
    # asyncio.run() starts and manages the async event loop
    asyncio.run(start_opcua_server(read_sensors))


if __name__ == "__main__":
    main()