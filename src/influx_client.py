from influxdb import InfluxDBClient

DB_NAME = "sensor_data"

client = InfluxDBClient(host="localhost", port=8086)

def init_db():
    databases = [db["name"] for db in client.get_list_database()]
    if DB_NAME not in databases:
        client.create_database(DB_NAME)
    client.switch_database(DB_NAME)
    print(f"InfluxDB connected — database: {DB_NAME}")

def write_reading(reading):
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

def query_average(sensor_id, time_range):
    # time_range: "1h", "24h", "7d"
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
    query = f'''
        SELECT "value", "unit" FROM "sensor"
        WHERE "sensor_id" = '{sensor_id}'
        AND time >= now() - {time_range}
        ORDER BY time ASC
    '''
    result = client.query(query)
    return list(result.get_points())
