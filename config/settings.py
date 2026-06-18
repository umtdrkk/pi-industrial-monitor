# --- MQTT settings ---

# Address of the MQTT broker (the message server). "localhost" means it's running
# on this same machine.
MQTT_BROKER = "localhost"

# Standard MQTT port (unencrypted)
MQTT_PORT = 1883

# Prefix used for all MQTT topics, e.g. "factory/sensor/1", "factory/sensor/2", etc.
MQTT_TOPIC_PREFIX = "factory/sensor"


# --- OPC UA settings ---

# Network address OPC UA clients will use to connect to our server.
# "0.0.0.0" means it listens on all network interfaces, port 4840 is the OPC UA default.
OPCUA_ENDPOINT = "opc.tcp://0.0.0.0:4840/factory/"

# A unique URI identifying our namespace (doesn't need to be a real website,
# just needs to be unique to avoid clashing with other OPC UA servers)
OPCUA_NAMESPACE = "http://yourfactory.com"


# --- General settings ---

# Total number of sensors (informational/reference - not used directly by the loops above)
NUM_SENSORS = 10

# How many seconds to wait between each round of sensor readings
SENSOR_READ_INTERVAL = 1.0

# Flag: False = running on a normal computer (use fake/random sensor data)
#       True  = running on the actual Raspberry Pi (read real hardware via SPI)
RUNNING_ON_PI = False


# --- Sensor channel definitions ---
# Each dictionary describes one sensor:
#   "id"   - unique channel number (matches ADC channel / MQTT topic / OPC UA node)
#   "type" - "voltage" or "current", determines how the raw ADC value is interpreted
#   "name" - name shown in OPC UA and logs
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