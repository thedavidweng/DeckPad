class ControllerModeError(Exception):
    """A failure the QAM panel can explain to the user.

    `code` is stable for the frontend; `message` is user-facing; `detail` is for logs and diagnostics.
    """

    def __init__(self, code, message, detail=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def to_dict(self):
        return {"code": self.code, "message": self.message, "detail": self.detail}


def bluetooth_unavailable(detail=None):
    return ControllerModeError(
        "bluetooth_unavailable",
        "The Bluetooth service is not running. Restart the Deck, then try again.",
        detail,
    )


def no_adapter(detail=None):
    return ControllerModeError(
        "no_adapter",
        "No Bluetooth adapter was found on this Deck.",
        detail,
    )


def bluetooth_off(detail=None):
    return ControllerModeError(
        "bluetooth_off",
        "Bluetooth is turned off. Turn it on in Steam's Bluetooth settings, then try again.",
        detail,
    )


def advertising_failed(detail=None):
    return ControllerModeError(
        "advertising_failed",
        "The Deck could not become discoverable. Turn Controller Mode off and on, then try again.",
        detail,
    )


def pairing_timed_out(detail=None):
    return ControllerModeError(
        "pairing_timed_out",
        "No device paired in time. Select Pair a Device again, then pick this Deck in the other "
        "device's Bluetooth settings.",
        detail,
    )


def pairing_failed(host_name=None, detail=None):
    if host_name:
        message = (
            "Pairing with %s did not finish. If this Deck is already listed in %s's Bluetooth settings, "
            "remove it there, then select Pair a Device and try again." % (host_name, host_name)
        )
    else:
        message = (
            "Pairing did not finish. If this Deck is already listed in the other device's Bluetooth "
            "settings, remove it there, then select Pair a Device and try again."
        )
    return ControllerModeError("pairing_failed", message, detail)


def start_failed(detail=None):
    return ControllerModeError(
        "start_failed",
        "Controller Mode could not start. Try again; if it keeps failing, restart the Deck.",
        detail,
    )
