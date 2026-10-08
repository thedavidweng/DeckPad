"""BlueZ GATT server objects (org.bluez.GattService1/Characteristic1/Descriptor1).

Never set a `name` attribute on these classes: ServiceInterface uses it as the D-Bus interface name,
and BlueZ then rejects the application with "No valid service object found".
"""

from dbus_fast import Variant
from dbus_fast.errors import DBusError
from dbus_fast.service import PropertyAccess, ServiceInterface, dbus_property, method


def uuid16(short):
    return "0000%s-0000-1000-8000-00805f9b34fb" % short.lower()


def _offset(options):
    if "offset" not in options:
        return 0
    offset = options["offset"]
    if not isinstance(offset, Variant) or offset.signature != "q":
        raise DBusError("org.bluez.Error.InvalidArguments", "Offset must be uint16")
    return offset.value


def _read(value, flags, options):
    if not any(flag in flags for flag in ("read", "encrypt-read")):
        raise DBusError("org.bluez.Error.NotPermitted", "Value is not readable")
    offset = _offset(options)
    if offset > len(value):
        raise DBusError("org.bluez.Error.InvalidOffset", "Offset exceeds value length")
    return value[offset:]


def _device(options):
    device = options.get("device")
    return device.value if isinstance(device, Variant) else None


class Descriptor(ServiceInterface):
    def __init__(self, characteristic, index, uuid, flags, value):
        super().__init__("org.bluez.GattDescriptor1")
        self.path = "%s/desc%d" % (characteristic.path, index)
        self._application = characteristic.application
        self._characteristic_path = characteristic.path
        self._uuid = uuid
        self._flags = list(flags)
        self.value = bytes(value)

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return self._uuid

    @dbus_property(access=PropertyAccess.READ)
    def Characteristic(self) -> "o":
        return self._characteristic_path

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> "as":
        return self._flags

    @method()
    def ReadValue(self, options: "a{sv}") -> "ay":
        value = _read(self.value, self._flags, options)
        self._application.host_seen(_device(options))
        return value


class Characteristic(ServiceInterface):
    def __init__(self, service, index, uuid, flags, value):
        super().__init__("org.bluez.GattCharacteristic1")
        self.path = "%s/char%d" % (service.path, index)
        self.application = service.application
        self._service_path = service.path
        self._uuid = uuid
        self._flags = list(flags)
        self.value = bytes(value)
        # BlueZ calls StartNotify/StopNotify only on CCCD writes and app (re-)registration, never on
        # a paired host's disconnect or plain reconnect, so only those two calls may change this flag.
        self.notifying = False
        self.on_notify_changed = None
        self.descriptors = []

    def add_descriptor(self, uuid, flags, value):
        descriptor = Descriptor(self, len(self.descriptors), uuid, flags, value)
        self.descriptors.append(descriptor)
        return descriptor

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return self._uuid

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> "o":
        return self._service_path

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> "as":
        return self._flags

    @dbus_property(access=PropertyAccess.READ)
    def Value(self) -> "ay":
        return self.value

    @method()
    def ReadValue(self, options: "a{sv}") -> "ay":
        value = _read(self.value, self._flags, options)
        self.application.host_seen(_device(options))
        return value

    @method()
    def WriteValue(self, value: "ay", options: "a{sv}"):
        if not any(flag in self._flags for flag in ("write", "encrypt-write", "write-without-response")):
            raise DBusError("org.bluez.Error.NotPermitted", "Value is not writable")
        if _offset(options) != 0:
            raise DBusError("org.bluez.Error.InvalidOffset", "Partial HID writes are not supported")
        if len(value) != len(self.value):
            raise DBusError("org.bluez.Error.InvalidValueLength", "Incorrect HID value length")
        if self._uuid == uuid16("2a4c") and value not in (b"\x00", b"\x01"):
            raise DBusError("org.bluez.Error.NotSupported", "Unknown HID control point")
        if self._uuid == uuid16("2a4e") and value != b"\x01":
            raise DBusError("org.bluez.Error.NotSupported", "Only Report Protocol is supported")
        # Suspend and rumble are accepted without side effects; Boot Protocol is not advertised.
        self.application.host_seen(_device(options))

    @method()
    def StartNotify(self):
        self._set_notifying(True)

    @method()
    def StopNotify(self):
        self._set_notifying(False)

    def _set_notifying(self, enabled):
        if "notify" not in self._flags:
            raise DBusError("org.bluez.Error.NotSupported", "Value does not support notifications")
        if self.notifying != enabled:
            self.notifying = enabled
            if self.on_notify_changed is not None:
                self.on_notify_changed()


class Service(ServiceInterface):
    def __init__(self, application, index, uuid, handle=0):
        super().__init__("org.bluez.GattService1")
        self.path = "%s/service%d" % (application.path, index)
        self.application = application
        self._uuid = uuid
        # 0 lets bluetoothd pick the handle; it then writes the one it picked back here.
        self.handle = handle
        self.characteristics = []

    def add_characteristic(self, uuid, flags, value):
        characteristic = Characteristic(self, len(self.characteristics), uuid, flags, value)
        self.characteristics.append(characteristic)
        return characteristic

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return self._uuid

    @dbus_property(access=PropertyAccess.READ)
    def Primary(self) -> "b":
        return True

    @dbus_property()
    def Handle(self) -> "q":
        return self.handle

    @Handle.setter
    def Handle(self, value: "q"):
        self.handle = value


class Application:
    """A tree of GATT services exported under one root path.

    dbus-fast answers ObjectManager.GetManagedObjects at the root with every object exported below
    it, so only GATT objects may live under this path (the agent and advertisements go elsewhere).
    """

    def __init__(self, path, on_host=None):
        self.path = path
        self.services = []
        self._on_host = on_host

    def host_seen(self, device_path):
        """BlueZ names the remote device in every read/write, which is how DeckPad knows its hosts."""
        if device_path and self._on_host is not None:
            self._on_host(device_path)

    def add_service(self, uuid, handle=0):
        service = Service(self, len(self.services), uuid, handle)
        self.services.append(service)
        return service

    def _objects(self):
        for service in self.services:
            yield service
            for characteristic in service.characteristics:
                yield characteristic
                yield from characteristic.descriptors

    def export(self, bus):
        for obj in self._objects():
            bus.export(obj.path, obj)
