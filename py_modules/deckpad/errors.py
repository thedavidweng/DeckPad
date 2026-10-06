START_FAILED_TITLE = "Could not turn on Controller Mode"
PAIRING_FAILED_TITLE = "Pairing did not finish"
SESSION_LOST_TITLE = "Controller Mode turned off"


class ControllerModeError(Exception):
    """A failure the QAM panel can explain to the user.

    `code` is stable for the frontend; `title` and `message` are user-facing (the message says what to
    do next); `detail` is for logs and diagnostics.
    """

    def __init__(self, code, message, detail=None, title=START_FAILED_TITLE):
        super().__init__(message)
        self.code = code
        self.title = title
        self.message = message
        self.detail = detail

    def to_dict(self):
        return {"code": self.code, "title": self.title, "message": self.message, "detail": self.detail}


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
        PAIRING_FAILED_TITLE,
    )


def pairing_timed_out(detail=None):
    return ControllerModeError(
        "pairing_timed_out",
        "No device paired in time. Select Pair a Device again, then pick this Deck in the other "
        "device's Bluetooth settings.",
        detail,
        PAIRING_FAILED_TITLE,
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
    return ControllerModeError("pairing_failed", message, detail, PAIRING_FAILED_TITLE)


def start_failed(detail=None):
    return ControllerModeError(
        "start_failed",
        "Controller Mode could not start. Try again; if it keeps failing, restart the Deck.",
        detail,
    )


def session_lost(cause):
    """Bluetooth went away underneath a running Controller Mode and did not come back; `cause` is why the
    last attempt to resume failed."""
    detail = "%s: %s" % (cause.code, cause.detail) if cause.detail else cause.code
    if cause.code == "bluetooth_off":
        return ControllerModeError(
            "bluetooth_turned_off",
            "Bluetooth was turned off. Turn it on in Steam's Bluetooth settings, then turn Controller Mode "
            "on again.",
            detail,
            SESSION_LOST_TITLE,
        )
    return ControllerModeError(
        "bluetooth_stopped",
        "Bluetooth stopped working and did not come back. Turn Controller Mode on again; if it keeps "
        "happening, restart the Deck.",
        detail,
        SESSION_LOST_TITLE,
    )


def _host(name):
    return name or "the device"


def forget_failed(host_name=None, detail=None):
    return ControllerModeError(
        "forget_failed",
        "Bluetooth did not remove the pairing. Try again; if it keeps failing, remove %s in Steam's "
        "Bluetooth settings." % _host(host_name),
        detail,
        "Could not forget %s" % _host(host_name),
    )


def disconnect_failed(host_name=None, detail=None):
    return ControllerModeError(
        "disconnect_failed",
        "Try again, or turn Controller Mode off to disconnect every device.",
        detail,
        "Could not disconnect %s" % _host(host_name),
    )


def reconnect_unavailable(detail=None):
    return ControllerModeError(
        "reconnect_unavailable",
        "The Deck could not start advertising to them. Turn Controller Mode off and on, then try again.",
        detail,
        "Paired devices cannot reconnect",
    )
