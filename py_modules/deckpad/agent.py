"""DeckPad's BlueZ pairing agent, the default agent only while Controller Mode is on (ADR-0005)."""

from dbus_fast.errors import DBusError
from dbus_fast.service import ServiceInterface, method

CAPABILITY = "NoInputNoOutput"
_REJECTED = "org.bluez.Error.Rejected"


class PairingAgent(ServiceInterface):
    """Rejects every pairing request until Pairing Mode exists to accept them.

    While this agent is the default, it also receives pairing requests a user starts from Steam's
    Bluetooth settings, so it must never accept outside an explicit Pairing Mode.
    """

    def __init__(self):
        super().__init__("org.bluez.Agent1")

    @method()
    def Release(self):
        pass

    @method()
    def RequestPinCode(self, device: "o") -> "s":
        raise DBusError(_REJECTED, "Pairing is not open")

    @method()
    def DisplayPinCode(self, device: "o", pincode: "s"):
        raise DBusError(_REJECTED, "Pairing is not open")

    @method()
    def RequestPasskey(self, device: "o") -> "u":
        raise DBusError(_REJECTED, "Pairing is not open")

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):
        pass

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u"):
        raise DBusError(_REJECTED, "Pairing is not open")

    @method()
    def RequestAuthorization(self, device: "o"):
        raise DBusError(_REJECTED, "Pairing is not open")

    @method()
    def AuthorizeService(self, device: "o", uuid: "s"):
        # BlueZ only asks this for devices that are already paired but not trusted. Accepting keeps
        # the user's existing peripherals working while our agent is the default.
        pass

    @method()
    def Cancel(self):
        pass
