"""A stand-in for bluetoothd's org.bluez D-Bus API, observed from BlueZ's side.

It models only the contract DeckPad relies on, the way BlueZ 5.83 behaves on the Deck:
- AgentManager1 keeps a stack of default agents. Steam's agent is already the default.
- GattManager1.RegisterApplication calls back GetManagedObjects on the application and
  rejects one that exposes no GATT service.
- Registrations are bound to the registering D-Bus connection and vanish with it.
- Attribute handles are allocated the way bluetoothd's gatt-db does it: a service that asks for no
  Handle goes after the highest handle ever used, so handles are never reused within one bluetoothd
  run, and a requested Handle that overlaps a registered service fails the whole application.
"""

import asyncio

from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.errors import DBusError
from dbus_fast.aio import MessageBus
from dbus_fast.service import PropertyAccess, ServiceInterface, dbus_property, method

STEAM_AGENT = ("steam", "/steam/agent")
ADAPTER_PATH = "/org/bluez/hci0"
HOST_ADDRESS = "38:F9:D3:C3:E9:69"
HOST_NAME = "mbp2019"

_FAILED = "org.bluez.Error.Failed"
_ALREADY_EXISTS = "org.bluez.Error.AlreadyExists"
_DOES_NOT_EXIST = "org.bluez.Error.DoesNotExist"

# GAP, GATT, and bluetoothd's own DIS, then PipeWire's BLE-MIDI service, as on the Deck.
CORE_LAST_HANDLE = 0x0017


class _Adapter(ServiceInterface):
    def __init__(self, bluez, powered):
        super().__init__("org.bluez.Adapter1")
        self._bluez = bluez
        self.powered = powered

    @dbus_property(access=PropertyAccess.READ)
    def Address(self) -> "s":
        return "E8:FB:1C:43:F3:44"

    @dbus_property(access=PropertyAccess.READ)
    def Powered(self) -> "b":
        return self.powered


    @dbus_property(access=PropertyAccess.READ)
    def Alias(self) -> "s":
        return "steamdeck"

    @method()
    async def RemoveDevice(self, device: "o"):
        self._bluez.calls.append(("RemoveDevice", device))
        if self._bluez.reject_remove_device:
            raise DBusError(_FAILED, self._bluez.reject_remove_device)
        if device not in self._bluez.devices:
            raise DBusError(_DOES_NOT_EXIST, "Does Not Exist")
        await self._bluez.remove_device(device)


class _Marker(ServiceInterface):
    """An interface with no members, so it shows up in GetManagedObjects."""


class _Device(ServiceInterface):
    """A remote device as bluetoothd sees it (org.bluez.Device1)."""

    def __init__(self, bluez, path, address, name, paired=False):
        super().__init__("org.bluez.Device1")
        self._bluez = bluez
        self.path = path
        self.address = address
        self.alias = name
        self.connected = False
        self.paired = paired

    def update(self, **changes):
        names = {"connected": "Connected", "paired": "Paired", "alias": "Alias"}
        for key, value in changes.items():
            setattr(self, key, value)
        changed = {names[k]: v for k, v in changes.items()}
        if changes.get("paired"):
            changed["Bonded"] = True
        # A call that arrives while bluetoothd is going away changes state but announces nothing.
        if self._bluez.bus is not None:
            self.emit_properties_changed(changed)

    @dbus_property(access=PropertyAccess.READ)
    def Address(self) -> "s":
        return self.address

    @dbus_property(access=PropertyAccess.READ)
    def AddressType(self) -> "s":
        return "public"

    @dbus_property(access=PropertyAccess.READ)
    def Alias(self) -> "s":
        return self.alias

    @dbus_property(access=PropertyAccess.READ)
    def Connected(self) -> "b":
        return self.connected

    @dbus_property(access=PropertyAccess.READ)
    def Paired(self) -> "b":
        return self.paired

    @dbus_property(access=PropertyAccess.READ)
    def Bonded(self) -> "b":
        return self.paired

    @method()
    def Disconnect(self):
        self._bluez.disconnect_requests.append(self.path)
        self._bluez.calls.append(("Disconnect", self.path))
        if self._bluez.reject_disconnect:
            raise DBusError(_FAILED, self._bluez.reject_disconnect)
        if self.connected:
            self.update(connected=False)


class FakeBluez:
    def __init__(self, adapter=True, powered=True):
        self._has_adapter = adapter
        self._adapter = _Adapter(self, powered)
        self.bus = None
        self.agents = {}
        self.default_agents = [STEAM_AGENT]
        self.applications = {}
        self.advertisements = {}
        self.hang_unregister = False
        self.reject_application = None
        self.reject_advertisement = None
        self.reject_remove_device = None
        self.reject_disconnect = None
        self.devices = {}
        self.disconnect_requests = []
        # Ordered record of calls that matter for teardown ordering, e.g. ("Disconnect", path).
        self.calls = []
        # (characteristic path, value) for every GATT notification the application sent, in order.
        self.notifications = []
        self.last_handle = CORE_LAST_HANDLE
        # Attribute handle of every registered GATT object, by application key and object path.
        # Services map to their declaration, characteristics to their value handle.
        self.handles = {}
        self._ranges = {}

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

    def gatt_objects(self, interface, uuid):
        """(path, properties) of every registered GATT object with this interface and UUID, in path order."""
        found = []
        for objects in self.applications.values():
            for path in sorted(objects):
                props = objects[path].get(interface)
                if props and props.get("UUID") == gatt_uuid(uuid):
                    found.append((path, props))
        return found

    @property
    def advertisement(self):
        """Properties of the one registered advertisement, or None while the Deck is not advertising."""
        if not self.advertisements:
            return None
        (props,) = self.advertisements.values()
        return props

    def device(self, address=HOST_ADDRESS, name=HOST_NAME):
        """The Device1 object for a remote device, created the first time bluetoothd sees it.

        Steam scans continuously, so a nearby host often already has a Device1 object before it connects.
        """
        path = self._device_path(address)
        if path not in self.devices:
            self.devices[path] = _Device(self, path, address, name)
            self.bus.export(path, self.devices[path])
        return self.devices[path]

    async def host_connects(self, address=HOST_ADDRESS, name=HOST_NAME):
        """A host picks the Deck from its Bluetooth list and opens an LE link to it."""
        adv = self.advertisement
        assert adv and adv.get("Discoverable"), "the Host cannot find the Deck: it is not discoverable"
        new = self._device_path(address) not in self.devices
        device = self.device(address, name)
        if new:
            # For a device bluetoothd has never seen, Connected arrives in InterfacesAdded.
            self.bus.unexport(device.path, device)
            device.connected = True
            self.bus.export(device.path, device)
        else:
            device.update(connected=True)
        return device.path

    async def host_reconnects(self, path):
        """A paired host connects again on its own. It needs no scan list entry, only a connectable
        advertisement from the Deck, which it recognises by address."""
        assert self.advertisement, "the Host cannot reconnect: the Deck is not advertising"
        assert self.devices[path].paired, "only a Paired Host reconnects by itself"
        self.devices[path].update(connected=True)

    async def host_pairs(self, path):
        """The host asks to pair; bluetoothd hands Just Works pairing to the default agent.

        Returns True if pairing completed. If the agent refuses (or it is Steam's agent, which stalls
        with a passkey prompt nobody answers), the host gives up and drops the link.
        """
        device = self.devices[path]
        sender, agent_path = self.default_agent
        ok = False
        if (sender, agent_path) != STEAM_AGENT:
            reply = await self.bus.call(
                Message(
                    destination=sender,
                    path=agent_path,
                    interface="org.bluez.Agent1",
                    member="RequestAuthorization",
                    signature="o",
                    body=[path],
                )
            )
            ok = reply.message_type == MessageType.METHOD_RETURN
        if ok:
            device.update(paired=True)
        else:
            device.update(connected=False)
        return ok

    async def device_uses_a_service(self, path, uuid="00001812-0000-1000-8000-00805f9b34fb"):
        """A paired but untrusted device connects to a local profile; bluetoothd asks the default agent
        with AuthorizeService. Returns whether the agent allowed it (Steam's agent always does)."""
        sender, agent_path = self.default_agent
        if (sender, agent_path) == STEAM_AGENT:
            return True
        reply = await self.bus.call(
            Message(
                destination=sender,
                path=agent_path,
                interface="org.bluez.Agent1",
                member="AuthorizeService",
                signature="os",
                body=[path, uuid],
            )
        )
        return reply.message_type == MessageType.METHOD_RETURN

    async def remove_device(self, path):
        """The bond is removed on the Deck (DeckPad's Forget, or Steam's Bluetooth settings)."""
        device = self.devices.pop(path)
        if device.connected:
            device.update(connected=False)
        self.bus.unexport(path, device)

    async def host_disconnects(self, path):
        self.devices[path].update(connected=False)

    async def host_reads(self, uuid, index=0, device=None, descriptor=None):
        """A host reads a characteristic (or one of its descriptors) over GATT, the way BlueZ forwards it."""
        ((sender, _app),) = self.applications.keys()
        path, _props = self.gatt_objects("org.bluez.GattCharacteristic1", uuid)[index]
        interface = "org.bluez.GattCharacteristic1"
        if descriptor is not None:
            path = [
                p
                for p, props in self.gatt_objects("org.bluez.GattDescriptor1", descriptor)
                if props["Characteristic"] == path
            ][0]
            interface = "org.bluez.GattDescriptor1"
        options = {"device": Variant("o", device or self._device_path(HOST_ADDRESS))}
        reply = await self.bus.call(
            Message(
                destination=sender,
                path=path,
                interface=interface,
                member="ReadValue",
                signature="a{sv}",
                body=[options],
            )
        )
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError("%s: %s" % (reply.error_name, reply.body))
        return bytes(reply.body[0])

    def input_report_path(self):
        """The object path of the gamepad input report (the notifying 2a4d characteristic)."""
        return next(
            path for path, props in self.gatt_objects("org.bluez.GattCharacteristic1", "2a4d") if "notify" in props["Flags"]
        )

    def gamepad_reports(self):
        """Every gamepad report notified to hosts so far, oldest first."""
        path = self.input_report_path()
        return [value for p, value in self.notifications if p == path]

    def handle_of(self, path):
        """The ATT handle a host discovers for a registered GATT object."""
        ((_key, handles),) = self.handles.items()
        return handles[path]

    async def host_subscribes(self, path=None, handle=None):
        """The host writes the input report's CCCD; bluetoothd turns that into StartNotify.

        A host that kept its GATT cache from an earlier connection names the report by `handle`. If no
        registered characteristic has that handle any more, bluetoothd answers Invalid Handle.
        """
        ((sender, _app),) = self.applications.keys()
        if handle is not None:
            by_handle = {h: p for p, h in self.handles[(sender, _app)].items()}
            if handle not in by_handle:
                raise RuntimeError("ATT Invalid Handle 0x%04x" % handle)
            path = by_handle[handle]
        reply = await self.bus.call(
            Message(
                destination=sender,
                path=path or self.input_report_path(),
                interface="org.bluez.GattCharacteristic1",
                member="StartNotify",
            )
        )
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError("%s: %s" % (reply.error_name, reply.body))

    def set_powered(self, powered):
        """The adapter is switched off or on (Steam's Bluetooth toggle). Switching off drops every link."""
        if not powered:
            for device in self.devices.values():
                if device.connected:
                    device.update(connected=False)
        self._adapter.powered = powered
        self._adapter.emit_properties_changed({"Powered": powered})

    async def stop_service(self):
        """bluetoothd exits (`systemctl stop bluetooth`): it powers the adapter off, unregisters every
        device object while keeping the bonds on disk, and leaves the bus. Every registration is lost."""
        if self._adapter.powered:
            self.set_powered(False)
        for path, device in self.devices.items():
            self.bus.unexport(path, device)
        await self.stop()
        self.agents.clear()
        self.applications.clear()
        self.advertisements.clear()
        self.default_agents = [STEAM_AGENT]
        self.devices = {
            path: _Device(self, path, d.address, d.alias, paired=d.paired) for path, d in self.devices.items() if d.paired
        }
        self._adapter = _Adapter(self, True)

    async def restart(self):
        """`systemctl restart bluetooth` underneath DeckPad. Paired devices come back from disk, unconnected."""
        await self.stop_service()
        await self.start()

    async def start(self):
        self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        self.bus.export("/org/bluez", _Marker("org.bluez.AgentManager1"))
        if self._has_adapter:
            self.bus.export(ADAPTER_PATH, self._adapter)
            self.bus.export(ADAPTER_PATH, _Marker("org.bluez.GattManager1"))
            self.bus.export(ADAPTER_PATH, _Marker("org.bluez.LEAdvertisingManager1"))
        for path, device in self.devices.items():
            self.bus.export(path, device)
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
        await self.bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=["type='signal',member='PropertiesChanged',arg0='org.bluez.GattCharacteristic1'"],
            )
        )
        await self.bus.request_name("org.bluez")

    async def stop(self):
        if self.bus:
            bus, self.bus = self.bus, None
            bus.disconnect()
            await bus.wait_for_disconnect()

    def _handle(self, msg):
        if msg.message_type == MessageType.SIGNAL and msg.member == "NameOwnerChanged":
            name, _old, new = msg.body
            if name.startswith(":") and not new:
                self._drop_client(name)
            return False
        if (
            msg.message_type == MessageType.SIGNAL
            and msg.member == "PropertiesChanged"
            and msg.body[0] == "org.bluez.GattCharacteristic1"
            and "Value" in msg.body[1]
        ):
            self.notifications.append((msg.path, bytes(msg.body[1]["Value"].value)))
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
        for table in (self.agents, self.applications, self.advertisements, self.handles, self._ranges):
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
        objects = _plain(objects)
        allocated = self._allocate_handles(objects)
        if allocated is None:
            return _FAILED, "Failed to create GATT service entry in local database"
        self.handles[key], self._ranges[key] = allocated
        self.applications[key] = objects

    def _allocate_handles(self, objects):
        taken = [r for ranges in self._ranges.values() for r in ranges]
        handles, ranges = {}, []
        last_handle = self.last_handle
        for service in sorted(p for p, i in objects.items() if "org.bluez.GattService1" in i):
            chars = sorted(p for p, i in objects.items() if i.get("org.bluez.GattCharacteristic1", {}).get("Service") == service)
            layout = []
            for char in chars:
                descs = sorted(
                    p for p, i in objects.items() if i.get("org.bluez.GattDescriptor1", {}).get("Characteristic") == char
                )
                flags = objects[char]["org.bluez.GattCharacteristic1"]["Flags"]
                # bluetoothd adds the CCCD itself for notify/indicate, right after the value.
                ccc = 1 if {"notify", "indicate"} & set(flags) else 0
                layout.append((char, ccc, descs))
            count = 1 + sum(2 + ccc + len(descs) for _c, ccc, descs in layout)
            start = objects[service]["org.bluez.GattService1"].get("Handle") or last_handle + 1
            end = start + count - 1
            if end > 0xFFFF or any(start <= e and s <= end for s, e in taken + ranges):
                return None
            handles[service] = start
            next_handle = start + 1
            for char, ccc, descs in layout:
                handles[char] = next_handle + 1
                next_handle += 2 + ccc
                for desc in descs:
                    handles[desc] = next_handle
                    next_handle += 1
            ranges.append((start, end))
            last_handle = max(last_handle, end)
        self.last_handle = last_handle
        return handles, ranges

    def occupy_handles(self, start, end, owner=":other.app"):
        """Another BlueZ client (Steam, PipeWire, another plugin) holds a service in this handle range."""
        self._ranges[(owner, "/other/app")] = [(start, end)]
        self.last_handle = max(self.last_handle, end)

    async def _unregister_application(self, sender, msg):
        if self.hang_unregister:
            await asyncio.sleep(3600)
        key = (sender, msg.body[0])
        self.calls.append(("UnregisterApplication", msg.body[0]))
        self.handles.pop(key, None)
        self._ranges.pop(key, None)
        if self.applications.pop(key, None) is None:
            return _DOES_NOT_EXIST, "Does Not Exist"

    def _device_path(self, address):
        return "%s/dev_%s" % (ADAPTER_PATH, address.replace(":", "_"))

    async def _register_advertisement(self, sender, msg):
        if msg.path != ADAPTER_PATH:
            return "org.freedesktop.DBus.Error.UnknownObject", "No adapter"
        key = (sender, msg.body[0])
        if key in self.advertisements:
            return _ALREADY_EXISTS, "Already Exists"
        if self.reject_advertisement:
            return _FAILED, self.reject_advertisement
        reply = await self.bus.call(
            Message(
                destination=sender,
                path=msg.body[0],
                interface="org.freedesktop.DBus.Properties",
                member="GetAll",
                signature="s",
                body=["org.bluez.LEAdvertisement1"],
            )
        )
        if reply.message_type != MessageType.METHOD_RETURN:
            return _FAILED, "Failed to parse advertisement"
        props = _plain(reply.body[0])
        if "Type" not in props:
            return "org.bluez.Error.InvalidArguments", "Invalid arguments"
        self.calls.append(("RegisterAdvertisement", msg.body[0]))
        self.advertisements[key] = props

    async def _unregister_advertisement(self, sender, msg):
        if self.hang_unregister:
            await asyncio.sleep(3600)
        key = (sender, msg.body[0])
        self.calls.append(("UnregisterAdvertisement", msg.body[0]))
        if self.advertisements.pop(key, None) is None:
            return _DOES_NOT_EXIST, "Does Not Exist"


def gatt_uuid(short):
    return "0000%s-0000-1000-8000-00805f9b34fb" % short.lower()


def _plain(value):
    if isinstance(value, Variant):
        return _plain(value.value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value
