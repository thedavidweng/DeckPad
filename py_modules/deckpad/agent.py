"""DeckPad's BlueZ pairing agent. It is the default agent only while controller mode is on."""

from dbus_fast.errors import DBusError
from dbus_fast.service import ServiceInterface, method

CAPABILITY = "NoInputNoOutput"
_REJECTED = "org.bluez.Error.Rejected"


class PairingAgent(ServiceInterface):
    """Accepts Just Works pairing only while pairing mode is open.

    While this agent is the default, it also receives pairing requests a user starts from Steam's
    Bluetooth settings, so it must never accept outside pairing mode. `allow_pairing` and
    `allow_service` are called with the device's object path and answer synchronously.
    """

    def __init__(self, allow_pairing, allow_service):
        super().__init__("org.bluez.Agent1")
        self._allow_pairing = allow_pairing
        self._allow_service = allow_service

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
        # BlueZ asks this only for paired but untrusted devices, so the user's trusted peripherals never
        # get here.
        if not self._allow_service(device):
            raise DBusError(_REJECTED, "Not a Paired Host")

    @method()
    def Cancel(self):
        pass
