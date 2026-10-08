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

    def __init__(self, allow_pairing, allow_service, service_uuids):
        super().__init__("org.bluez.Agent1")
        self._allow_pairing = allow_pairing
        self._allow_service = allow_service
        self._service_uuids = frozenset(service_uuids)

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
        raise DBusError(_REJECTED, "Passkey display is not supported")

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u"):
        raise DBusError(_REJECTED, "Numeric comparison is not supported")

    @method()
    def RequestAuthorization(self, device: "o"):
        self._authorize(device)

    @method()
    def AuthorizeService(self, device: "o", uuid: "s"):
        # BlueZ asks this only for paired but untrusted devices, so the user's trusted peripherals never
        # get here.
        if uuid.lower() not in self._service_uuids or not self._allow_service(device):
            raise DBusError(_REJECTED, "Not a Paired Host")

    @method()
    def Cancel(self):
        pass
