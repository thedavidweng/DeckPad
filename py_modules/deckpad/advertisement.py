"""The LE advertisement that lets a Host find the Deck in its Bluetooth list during Pairing Mode."""

from dbus_fast.service import PropertyAccess, ServiceInterface, dbus_property, method

from . import gatt

GAMEPAD_APPEARANCE = 0x03C4


class Advertisement(ServiceInterface):
    """A connectable, discoverable advertisement for the HID service.

    Discoverability comes from this advertisement alone (LE General Discoverable flag). Adapter1's
    Discoverable property is never touched: it would make the Deck discoverable over Classic too.
    """

    def __init__(self, local_name):
        super().__init__("org.bluez.LEAdvertisement1")
        self._local_name = local_name

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> "s":
        return "peripheral"

    @dbus_property(access=PropertyAccess.READ)
    def ServiceUUIDs(self) -> "as":
        return [gatt.uuid16("1812")]

    @dbus_property(access=PropertyAccess.READ)
    def Appearance(self) -> "q":
        return GAMEPAD_APPEARANCE

    @dbus_property(access=PropertyAccess.READ)
    def LocalName(self) -> "s":
        return self._local_name

    @dbus_property(access=PropertyAccess.READ)
    def Discoverable(self) -> "b":
        return True

    @method()
    def Release(self):
        pass
