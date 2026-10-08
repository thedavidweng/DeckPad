"""Thin client calls into bluetoothd's org.bluez D-Bus API.

Calls are sent as explicit messages rather than through introspected proxies, so each call is one
round trip and does not depend on BlueZ's introspection data.
"""

import contextlib

from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus

from . import errors

SERVICE = "org.bluez"
AGENT_MANAGER_PATH = "/org/bluez"

ADAPTER = "org.bluez.Adapter1"
AGENT_MANAGER = "org.bluez.AgentManager1"
GATT_MANAGER = "org.bluez.GattManager1"
LE_ADVERTISING_MANAGER = "org.bluez.LEAdvertisingManager1"
DEVICE = "org.bluez.Device1"

_UNAVAILABLE = {
    "org.freedesktop.DBus.Error.ServiceUnknown",
    "org.freedesktop.DBus.Error.NameHasNoOwner",
    "org.freedesktop.DBus.Error.NoReply",
}


class BluezError(Exception):
    def __init__(self, name, text):
        super().__init__("%s: %s" % (name, text))
        self.name = name
        self.text = text

    @property
    def service_unavailable(self):
        return self.name in _UNAVAILABLE


@contextlib.asynccontextmanager
async def temporary_connection():
    """A system bus connection for one piece of work while controller mode is off, closed afterwards."""
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        yield bus
    finally:
        bus.disconnect()


async def call(bus, path, interface, member, signature="", body=()):
    reply = await bus.call(
        Message(
            destination=SERVICE,
            path=path,
            interface=interface,
            member=member,
            signature=signature,
            body=list(body),
        )
    )
    if reply.message_type == MessageType.ERROR:
        raise BluezError(reply.error_name, reply.body[0] if reply.body else "")
    return reply.body


async def _bus_daemon_call(bus, member, arg):
    reply = await bus.call(
        Message(
            destination="org.freedesktop.DBus",
            path="/org/freedesktop/DBus",
            interface="org.freedesktop.DBus",
            member=member,
            signature="s",
            body=[arg],
        )
    )
    if reply.message_type == MessageType.ERROR:
        raise BluezError(reply.error_name, reply.body[0] if reply.body else "")
    return reply.body


async def add_match(bus, rule):
    await _bus_daemon_call(bus, "AddMatch", rule)


def adapter_index(adapter_path):
    """The kernel's index (the N in hciN) for an adapter object path, or None if it has none."""
    name = (adapter_path or "").rsplit("/", 1)[-1]
    if name.startswith("hci") and name[3:].isdigit():
        return int(name[3:])
    return None


async def find_adapter(bus):
    """Return (path, properties) of the first Bluetooth adapter BlueZ knows about."""
    try:
        objects = await managed_objects(bus)
    except BluezError as e:
        if e.service_unavailable:
            raise errors.bluetooth_unavailable(str(e)) from e
        raise errors.start_failed(str(e)) from e
    for path in sorted(objects):
        interfaces = objects[path]
        if ADAPTER in interfaces and GATT_MANAGER in interfaces:
            return path, {k: _unwrap(v) for k, v in interfaces[ADAPTER].items()}
    raise errors.no_adapter()


async def register_agent(bus, path, capability):
    await call(bus, AGENT_MANAGER_PATH, AGENT_MANAGER, "RegisterAgent", "os", (path, capability))


async def request_default_agent(bus, path):
    await call(bus, AGENT_MANAGER_PATH, AGENT_MANAGER, "RequestDefaultAgent", "o", (path,))


async def unregister_agent(bus, path):
    await call(bus, AGENT_MANAGER_PATH, AGENT_MANAGER, "UnregisterAgent", "o", (path,))


async def register_application(bus, adapter_path, app_path):
    await call(bus, adapter_path, GATT_MANAGER, "RegisterApplication", "oa{sv}", (app_path, {}))


async def unregister_application(bus, adapter_path, app_path):
    await call(bus, adapter_path, GATT_MANAGER, "UnregisterApplication", "o", (app_path,))


async def register_advertisement(bus, adapter_path, adv_path):
    await call(bus, adapter_path, LE_ADVERTISING_MANAGER, "RegisterAdvertisement", "oa{sv}", (adv_path, {}))


async def unregister_advertisement(bus, adapter_path, adv_path):
    await call(bus, adapter_path, LE_ADVERTISING_MANAGER, "UnregisterAdvertisement", "o", (adv_path,))


async def disconnect_device(bus, device_path):
    await call(bus, device_path, DEVICE, "Disconnect")


async def remove_device(bus, adapter_path, device_path):
    """Remove a device and its bond from the adapter, disconnecting it first if needed."""
    await call(bus, adapter_path, ADAPTER, "RemoveDevice", "o", (device_path,))


def send_disconnect_device(bus, device_path):
    """Ask bluetoothd to drop a device's link without waiting for the reply.

    dbus-fast writes straight to the socket when nothing else is queued, so this is on the wire
    before the caller closes the connection, and the daemon delivers it to bluetoothd ahead of the
    disconnect notice.
    """
    bus.send(Message(destination=SERVICE, path=device_path, interface=DEVICE, member="Disconnect"))


async def watch_devices(bus):
    """Do this before reading current state, or a host that connects in between is missed."""
    for rule in (
        "type='signal',sender='%s',interface='org.freedesktop.DBus.ObjectManager'" % SERVICE,
        "type='signal',sender='%s',interface='org.freedesktop.DBus.Properties',"
        "member='PropertiesChanged',arg0='%s'" % (SERVICE, DEVICE),
    ):
        await add_match(bus, rule)


async def service_pid(bus):
    """PID of the process that owns org.bluez (bluetoothd)."""
    (pid,) = await _bus_daemon_call(bus, "GetConnectionUnixProcessID", SERVICE)
    return pid


async def managed_objects(bus):
    (objects,) = await call(bus, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    return objects


def device_properties(props):
    return {k: _unwrap(v) for k, v in props.items()}


def _unwrap(value):
    return value.value if isinstance(value, Variant) else value
