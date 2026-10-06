"""Asking Hosts for a 15-20 ms LE connection interval while Controller Mode is on (ADR-0008).

When a Host connects, the kernel compares the connection's interval with the adapter's default LE
connection interval range and, if it falls outside, sends the Host an L2CAP Connection Parameter Update
Request for that range (net/bluetooth/l2cap_core.c, l2cap_le_conn_ready). The range is the same one
main.conf's [LE] Min/MaxConnectionInterval set, and the MGMT Set Default System Configuration command
changes it at runtime (root only). The adapter's previous range is saved to a file first, so a later
start can put it back if DeckPad was killed before restoring it.
"""

import json
import logging
import os
import struct
import time

from .hci_socket import HCI_CHANNEL_CONTROL, HCI_DEV_NONE, open_hci_socket

log = logging.getLogger("deckpad.connection_interval")

# 1.25 ms units: 15-20 ms. 8.75-11.25 ms carried more reports but made links drop right after the
# update more often on the tested Host (ADR-0008).
REQUESTED = (12, 16)

_READ_DEF_SYSTEM_CONFIG = 0x004B
_SET_DEF_SYSTEM_CONFIG = 0x004C
_EV_CMD_COMPLETE = 0x0001
_EV_CMD_STATUS = 0x0002
_LE_MIN_CONN_INTERVAL = 0x0017
_LE_MAX_CONN_INTERVAL = 0x0018
_TIMEOUT = 0.5


def open_mgmt_socket():
    return open_hci_socket(HCI_DEV_NONE, HCI_CHANNEL_CONTROL)


class _Mgmt:
    def __init__(self, open_socket):
        self._sock = open_socket()
        self._sock.settimeout(_TIMEOUT)

    def close(self):
        self._sock.close()

    def command(self, opcode, index, params=b""):
        """Send one MGMT command and return its reply parameters. Raises OSError if the kernel refuses."""
        self._sock.send(struct.pack("<HHH", opcode, index, len(params)) + params)
        deadline = time.monotonic() + _TIMEOUT
        while time.monotonic() < deadline:
            packet = self._sock.recv(1024)
            if len(packet) < 9:
                continue
            event, event_index, _length = struct.unpack_from("<HHH", packet)
            reply_opcode, status = struct.unpack_from("<HB", packet, 6)
            if event not in (_EV_CMD_COMPLETE, _EV_CMD_STATUS) or reply_opcode != opcode or event_index != index:
                continue
            if status != 0:
                raise OSError("MGMT command 0x%04x failed with status 0x%02x" % (opcode, status))
            return packet[9:]
        raise TimeoutError("MGMT command 0x%04x got no reply" % opcode)

    def read_conn_interval(self, index):
        tlvs = _parse_tlvs(self.command(_READ_DEF_SYSTEM_CONFIG, index))
        return (tlvs[_LE_MIN_CONN_INTERVAL], tlvs[_LE_MAX_CONN_INTERVAL])

    def set_conn_interval(self, index, interval):
        # The kernel checks nothing about the pair, so the order of the two values does not matter.
        params = struct.pack("<HBHHBH", _LE_MIN_CONN_INTERVAL, 2, interval[0], _LE_MAX_CONN_INTERVAL, 2, interval[1])
        self.command(_SET_DEF_SYSTEM_CONFIG, index, params)


def _parse_tlvs(data):
    values = {}
    offset = 0
    while offset + 3 <= len(data):
        kind, length = struct.unpack_from("<HB", data, offset)
        if length == 2:
            (values[kind],) = struct.unpack_from("<H", data, offset + 3)
        offset += 3 + length
    return values


class IntervalRequest:
    def __init__(self, index, previous, state_path, open_socket):
        self._index = index
        self._previous = previous
        self._state_path = state_path
        self._open_socket = open_socket

    def restore(self):
        """Put the adapter's own range back. Synchronous and quick, so it is safe during plugin unload."""
        if self._previous is None:
            return
        try:
            _set(self._open_socket, self._index, self._previous)
        except Exception as e:
            log.warning("Could not restore the adapter's connection interval: %r", e)
            return
        self._previous = None
        _forget(self._state_path)
        log.info("Restored the adapter's connection interval")


def request(index, state_path, open_socket=open_mgmt_socket):
    """Ask Hosts that connect from now on for the REQUESTED interval. Returns None if that is not possible."""
    try:
        mgmt = _Mgmt(open_socket)
    except Exception as e:
        log.info("Cannot change the connection interval: %r", e)
        return None
    try:
        previous = mgmt.read_conn_interval(index)
        if previous != REQUESTED:
            _remember(state_path, index, previous)
            mgmt.set_conn_interval(index, REQUESTED)
    except Exception as e:
        log.warning("Could not request a shorter connection interval: %r", e)
        _forget(state_path)
        return None
    finally:
        mgmt.close()
    log.info("Hosts are asked for a %.2f-%.2f ms connection interval", REQUESTED[0] * 1.25, REQUESTED[1] * 1.25)
    return IntervalRequest(index, previous if previous != REQUESTED else None, state_path, open_socket)


class ShorterInterval:
    """The request, held only while Pairing Mode is not accepting new Hosts.

    On the tested Host the switch to the shorter interval sometimes dropped the link, and a drop
    during pairing cancels the pairing. Paired Hosts reconnecting recover by reconnecting again.
    """

    def __init__(self, index, state_path, open_socket=open_mgmt_socket):
        self._index = index
        self._state_path = state_path
        self._open_socket = open_socket
        self._request = None
        self._requested = False

    def update(self, pairing):
        if pairing and self._requested:
            self.close()
        elif not pairing and not self._requested:
            self._requested = True
            self._request = request(self._index, self._state_path, open_socket=self._open_socket)

    def close(self):
        self._requested = False
        request, self._request = self._request, None
        if request is not None:
            request.restore()


def restore_leftover(state_path, open_socket=open_mgmt_socket):
    """At backend start, undo a request that a killed DeckPad process left in place. Returns whether it did."""
    try:
        with open(state_path) as f:
            saved = json.load(f)
        index, previous = saved["index"], (saved["min"], saved["max"])
    except FileNotFoundError:
        return False
    except Exception as e:
        log.warning("Ignoring unreadable %s: %r", state_path, e)
        _forget(state_path)
        return False
    try:
        _set(open_socket, index, previous)
    except Exception as e:
        log.warning("Could not restore the adapter's connection interval: %r", e)
        return False
    _forget(state_path)
    return True


def _set(open_socket, index, interval):
    mgmt = _Mgmt(open_socket)
    try:
        mgmt.set_conn_interval(index, interval)
    finally:
        mgmt.close()


def _remember(state_path, index, previous):
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w") as f:
        json.dump({"index": index, "min": previous[0], "max": previous[1]}, f)


def _forget(state_path):
    try:
        os.unlink(state_path)
    except FileNotFoundError:
        pass
