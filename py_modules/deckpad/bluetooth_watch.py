"""Notices when Bluetooth goes away while controller mode is on.

bluetoothd drops every registration (application, advertisement, agent) when it exits or when the
adapter disappears, and a powered-off adapter carries no links, so the session's state no longer
means anything. The watch uses its own bus connection, so it keeps working whatever happens to the
session's.
"""

import logging

from dbus_fast import BusType, Message, MessageType
from dbus_fast.aio import MessageBus

from . import bluez, errors

log = logging.getLogger("deckpad.bluetooth_watch")

SERVICE_STOPPED = "service_stopped"
POWERED_OFF = "powered_off"
ADAPTER_REMOVED = "adapter_removed"


class BluetoothWatch:
    def __init__(self, on_lost):
        """`on_lost(reason)` is called once, synchronously, with one of the reasons above."""
        self._on_lost = on_lost
        self._bus = None
        self._adapter_path = None
        self._fired = False

    async def start(self):
        """Raises ControllerModeError if the adapter is already gone."""
        try:
            self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        except Exception as e:
            raise errors.bluetooth_unavailable(repr(e)) from e
        try:
            self._bus.add_message_handler(self._on_message)
            for rule in (
                "type='signal',sender='org.freedesktop.DBus',member='NameOwnerChanged',arg0='%s'" % bluez.SERVICE,
                "type='signal',sender='%s',interface='org.freedesktop.DBus.ObjectManager',member='InterfacesRemoved'"
                % bluez.SERVICE,
                "type='signal',sender='%s',interface='org.freedesktop.DBus.Properties',"
                "member='PropertiesChanged',arg0='%s'" % (bluez.SERVICE, bluez.ADAPTER),
            ):
                await _add_match(self._bus, rule)
            # Read the state only after subscribing, so a change in between is not missed.
            self._adapter_path, adapter = await bluez.find_adapter(self._bus)
        except BaseException:
            self.stop()
            raise
        if not adapter.get("Powered"):
            self.stop()
            raise errors.bluetooth_off()

    def stop(self):
        """Synchronous and safe to call more than once."""
        self._fired = True
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None

    def _on_message(self, msg):
        if msg.message_type != MessageType.SIGNAL or self._fired:
            return False
        if msg.member == "NameOwnerChanged" and msg.body[0] == bluez.SERVICE and not msg.body[2]:
            self._lost(SERVICE_STOPPED)
        elif msg.member == "InterfacesRemoved" and msg.body[0] == self._adapter_path and bluez.ADAPTER in msg.body[1]:
            self._lost(ADAPTER_REMOVED)
        elif (
            msg.member == "PropertiesChanged"
            and msg.path == self._adapter_path
            and msg.body[0] == bluez.ADAPTER
            and "Powered" in msg.body[1]
            and not msg.body[1]["Powered"].value
        ):
            self._lost(POWERED_OFF)
        return False

    def _lost(self, reason):
        self._fired = True
        log.warning("Bluetooth went away underneath Controller Mode (%s)", reason)
        try:
            self._on_lost(reason)
        except Exception:
            log.exception("Bluetooth loss handler failed")


async def _add_match(bus, rule):
    reply = await bus.call(
        Message(
            destination="org.freedesktop.DBus",
            path="/org/freedesktop/DBus",
            interface="org.freedesktop.DBus",
            member="AddMatch",
            signature="s",
            body=[rule],
        )
    )
    if reply.message_type == MessageType.ERROR:
        raise bluez.BluezError(reply.error_name, reply.body[0] if reply.body else "")
