"""Deck Controls in, Gamepad Reports out, for as long as Controller Mode is on.

DeckPad reads the built-in controller's raw HID interface read-only, next to Steam (ADR-0003). The
node is found by VID/PID plus sysfs topology on every (re)open, because hidraw numbering is not
stable and the interface disappears and comes back when the controller resets.
"""

import asyncio
import logging
import os

from .gamepad_report import DECK_STATE_REPORT_SIZE, gamepad_report
from .report_pacer import ReportPacer

log = logging.getLogger("deckpad.deck_input")

HIDRAW_CLASS = "/sys/class/hidraw"
DEV_DIR = "/dev"
VALVE_CONTROLLER_HID_ID = "0003:000028DE:00001205"
REOPEN_DELAY = 1.0


def find_controller_node():
    """The /dev path of the controller's raw interface: the 28DE:1205 hidraw device without an input/ child.

    The other two 28DE:1205 interfaces are Steam's lizard-mode keyboard and mouse.
    """
    try:
        names = sorted(os.listdir(HIDRAW_CLASS))
    except OSError:
        return None
    for name in names:
        device = os.path.join(HIDRAW_CLASS, name, "device")
        try:
            with open(os.path.join(device, "uevent")) as f:
                uevent = f.read().split()
        except OSError:
            continue
        if "HID_ID=" + VALVE_CONTROLLER_HID_ID in uevent and not os.path.exists(os.path.join(device, "input")):
            return os.path.join(DEV_DIR, name)
    return None


class DeckInput:
    def __init__(self, send, report_interval, on_change=None):
        """`send(report)` delivers one Gamepad Report and returns whether a Host received it.

        `report_interval()` is the time between reports the link can carry right now (ADR-0008).
        `on_change()` is called when the controller becomes readable or stops being readable.
        """
        self._pacer = ReportPacer(send, report_interval)
        self._on_change = on_change
        self._fd = None
        self._retry = None
        self._running = False
        self._missing_logged = False
        self._available = None
        # The last reason the controller could not be opened, for diagnostics.
        self.problem = None

    @property
    def available(self):
        """Whether Deck Controls are being read. A controller that just went away counts as available
        until reopening it fails, because it usually comes straight back after a reset."""
        return bool(self._available)

    def start(self):
        self._running = True
        self._open()

    def stop(self):
        """Stop reading at once. Synchronous, so it is safe while Decky unloads the plugin."""
        self._running = False
        if self._retry is not None:
            self._retry.cancel()
            self._retry = None
        self._close()
        self._pacer.close()

    def _open(self):
        self._retry = None
        if not self._running:
            return
        path = find_controller_node()
        if path is not None:
            try:
                self._fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            except OSError as e:
                if self.problem != "open %s: %r" % (path, e):
                    log.warning("Could not open the Deck's controller at %s: %r", path, e)
                self.problem = "open %s: %r" % (path, e)
            else:
                asyncio.get_running_loop().add_reader(self._fd, self._readable)
                self._missing_logged = False
                self.problem = None
                log.info("Reading Deck Controls from %s", path)
                self._set_available(True)
                return
        else:
            self.problem = "no 28DE:1205 raw controller interface in %s" % HIDRAW_CLASS
            if not self._missing_logged:
                log.warning("The Deck's controller is not available; retrying")
                self._missing_logged = True
        self._retry = asyncio.get_running_loop().call_later(REOPEN_DELAY, self._open)
        self._set_available(False)

    def _set_available(self, available):
        if available == self._available:
            return
        self._available = available
        if self._on_change is not None:
            try:
                self._on_change()
            except Exception:
                log.exception("Controller availability handler failed")

    def _close(self):
        if self._fd is not None:
            try:
                asyncio.get_running_loop().remove_reader(self._fd)
            except RuntimeError:
                pass
            os.close(self._fd)
            self._fd = None

    def _readable(self):
        latest = None
        # hidraw returns one whole report per read; draining them all keeps only the newest state.
        while True:
            try:
                data = os.read(self._fd, DECK_STATE_REPORT_SIZE)
            except BlockingIOError:
                break
            except OSError as e:
                self._lost(repr(e))
                return
            if not data:
                self._lost("end of file")
                return
            report = gamepad_report(data)
            if report is not None:
                latest = report
        if latest is not None:
            self._pacer.offer(latest)

    def _lost(self, reason):
        log.warning("Lost the Deck's controller (%s); reopening", reason)
        self._close()
        self._retry = asyncio.get_running_loop().call_later(REOPEN_DELAY, self._open)
