MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC_PREFIX = "factory/sensor"

OPCUA_ENDPOINT = "opc.tcp://0.0.0.0:4840/factory/"
OPCUA_NAMESPACE = "http://yourfactory.com"

SENSOR_READ_INTERVAL = 1.0

RUNNING_ON_PI = False

# Each sensor needs: id, type (voltage/current), name, category
# category drives which visual the dashboard picks automatically:
#   "distance" → gauge
#   "pressure" → line chart
#   "temperature" → line chart
#   anything else → line chart (default)
SENSOR_CHANNELS = [
    {"id": 1, "type": "voltage", "name": "Distanzsensor", "category": "distance"},
    {"id": 2, "type": "current", "name": "Drucksensor (0-1 bar)", "category": "pressure"},
]

NUM_SENSORS = len(SENSOR_CHANNELS)