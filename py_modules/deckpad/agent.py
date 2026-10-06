"""DeckPad's BlueZ pairing agent, the default agent only while Controller Mode is on (ADR-0005)."""

from dbus_fast.errors import DBusError
from dbus_fast.service import ServiceInterface, method

CAPABILITY = "NoInputNoOutput"
_REJECTED = "org.bluez.Error.Rejected"


class PairingAgent(ServiceInterface):
    """Accepts Just Works pairing only while Pairing Mode is open, and refuses it at any other time.

    While this agent is the default, it also receives pairing requests a user starts from Steam's
    Bluetooth settings, so it must never accept outside an explicit Pairing Mode. `allow_pairing` is
    called with the device's object path and answers synchronously.
    """

    def __init__(self, allow_pairing):
        super().__init__("org.bluez.Agent1")
        self._allow_pairing = allow_pairing

    def _authorize(self, device):
        if not self._allow_pairing(device):
            raise DBusError(_REJECTED, "Pairing Mode is not open")

    @method()
    def Release(self):
        pass

    @method()
    def RequestPinCode(self, device: "o") -> "s":
        raise DBusError(_REJECTED, "PIN pairing is not supported")

    @method()
    def DisplayPinCode(self, device: "o", pincode: "s"):
        raise DBusError(_REJECTED, "PIN pairing is not supported")

    @method()
    def RequestPasskey(self, device: "o") -> "u":
        raise DBusError(_REJECTED, "Passkey entry is not supported")

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):
        pass

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u"):
        # The Deck has no way to show the passkey to compare, so this is treated as Just Works.
        self._authorize(device)

    @method()
    def RequestAuthorization(self, device: "o"):
        self._authorize(device)

    @method()
    def AuthorizeService(self, device: "o", uuid: "s"):
        # BlueZ only asks this for devices that are already paired but not trusted. Accepting keeps
        # the user's existing peripherals working while our agent is the default.
        pass

    @method()
    def Cancel(self):
        pass
