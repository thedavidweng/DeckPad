"""BlueZ GATT server objects (org.bluez.GattService1/Characteristic1/Descriptor1).

Never set a `name` attribute on these classes: ServiceInterface uses it as the D-Bus interface name,
and BlueZ then rejects the application with "No valid service object found" (ADR-0004).
"""

from dbus_fast import Variant
from dbus_fast.service import PropertyAccess, ServiceInterface, dbus_property, method


def uuid16(short):
    return "0000%s-0000-1000-8000-00805f9b34fb" % short.lower()


def _offset(options):
    offset = options.get("offset")
    return int(offset.value) if isinstance(offset, Variant) else 0


class Descriptor(ServiceInterface):
    def __init__(self, characteristic, index, uuid, flags, value):
        super().__init__("org.bluez.GattDescriptor1")
        self.path = "%s/desc%d" % (characteristic.path, index)
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
        return self.value[_offset(options):]


class Characteristic(ServiceInterface):
    def __init__(self, service, index, uuid, flags, value):
        super().__init__("org.bluez.GattCharacteristic1")
        self.path = "%s/char%d" % (service.path, index)
        self._service_path = service.path
        self._uuid = uuid
        self._flags = list(flags)
        self.value = bytes(value)
        # BlueZ calls StartNotify/StopNotify only on CCCD writes and app (re-)registration, never on
        # a bonded Host's disconnect or plain reconnect, so only those two calls may change this flag.
        self.notifying = False
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
        return self.value[_offset(options):]

    @method()
    def WriteValue(self, value: "ay", options: "a{sv}"):
        pass

    @method()
    def StartNotify(self):
        self.notifying = True

    @method()
    def StopNotify(self):
        self.notifying = False


class Service(ServiceInterface):
    def __init__(self, application, index, uuid):
        super().__init__("org.bluez.GattService1")
        self.path = "%s/service%d" % (application.path, index)
        self._uuid = uuid
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


class Application:
    """A tree of GATT services exported under one root path.

    dbus-fast answers ObjectManager.GetManagedObjects at the root with every object exported below
    it, so only GATT objects may live under this path (the agent and advertisements go elsewhere).
    """

    def __init__(self, path):
        self.path = path
        self.services = []

    def add_service(self, uuid):
        service = Service(self, len(self.services), uuid)
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

    def unexport(self, bus):
        for obj in self._objects():
            bus.unexport(obj.path, obj)
