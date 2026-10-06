"""The Deck's Bluetooth Peripheral role: everything DeckPad registers with BlueZ for one Controller Mode session.

Each session owns its own system-bus connection. BlueZ binds every registration to the connection
that made it, so closing the connection is the backstop that releases anything a failed or
interrupted teardown left behind.
"""

import logging

from dbus_fast import BusType
from dbus_fast.aio import MessageBus

from . import bluez, errors, gatt, identity
from .agent import CAPABILITY, PairingAgent

log = logging.getLogger("deckpad.peripheral")

APP_PATH = "/io/github/thedavidweng/deckpad/app"
AGENT_PATH = "/io/github/thedavidweng/deckpad/agent"


def build_application():
    app = gatt.Application(APP_PATH)
    dis = app.add_service(gatt.uuid16("180a"))
    dis.add_characteristic(gatt.uuid16("2a50"), ["read"], identity.PNP_ID)
    return app


class Peripheral:
    def __init__(self):
        self._bus = None
        self._adapter_path = None
        # Teardown steps for what has been registered so far, run newest first. Later
        # registrations (advertisement, connected Hosts) therefore unwind before the application
        # and the agent.
        self._undo = []

    async def start(self):
        """Register DeckPad with BlueZ. On failure, undo whatever was registered and raise ControllerModeError."""
        try:
            await self._start()
        except BaseException:
            await self.stop()
            raise

    async def _start(self):
        try:
            self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        except Exception as e:
            raise errors.bluetooth_unavailable(repr(e)) from e

        self._adapter_path, adapter = await bluez.find_adapter(self._bus)
        if not adapter.get("Powered"):
            raise errors.bluetooth_off()

        bus = self._bus
        try:
            agent = PairingAgent()
            bus.export(AGENT_PATH, agent)
            await bluez.register_agent(bus, AGENT_PATH, CAPABILITY)
            self._undo.append(("unregister agent", lambda: bluez.unregister_agent(bus, AGENT_PATH)))
            await bluez.request_default_agent(bus, AGENT_PATH)

            app = build_application()
            app.export(bus)
            adapter_path = self._adapter_path
            await bluez.register_application(bus, adapter_path, APP_PATH)
            self._undo.append(
                ("unregister application", lambda: bluez.unregister_application(bus, adapter_path, APP_PATH))
            )
        except bluez.BluezError as e:
            if e.service_unavailable:
                raise errors.bluetooth_unavailable(str(e)) from e
            raise errors.start_failed(str(e)) from e

    async def stop(self):
        """Undo every registration in reverse order, then close the bus connection. Safe to call repeatedly."""
        while self._undo:
            label, step = self._undo.pop()
            try:
                await step()
            except Exception as e:
                log.warning("Teardown step %r failed: %r", label, e)
        self.close()

    def close(self):
        """Drop the bus connection immediately; BlueZ then releases anything still registered."""
        self._undo.clear()
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
