"""Asks hosts for a 15-20 ms LE connection interval while controller mode is on.

When a host connects, the kernel compares the connection's interval with the adapter's default LE
connection interval range and, if it falls outside, sends the host an L2CAP Connection Parameter Update
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
from . import storage

log = logging.getLogger("deckpad.connection_interval")

# 1.25 ms units: 15-20 ms. 8.75-11.25 ms carried more reports but made links drop right after the
# update more often on the tested host.
REQUESTED = (12, 16)

_READ_DEF_SYSTEM_CONFIG = 0x004B
_SET_DEF_SYSTEM_CONFIG = 0x004C
_READ_INDEX_LIST = 0x0003
_READ_INFO = 0x0004
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
        try:
            self._sock.settimeout(_TIMEOUT)
        except BaseException:
            self._sock.close()
            raise

    def close(self):
        self._sock.close()

    def command(self, opcode, index, params=b""):
        """Send one MGMT command and return its reply parameters. Raises OSError if the kernel refuses."""
        command = struct.pack("<HHH", opcode, index, len(params)) + params
        if self._sock.send(command) != len(command):
            raise OSError("Incomplete MGMT command write")
        deadline = time.monotonic() + _TIMEOUT
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._sock.settimeout(remaining)
            packet = self._sock.recv(65541)
            if len(packet) < 6:
                raise ValueError("Truncated MGMT header")
            event, event_index, length = struct.unpack_from("<HHH", packet)
            if length != len(packet) - 6:
                raise ValueError("MGMT payload length mismatch")
            if event not in (_EV_CMD_COMPLETE, _EV_CMD_STATUS) or event_index != index:
                continue
            if length < 3 or (event == _EV_CMD_STATUS and length != 3):
                raise ValueError("Invalid MGMT command response length")
            reply_opcode, status = struct.unpack_from("<HB", packet, 6)
            if reply_opcode != opcode:
                continue
            if status != 0:
                raise OSError("MGMT command 0x%04x failed with status 0x%02x" % (opcode, status))
            if event == _EV_CMD_COMPLETE:
                return packet[9:]
        raise TimeoutError("MGMT command 0x%04x got no reply" % opcode)

    def read_conn_interval(self, index):
        tlvs = _parse_tlvs(self.command(_READ_DEF_SYSTEM_CONFIG, index))
        try:
            interval = (tlvs[_LE_MIN_CONN_INTERVAL], tlvs[_LE_MAX_CONN_INTERVAL])
        except KeyError as e:
            raise ValueError("MGMT response lacks connection interval") from e
        _validate_interval(interval)
        return interval

    def read_address(self, index):
        info = self.command(_READ_INFO, index)
        if len(info) != 280:
            raise ValueError("Invalid MGMT controller information length")
        address = ":".join("%02X" % value for value in info[:6][::-1])
        _validate_address(address)
        return address

    def find_adapter(self, address):
        data = self.command(_READ_INDEX_LIST, HCI_DEV_NONE)
        if len(data) < 2:
            raise ValueError("Truncated MGMT controller index list")
        count = struct.unpack_from("<H", data)[0]
        if len(data) != 2 + 2 * count:
            raise ValueError("Invalid MGMT controller index list length")
        indices = struct.unpack_from("<%dH" % count, data, 2)
        if len(set(indices)) != count or HCI_DEV_NONE in indices:
            raise ValueError("Invalid MGMT controller indices")
        matches = [index for index in indices if self.read_address(index) == address]
        if len(matches) != 1:
            raise OSError("Saved Bluetooth adapter is absent or ambiguous")
        return matches[0]

    def set_conn_interval(self, index, interval):
        # The kernel checks nothing about the pair, so the order of the two values does not matter.
        params = struct.pack("<HBHHBH", _LE_MIN_CONN_INTERVAL, 2, interval[0], _LE_MAX_CONN_INTERVAL, 2, interval[1])
        if self.command(_SET_DEF_SYSTEM_CONFIG, index, params):
            raise ValueError("Unexpected MGMT set response parameters")


def _parse_tlvs(data):
    values = {}
    offset = 0
    seen = set()
    while offset < len(data):
        if offset + 3 > len(data):
            raise ValueError("Truncated MGMT TLV header")
        kind, length = struct.unpack_from("<HB", data, offset)
        if offset + 3 + length > len(data):
            raise ValueError("Truncated MGMT TLV value")
        if kind in seen:
            raise ValueError("Duplicate MGMT TLV")
        seen.add(kind)
        if kind in (_LE_MIN_CONN_INTERVAL, _LE_MAX_CONN_INTERVAL) and length != 2:
            raise ValueError("Invalid connection interval TLV length")
        if length == 2:
            (values[kind],) = struct.unpack_from("<H", data, offset + 3)
        offset += 3 + length
    return values


def _validate_interval(interval):
    if any(type(value) is not int for value in interval) or not 6 <= interval[0] <= interval[1] <= 3200:
        raise ValueError("Invalid LE connection interval range")


def _validate_address(address):
    if not isinstance(address, str):
        raise ValueError("Invalid Bluetooth adapter address")
    raw = bytes.fromhex(address.replace(":", ""))
    if len(raw) != 6 or not any(raw) or address != ":".join("%02X" % value for value in raw):
        raise ValueError("Invalid Bluetooth adapter address")


class IntervalRequest:
    def __init__(self, state_path, open_socket):
        self._state_path = state_path
        self._open_socket = open_socket

    def restore(self):
        """Put the adapter's own range back. Synchronous and quick, so it is safe during plugin unload."""
        if self._state_path is None:
            return True
        if not restore_leftover(self._state_path, self._open_socket):
            return False
        self._state_path = None
        log.info("Restored the adapter's connection interval")
        return True


def request(index, state_path, open_socket=open_mgmt_socket):
    """Ask hosts that connect from now on for the REQUESTED interval. Returns None if that is not possible."""
    if os.path.exists(state_path) and not restore_leftover(state_path, open_socket):
        log.warning("Cannot change connection interval: an earlier transaction is unresolved")
        return None
    try:
        mgmt = _Mgmt(open_socket)
    except Exception as e:
        log.info("Cannot change the connection interval: %r", e)
        return None
    try:
        address = mgmt.read_address(index)
        previous = mgmt.read_conn_interval(index)
        if previous != REQUESTED:
            _remember(state_path, address, previous)
            if mgmt.read_address(index) != address:
                raise OSError("Bluetooth adapter changed before interval request")
            mgmt.set_conn_interval(index, REQUESTED)
            if mgmt.read_conn_interval(index) != REQUESTED or mgmt.read_address(index) != address:
                raise OSError("Connection interval request verification failed")
    except Exception as e:
        log.warning("Could not request a shorter connection interval: %r", e)
        restore_leftover(state_path, open_socket)
        return None
    finally:
        mgmt.close()
    log.info("Hosts are asked for a %.2f-%.2f ms connection interval", REQUESTED[0] * 1.25, REQUESTED[1] * 1.25)
    return IntervalRequest(state_path if previous != REQUESTED else None, open_socket)


class ShorterInterval:
    """The request, held only while pairing mode is closed.

    On the tested host the switch to the shorter interval sometimes dropped the link, and a drop
    during pairing cancels the pairing. A paired host that drops simply reconnects.
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


def current(index, open_socket=open_mgmt_socket):
    """The adapter's default LE connection interval range (min, max) in 1.25 ms units. Needs root."""
    mgmt = _Mgmt(open_socket)
    try:
        return mgmt.read_conn_interval(index)
    finally:
        mgmt.close()


def restore_leftover(state_path, open_socket=open_mgmt_socket):
    """Undo a request that a killed DeckPad process left in place. Returns whether it did."""
    try:
        with open(state_path) as f:
            saved = json.load(f)
        address, previous = saved["address"], (saved["min"], saved["max"])
        _validate_address(address)
        _validate_interval(previous)
    except FileNotFoundError:
        return False
    except Exception as e:
        log.warning("Ignoring unreadable %s: %r", state_path, e)
        return False
    try:
        _restore(open_socket, address, previous)
    except Exception as e:
        log.warning("Could not restore the adapter's connection interval: %r", e)
        return False
    storage.erase(state_path)
    return True


def _restore(open_socket, address, interval):
    mgmt = _Mgmt(open_socket)
    try:
        index = mgmt.find_adapter(address)
        current = mgmt.read_conn_interval(index)
        if mgmt.read_address(index) != address:
            raise OSError("Bluetooth adapter changed before interval restore")
        if current == interval:
            return
        if current != REQUESTED:
            raise OSError("Connection interval changed outside DeckPad; refusing to overwrite it")
        mgmt.set_conn_interval(index, interval)
        if mgmt.read_conn_interval(index) != interval or mgmt.read_address(index) != address:
            raise OSError("Connection interval restore verification failed")
    finally:
        mgmt.close()


def _remember(state_path, address, previous):
    storage.save(state_path, {"address": address, "min": previous[0], "max": previous[1]})
