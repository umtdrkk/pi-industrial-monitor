import paho.mqtt.client as mqtt
from config.settings import MQTT_BROKER, MQTT_PORT, MQTT_TOPIC_PREFIX
import json

client = mqtt.Client()

def connect():
    client.connect(MQTT_BROKER, MQTT_PORT)
    client.loop_start()
    print(f"Connected to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")

def publish(readings):
    for reading in readings:
        topic = f"{MQTT_TOPIC_PREFIX}/{reading['id']}"
        payload = json.dumps(reading)
        client.publish(topic, payload)
        print(f"Published to {topic}: {payload}")

def disconnect():
    client.loop_stop()
    client.disconnect()