"""The Troubleshooting section's summary and the plain-text report users attach to bug reports.

Only reads state, and works whether or not controller mode is on or bluetoothd is running.
"""

import asyncio
import collections
import logging
import os
import sys
import time

from . import bluez, connection_interval, deck_controls, device_id, errors, identity

log = logging.getLogger("deckpad.diagnostics")

QUERY_TIMEOUT = 3.0
LOG_LINES = 150


class RecentLog(logging.Handler):
    """Keeps the newest log lines in memory, so diagnostics can include them without reading files."""

    def __init__(self, capacity=LOG_LINES):
        super().__init__(logging.INFO)
        self.lines = collections.deque(maxlen=capacity)
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    def emit(self, record):
        try:
            self.lines.append(self.format(record))
        except Exception:
            self.handleError(record)

    def attach(self, logger):
        if self not in logger.handlers:
            logger.addHandler(self)


RECENT_LOG = RecentLog()
_deckpad_logger = logging.getLogger("deckpad")
# The root logger's level would otherwise drop the INFO lines that explain what happened.
_deckpad_logger.setLevel(logging.INFO)
RECENT_LOG.attach(_deckpad_logger)


async def collect(controller_mode, version=None):
    """Return {"summary": [[label, value], ...], "text": report}."""
    state = controller_mode.diagnostics()
    snapshot = controller_mode.snapshot()
    root = os.geteuid() == 0
    try:
        bt = await asyncio.wait_for(_bluetooth(root), QUERY_TIMEOUT)
    except Exception as e:
        bt = {"running": None, "problem": repr(e)}

    summary = [
        ["Controller Mode", state["status"]],
        ["Bluetooth service", {True: "running", False: "not running", None: "unknown"}[bt["running"]]],
        ["Adapter", _adapter_summary(bt)],
        ["Deck's controls", _controls_summary(state)],
        ["Controller Identity", _identity_summary(root, bt)],
        ["Connection interval", _interval_summary(root, bt)],
        ["Paired devices", str(len(snapshot["hosts"]))],
    ]

    from dbus_fast.__version__ import __version__ as dbus_fast_version

    lines = [
        "DeckPad diagnostics, %s" % _time(time.time()),
        "DeckPad %s, dbus-fast %s, Python %s" % (version or "unknown", dbus_fast_version, sys.version.split()[0]),
        "Running as root: %s" % _yes(root),
        "Controller Mode: %s" % state["status"],
        "Pairing Mode: %s" % state["pairing"],
        "Connection: %s (advertising: %s)" % (state["connection"], state["advertising"] or "no"),
        "Deck's controls: %s" % _controls_summary(state),
    ]
    if state["controls_problem"]:
        lines.append("  %s" % state["controls_problem"])
    if state["status"] == "on":
        lines.append(
            "Gamepad Reports: %d delivered, %d not delivered (no Host subscribed)"
            % (state["reports_delivered"], state["reports_undelivered"])
        )
    if state["link_intervals"]:
        lines.append("Host link intervals: %s" % ", ".join("%.2f ms" % (i * 1000) for i in state["link_intervals"]))
    if bt["running"]:
        lines.append("Bluetooth service: running (pid %s)" % bt.get("pid"))
    elif bt["running"] is False:
        lines.append("Bluetooth service: not running")
    else:
        lines.append("Bluetooth service: unknown (%s)" % bt.get("problem"))
    adapter = bt.get("adapter")
    if adapter is not None:
        lines.append(
            "Adapter: %s %s, powered %s, alias %s, modalias %s"
            % (
                bt["adapter_path"],
                adapter.get("Address"),
                _yes(adapter.get("Powered")),
                adapter.get("Alias"),
                adapter.get("Modalias"),
            )
        )
    elif bt.get("adapter_problem"):
        lines.append("Adapter: %s" % bt["adapter_problem"])
    lines.append("Controller Identity override: %s" % _identity_detail(root, bt))
    lines.append("Shorter connection interval: %s" % _interval_detail(root, bt))
    lines.append("Paired Hosts: %d" % len(snapshot["hosts"]))
    for host in snapshot["hosts"]:
        link = "connected" if host["connected"] else "not connected"
        lines.append("  %s %s (%s)" % (host["address"], host["name"] or "(no name yet)", link))
    if state["errors"]:
        last = state["errors"][-1]
        lines.append("Last error: %s: %s" % (last.code, last.detail or last.message))
        lines.append("Recent errors:")
        for error in state["errors"]:
            lines.append("  %s %s: %s" % (_time(error.occurred_at), error.code, error.detail or error.message))
    else:
        lines.append("Last error: none")
    lines.append("Recent log:")
    lines.extend("  " + line for line in RECENT_LOG.lines)
    return {"summary": summary, "text": "\n".join(lines) + "\n"}


async def _bluetooth(root):
    async with bluez.temporary_connection() as bus:
        result = {"running": True}
        try:
            result["pid"] = await bluez.service_pid(bus)
        except bluez.BluezError:
            return {"running": False}
        try:
            result["adapter_path"], result["adapter"] = await bluez.find_adapter(bus)
        except errors.ControllerModeError as e:
            result["adapter_problem"] = e.code
            return result
        modalias = result["adapter"].get("Modalias")
        if root:
            try:
                result["device_id"] = device_id.current(result["pid"], modalias, identity.DEVICE_ID)
            except Exception as e:
                log.info("Could not read bluetoothd's DeviceID: %r", e)
            index = _index(result["adapter_path"])
            if index is not None:
                try:
                    result["interval"] = connection_interval.current(index)
                except Exception as e:
                    log.info("Could not read the adapter's connection interval: %r", e)
        return result


def _index(adapter_path):
    name = adapter_path.rsplit("/", 1)[-1]
    if name.startswith("hci") and name[3:].isdigit():
        return int(name[3:])
    return None


def _adapter_summary(bt):
    adapter = bt.get("adapter")
    if adapter is not None:
        return "on" if adapter.get("Powered") else "off"
    if bt.get("adapter_problem") == "no_adapter":
        return "not found"
    return "unknown"


def _controls_summary(state):
    if state["controls_reading"] is True:
        return "reading"
    if state["controls_reading"] is False:
        return "not found" if (state["controls_problem"] or "").startswith("no ") else "not readable"
    return "found" if deck_controls.find_controller_node() else "not found"


def _identity_summary(root, bt):
    if not root:
        return "unavailable (needs root)"
    return {
        "controller_identity": "Xbox Wireless Controller (045E:0B13)",
        "bluez": "BlueZ's own",
    }.get(bt.get("device_id"), "unknown")


def _identity_detail(root, bt):
    if not root:
        return "unavailable (needs root)"
    return {"controller_identity": "active", "bluez": "inactive"}.get(bt.get("device_id"), "unknown")


def _interval_summary(root, bt):
    if not root:
        return "unavailable (needs root)"
    interval = bt.get("interval")
    if interval is None:
        return "unknown"
    return "%.2f-%.2f ms" % (interval[0] * 1.25, interval[1] * 1.25)


def _interval_detail(root, bt):
    if not root:
        return "unavailable (needs root)"
    interval = bt.get("interval")
    if interval is None:
        return "adapter range unknown"
    requested = "requested" if tuple(interval) == connection_interval.REQUESTED else "not requested"
    return "%s (adapter range %d-%d, %s)" % (requested, interval[0], interval[1], _interval_summary(root, bt))


def _yes(value):
    return "yes" if value else "no"


def _time(timestamp):
    # time rather than datetime: only modules known to ship in Decky's embedded Python are used.
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))
