# Flask - lightweight web framework for building the API server
from flask import Flask, jsonify

# flask_cors - allows the dashboard (port 8080) to call this API (port 5000)
# without the browser blocking it for security reasons (CORS policy)
from flask_cors import CORS

# Import our InfluxDB query functions
from src.influx_client import query_average, query_history

# Import sensor config so we know which sensors exist
from config.settings import SENSOR_CHANNELS

# Create the Flask app
app = Flask(__name__)

# Enable CORS for all routes — allows dashboard to call this API
CORS(app)


@app.route('/api/sensors', methods=['GET'])
def get_sensors():
    """
    Returns the list of all configured sensors.
    Dashboard uses this to know which sensors exist and their names/types.
    """
    return jsonify(SENSOR_CHANNELS)


@app.route('/api/sensors/<int:sensor_id>/average', methods=['GET'])
def get_average(sensor_id):
    """
    Returns average values for a sensor over multiple time ranges.
    Example: GET /api/sensors/1/average
    Returns averages for 1min, 10min, 1h, 24h, 7d
    """
    # Define all the time ranges we want to support
    time_ranges = {
        "1min":  "1m",
        "10min": "10m",
        "1h":    "1h",
        "24h":   "24h",
        "7d":    "7d",
    }

    # Query InfluxDB for each time range
    averages = {}
    for label, influx_range in time_ranges.items():
        avg = query_average(str(sensor_id), influx_range)
        averages[label] = avg

    return jsonify({
        "sensor_id": sensor_id,
        "averages": averages
    })


@app.route('/api/sensors/<int:sensor_id>/history/<time_range>', methods=['GET'])
def get_history(sensor_id, time_range):
    """
    Returns raw historical data points for a sensor over a given time range.
    Example: GET /api/sensors/1/history/1h
    Valid time ranges: 1m, 10m, 1h, 24h, 7d
    """
    # Map friendly names to InfluxDB format
    valid_ranges = {
        "1min":  "1m",
        "10min": "10m",
        "1h":    "1h",
        "24h":   "24h",
        "7d":    "7d",
    }

    # Validate the requested time range
    influx_range = valid_ranges.get(time_range)
    if not influx_range:
        return jsonify({"error": f"Invalid time range. Use one of: {list(valid_ranges.keys())}"}), 400

    # Query InfluxDB for historical data points
    history = query_history(str(sensor_id), influx_range)

    return jsonify({
        "sensor_id": sensor_id,
        "time_range": time_range,
        "count": len(history),
        "data": history
    })


@app.route('/api/health', methods=['GET'])
def health():
    """
    Simple health check endpoint.
    GET /api/health → confirms Flask is running
    """
    return jsonify({"status": "ok"})


def start_flask():
    """
    Starts the Flask server on port 5000.
    Runs in debug=False so it doesn't interfere with threading.
    """
    app.run(host='0.0.0.0', port=5001, debug=False)
