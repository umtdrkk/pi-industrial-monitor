import asyncio
from asyncua import Server
from config.settings import OPCUA_ENDPOINT, OPCUA_NAMESPACE, SENSOR_CHANNELS

async def start_opcua_server(get_readings_fn):
    server = Server()
    await server.init()
    server.set_endpoint(OPCUA_ENDPOINT)

    uri = OPCUA_NAMESPACE
    idx = await server.register_namespace(uri)

    factory = await server.nodes.objects.add_object(idx, "Factory")

    nodes = {}
    for channel in SENSOR_CHANNELS:
        sensor_obj = await factory.add_object(idx, channel["name"])
        value_node = await sensor_obj.add_variable(idx, "Value", 0.0)
        unit_node  = await sensor_obj.add_variable(idx, "Unit", channel["type"])
        await value_node.set_writable()
        nodes[channel["id"]] = value_node

    print(f"OPC UA server running at {OPCUA_ENDPOINT}")

    async with server:
        while True:
            readings = get_readings_fn()
            for reading in readings:
                await nodes[reading["id"]].write_value(float(reading["value"]))
            await asyncio.sleep(1)