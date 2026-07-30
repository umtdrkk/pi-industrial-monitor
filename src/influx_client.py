import socket
from influxdb import InfluxDBClient

DB_NAME = "sensor_data"

# ── HTTP CLIENT (for reads and init) ─────────────────────────────────────────
# Used for: init_db(), query_average(), query_history()
# HTTP is fine for queries — they're infrequent and need reliable responses
client = InfluxDBClient(host="localhost", port=8086)

# ── UDP SOCKET (for writes) ───────────────────────────────────────────────────
# Used for: write_reading_udp()
# UDP is fire-and-forget — no TCP handshake, no HTTP overhead, ~0.1ms per write
# vs HTTP which takes ~20ms per write (200x faster)
# Requires InfluxDB UDP listener enabled in /etc/influxdb/influxdb.conf:
#   [[udp]]
#     enabled = true
#     bind-address = ":8089"
#     database = "sensor_data"
_udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_udp_addr = ('localhost', 8089)


def init_db():
    """
    Creates the InfluxDB database if it doesn't exist yet.
    Called once at startup before any writes happen.
    Uses HTTP client — reliability matters here.
    """
    databases = [db["name"] for db in client.get_list_database()]
    if DB_NAME not in databases:
        client.create_database(DB_NAME)
    client.switch_database(DB_NAME)
    print(f"InfluxDB connected — database: {DB_NAME}")


def write_reading(reading):
    """
    Writes a single sensor reading to InfluxDB via HTTP.
    Kept for compatibility and fallback — used by the batch writer in main.py.
    For high-frequency writes, use write_reading_udp() instead.
    """
    point = [
        {
            "measurement": "sensor",
            "tags": {
                "sensor_id": str(reading["id"]),
                "sensor_name": reading["name"],
                "sensor_type": reading["type"],
                "category": reading.get("category", "default"),
            },
            "fields": {
                "value": float(reading["value"]),
                "unit": reading["unit"],
            }
        }
    ]
    client.write_points(point)


def write_reading_udp(reading):
    """
    Writes a single sensor reading to InfluxDB via UDP line protocol.

    UDP = fire and forget:
        No TCP handshake, no HTTP overhead, no waiting for confirmation.
        ~0.1ms per write vs ~20ms for HTTP → 200x faster.

    InfluxDB line protocol format:
        measurement,tag1=val1,tag2=val2 field1=val1,field2=val2

    Tradeoff:
        Occasional packets may be lost (UDP has no delivery guarantee).
        At 100Hz, losing 1 reading per second is completely acceptable —
        the next reading arrives 10ms later anyway.

    Requires UDP listener enabled in /etc/influxdb/influxdb.conf.
    """
    # Build InfluxDB line protocol string
    # Format: measurement,tags fields
    # Note: string field values must be quoted, numeric values unquoted
    line = (
        f"sensor,"
        f"sensor_id={reading['id']},"
        f"sensor_name={reading['name'].replace(' ', '\\ ')},"
        f"sensor_type={reading['type']},"
        f"category={reading.get('category', 'default')} "
        f"value={float(reading['value'])},"
        f"unit=\"{reading['unit']}\""
    )

    try:
        # Send UDP datagram — returns instantly, no waiting
        _udp_sock.sendto(line.encode('utf-8'), _udp_addr)
    except Exception as e:
        # UDP send failed (very rare) — log and continue
        print(f"[InfluxDB UDP] Send error: {e}")


def query_average(sensor_id, time_range):
    """
    Returns the mean value for a sensor over a given time range.
    time_range examples: "1min", "10min", "1h", "24h", "7d"
    Uses HTTP client — queries are infrequent and need reliable results.
    """
    query = f'''
        SELECT MEAN("value") FROM "sensor"
        WHERE "sensor_id" = '{sensor_id}'
        AND time >= now() - {time_range}
    '''
    result = client.query(query)
    points = list(result.get_points())
    if points and points[0]["mean"] is not None:
        return round(points[0]["mean"], 3)
    return None


def query_history(sensor_id, time_range):
    """
    Returns all raw readings for a sensor over a given time range.
    Used by Flask API for historical chart data in the dashboard.
    Uses HTTP client — queries are infrequent and need reliable results.
    """
    query = f'''
        SELECT "value", "unit" FROM "sensor"
        WHERE "sensor_id" = '{sensor_id}'
        AND time >= now() - {time_range}
        ORDER BY time ASC
    '''
    result = client.query(query)
    return list(result.get_points())