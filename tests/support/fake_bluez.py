"""A stand-in for bluetoothd's org.bluez D-Bus API, observed from BlueZ's side.

It models only the contract DeckPad relies on, the way BlueZ 5.83 behaves on the Deck:
- AgentManager1 keeps a stack of default agents. Steam's agent is already the default.
- GattManager1.RegisterApplication calls back GetManagedObjects on the application and
  rejects one that exposes no GATT service.
- Registrations are bound to the registering D-Bus connection and vanish with it.
"""

import asyncio

from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import PropertyAccess, ServiceInterface, dbus_property

STEAM_AGENT = ("steam", "/steam/agent")
ADAPTER_PATH = "/org/bluez/hci0"

_FAILED = "org.bluez.Error.Failed"
_ALREADY_EXISTS = "org.bluez.Error.AlreadyExists"
_DOES_NOT_EXIST = "org.bluez.Error.DoesNotExist"


class _Adapter(ServiceInterface):
    def __init__(self, powered):
        super().__init__("org.bluez.Adapter1")
        self.powered = powered

    @dbus_property(access=PropertyAccess.READ)
    def Address(self) -> "s":
        return "E8:FB:1C:43:F3:44"

    @dbus_property(access=PropertyAccess.READ)
    def Powered(self) -> "b":
        return self.powered


class _Marker(ServiceInterface):
    """An interface with no members, so it shows up in GetManagedObjects."""


class FakeBluez:
    def __init__(self, adapter=True, powered=True):
        self._has_adapter = adapter
        self._adapter = _Adapter(powered)
        self.bus = None
        self.agents = {}
        self.default_agents = [STEAM_AGENT]
        self.applications = {}
        self.advertisements = {}
        self.hang_unregister = False
        self.reject_application = None

    @property
    def default_agent(self):
        return self.default_agents[-1]

    def registrations(self):
        """Everything any client currently has registered with BlueZ, besides Steam's agent."""
        return {
            "agents": dict(self.agents),
            "default_agents": [a for a in self.default_agents if a != STEAM_AGENT],
            "applications": dict(self.applications),
            "advertisements": dict(self.advertisements),
        }

    def is_clean(self):
        return self.default_agent == STEAM_AGENT and not any(self.registrations().values())

    async def wait_until_clean(self, timeout=2.0):
        """BlueZ releases a disconnected client's registrations once the bus reports it gone."""
        deadline = asyncio.get_running_loop().time() + timeout
        while not self.is_clean() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        return self.is_clean()

    async def start(self):
        self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        self.bus.export("/org/bluez", _Marker("org.bluez.AgentManager1"))
        if self._has_adapter:
            self.bus.export(ADAPTER_PATH, self._adapter)
            self.bus.export(ADAPTER_PATH, _Marker("org.bluez.GattManager1"))
            self.bus.export(ADAPTER_PATH, _Marker("org.bluez.LEAdvertisingManager1"))
        self.bus.add_message_handler(self._handle)
        await self.bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=["type='signal',sender='org.freedesktop.DBus',member='NameOwnerChanged'"],
            )
        )
        await self.bus.request_name("org.bluez")

    async def stop(self):
        if self.bus:
            self.bus.disconnect()
            await self.bus.wait_for_disconnect()
            self.bus = None

    def _handle(self, msg):
        if msg.message_type == MessageType.SIGNAL and msg.member == "NameOwnerChanged":
            name, _old, new = msg.body
            if name.startswith(":") and not new:
                self._drop_client(name)
            return False
        if msg.message_type != MessageType.METHOD_CALL:
            return False
        handler = {
            ("org.bluez.AgentManager1", "RegisterAgent"): self._register_agent,
            ("org.bluez.AgentManager1", "RequestDefaultAgent"): self._request_default_agent,
            ("org.bluez.AgentManager1", "UnregisterAgent"): self._unregister_agent,
            ("org.bluez.GattManager1", "RegisterApplication"): self._register_application,
            ("org.bluez.GattManager1", "UnregisterApplication"): self._unregister_application,
            ("org.bluez.LEAdvertisingManager1", "RegisterAdvertisement"): self._register_advertisement,
            ("org.bluez.LEAdvertisingManager1", "UnregisterAdvertisement"): self._unregister_advertisement,
        }.get((msg.interface, msg.member))
        if handler is None:
            return False
        asyncio.get_running_loop().create_task(self._reply(msg, handler))
        return True

    async def _reply(self, msg, handler):
        try:
            error = await handler(msg.sender, msg)
        except asyncio.CancelledError:
            raise
        if error:
            self.bus.send(Message.new_error(msg, error[0], error[1]))
        else:
            self.bus.send(Message.new_method_return(msg))

    def _drop_client(self, sender):
        for table in (self.agents, self.applications, self.advertisements):
            for key in [k for k in table if k[0] == sender]:
                del table[key]
        self.default_agents = [a for a in self.default_agents if a[0] != sender]

    async def _register_agent(self, sender, msg):
        key = (sender, msg.body[0])
        if key in self.agents:
            return _ALREADY_EXISTS, "Already Exists"
        self.agents[key] = msg.body[1]

    async def _request_default_agent(self, sender, msg):
        key = (sender, msg.body[0])
        if key not in self.agents:
            return _DOES_NOT_EXIST, "Does Not Exist"
        if key in self.default_agents:
            self.default_agents.remove(key)
        self.default_agents.append(key)

    async def _unregister_agent(self, sender, msg):
        if self.hang_unregister:
            await asyncio.sleep(3600)
        key = (sender, msg.body[0])
        if key not in self.agents:
            return _DOES_NOT_EXIST, "Does Not Exist"
        del self.agents[key]
        if key in self.default_agents:
            self.default_agents.remove(key)

    async def _register_application(self, sender, msg):
        if not self._has_adapter or msg.path != ADAPTER_PATH:
            return "org.freedesktop.DBus.Error.UnknownObject", "No adapter"
        key = (sender, msg.body[0])
        if key in self.applications:
            return _ALREADY_EXISTS, "Already Exists"
        if self.reject_application:
            return _FAILED, self.reject_application
        reply = await self.bus.call(
            Message(
                destination=sender,
                path=msg.body[0],
                interface="org.freedesktop.DBus.ObjectManager",
                member="GetManagedObjects",
            )
        )
        if reply.message_type != MessageType.METHOD_RETURN:
            return _FAILED, "Failed to read application objects"
        objects = reply.body[0]
        if not any("org.bluez.GattService1" in ifaces for ifaces in objects.values()):
            return _FAILED, "No valid service object found"
        self.applications[key] = _plain(objects)

    async def _unregister_application(self, sender, msg):
        if self.hang_unregister:
            await asyncio.sleep(3600)
        key = (sender, msg.body[0])
        if self.applications.pop(key, None) is None:
            return _DOES_NOT_EXIST, "Does Not Exist"

    async def _register_advertisement(self, sender, msg):
        key = (sender, msg.body[0])
        if key in self.advertisements:
            return _ALREADY_EXISTS, "Already Exists"
        self.advertisements[key] = True

    async def _unregister_advertisement(self, sender, msg):
        if self.hang_unregister:
            await asyncio.sleep(3600)
        key = (sender, msg.body[0])
        if self.advertisements.pop(key, None) is None:
            return _DOES_NOT_EXIST, "Does Not Exist"


def _plain(value):
    if isinstance(value, Variant):
        return _plain(value.value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value
