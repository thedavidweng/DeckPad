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


def start_failed(detail=None):
    return ControllerModeError(
        "start_failed",
        "Controller Mode could not start. Try again; if it keeps failing, restart the Deck.",
        detail,
    )
