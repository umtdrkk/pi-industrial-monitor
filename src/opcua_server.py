# asyncio lets Python run code asynchronously (handle multiple tasks without blocking)
import asyncio

# Server class from asyncua creates an OPC UA server (industrial communication standard)
from asyncua import Server

# Import settings: server address, namespace URI, and list of sensor channel configs
from config.settings import OPCUA_ENDPOINT, OPCUA_NAMESPACE, SENSOR_CHANNELS

# This function starts the OPC UA server. "get_readings_fn" is a function we pass in
# that returns the latest sensor readings whenever we call it.
async def start_opcua_server(get_readings_fn):
    # Create a new OPC UA server instance
    server = Server()

    # Set up the server's internal structures (must be done before configuring it)
    await server.init()

    # Set the network address clients will connect to (e.g. opc.tcp://0.0.0.0:4840)
    server.set_endpoint(OPCUA_ENDPOINT)

    # Register our own "namespace" - a unique identifier so our nodes don't clash
    # with nodes from other applications. idx is a number representing our namespace.
    uri = OPCUA_NAMESPACE
    idx = await server.register_namespace(uri)

    # Create a top-level folder/object called "Factory" under the server's default Objects node
    factory = await server.nodes.objects.add_object(idx, "Factory")

    # Dictionary to keep track of each sensor's "Value" node so we can update it later
    nodes = {}

    # For every sensor channel defined in settings, create its structure in the OPC UA tree
    for channel in SENSOR_CHANNELS:
        # Create a sub-object for this sensor, e.g. Factory/Temperature1
        sensor_obj = await factory.add_object(idx, channel["name"])

        # Add a "Value" variable node, starting at 0.0 - this will hold the live reading
        value_node = await sensor_obj.add_variable(idx, "Value", 0.0)

        # Add a "Unit" variable node showing the type/unit of measurement (e.g. "°C")
        unit_node  = await sensor_obj.add_variable(idx, "Unit", channel["type"])

        # Allow OPC UA clients to write to the Value node (not just read it)
        await value_node.set_writable()

        # Save a reference to this sensor's Value node, keyed by its ID, for quick access later
        nodes[channel["id"]] = value_node

    print(f"OPC UA server running at {OPCUA_ENDPOINT}")

    # Start the server (runs setup/teardown automatically via "async with")
    async with server:
        # Run forever, continuously updating sensor values
        while True:
            # Get the latest readings (calls the function passed into this server)
            readings = get_readings_fn()

            # For each reading, find its matching node and update its value
            for reading in readings:
                await nodes[reading["id"]].write_value(float(reading["value"]))

            # Wait 1 second before updating again (so we don't spam updates)
            await asyncio.sleep(1)