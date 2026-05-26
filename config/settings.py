MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC_PREFIX = "factory/sensor"

OPCUA_ENDPOINT = "opc.tcp://0.0.0.0:4840/factory/"
OPCUA_NAMESPACE = "http://yourfactory.com"

NUM_SENSORS = 10
SENSOR_READ_INTERVAL = 1.0

RUNNING_ON_PI = False

SENSOR_CHANNELS = [
    {"id": 1,  "type": "voltage",  "name": "Sensor 1"},
    {"id": 2,  "type": "voltage",  "name": "Sensor 2"},
    {"id": 3,  "type": "voltage",  "name": "Sensor 3"},
    {"id": 4,  "type": "voltage",  "name": "Sensor 4"},
    {"id": 5,  "type": "voltage",  "name": "Sensor 5"},
    {"id": 6,  "type": "voltage",  "name": "Sensor 6"},
    {"id": 7,  "type": "voltage",  "name": "Sensor 7"},
    {"id": 8,  "type": "voltage",  "name": "Sensor 8"},
    {"id": 9,  "type": "current",  "name": "Sensor 9"},
    {"id": 10, "type": "current",  "name": "Sensor 10"},
]