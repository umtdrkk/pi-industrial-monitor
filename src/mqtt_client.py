# Import the MQTT client library (paho-mqtt) - lets us talk to an MQTT broker
import paho.mqtt.client as mqtt

# Import settings from another file (broker address, port, topic prefix)
from config.settings import MQTT_BROKER, MQTT_PORT, MQTT_TOPIC_PREFIX

# json is used to convert Python dictionaries into text (JSON format) for sending
import json

# Create an MQTT client object - this is our connection to the broker
client = mqtt.Client()

def connect():
    # Connect to the MQTT broker using the address and port from settings
    client.connect(MQTT_BROKER, MQTT_PORT)

    # Start a background thread that handles network traffic automatically
    # (without this, the client won't send/receive messages properly)
    client.loop_start()

    print(f"Connected to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")

def publish(readings):
    # Loop through each sensor reading in the list
    for reading in readings:
        # Build the topic name, e.g. "sensors/temperature1"
        topic = f"{MQTT_TOPIC_PREFIX}/{reading['id']}"

        # Convert the reading (a dict) into a JSON string, since MQTT sends text/bytes
        payload = json.dumps(reading)

        # Send (publish) the message to the broker on the given topic
        client.publish(topic, payload)

        print(f"Published to {topic}: {payload}")

def disconnect():
    # Stop the background network thread
    client.loop_stop()

    # Close the connection to the broker cleanly
    client.disconnect()