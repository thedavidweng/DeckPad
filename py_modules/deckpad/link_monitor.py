"""The Connected Host's connection interval, learned from the Bluetooth controller's HCI events (ADR-0008).

The Host picks the interval and may refuse DeckPad's request for a shorter one, and nothing in BlueZ's
D-Bus API reports it. On the tested Deck the link carried only about one notification per connection
event at long intervals, and BlueZ queues anything beyond that without bound, so the pace follows
the interval: one Gamepad Report per connection event, with a margin.

Reading HCI events needs a raw HCI socket with CAP_NET_RAW (DeckPad runs as root). The socket filter
passes only Disconnect Complete and LE Meta events, so the CPU cost is a few small packets per second
(mostly Steam's scan results, which are dropped).
"""

import asyncio
import logging
import struct

from .hci_socket import HCI_CHANNEL_RAW, open_hci_socket

log = logging.getLogger("deckpad.link_monitor")

# Used while no Host's interval is known: one report per 60 ms is safe at 48.75 ms, the longest
# interval a Host chose in testing.
FALLBACK_REPORT_INTERVAL = 0.06
MARGIN = 1.15

_UNIT = 0.00125
_HCI_EVENT_PKT = 0x04
_EVT_DISCONNECT_COMPLETE = 0x05
_EVT_LE_META = 0x3E
_LE_CONNECTION_COMPLETE = 0x01
_LE_CONNECTION_UPDATE_COMPLETE = 0x03
_LE_ENHANCED_CONNECTION_COMPLETE = 0x0A
_LE_ENHANCED_CONNECTION_COMPLETE_V2 = 0x29
_ROLE_PERIPHERAL = 0x01
_SOL_HCI = 0
_HCI_FILTER = 2


def open_hci_event_socket(index):
    sock = open_hci_socket(index, HCI_CHANNEL_RAW)
    try:
        # struct hci_ufilter: packet type mask, event mask (64 bits), opcode.
        event_mask = (1 << _EVT_DISCONNECT_COMPLETE) | (1 << _EVT_LE_META)
        hci_filter = struct.pack("<IIIH2x", 1 << _HCI_EVENT_PKT, event_mask & 0xFFFFFFFF, event_mask >> 32, 0)
        sock.setsockopt(_SOL_HCI, _HCI_FILTER, hci_filter)
    except BaseException:
        sock.close()
        raise
    return sock


class LinkMonitor:
    def __init__(self, index, open_socket=open_hci_event_socket):
        self._index = index
        self._open_socket = open_socket
        self._sock = None
        # Connection handle -> interval in seconds, for links where the Deck is the Peripheral.
        self._links = {}

    def start(self):
        try:
            self._sock = self._open_socket(self._index)
        except Exception as e:
            log.info("Cannot watch connection intervals, pacing conservatively: %r", e)
            return
        self._sock.setblocking(False)
        asyncio.get_running_loop().add_reader(self._sock.fileno(), self._readable)

    def stop(self):
        """Synchronous, so it is safe while Decky unloads the plugin."""
        if self._sock is not None:
            try:
                asyncio.get_running_loop().remove_reader(self._sock.fileno())
            except RuntimeError:
                pass
            self._sock.close()
            self._sock = None
        self._links.clear()

    def intervals(self):
        """Connection intervals of the current Host links, in seconds."""
        return sorted(self._links.values())

    def report_interval(self):
        """Seconds between Gamepad Reports that the slowest Connected Host's link can carry."""
        if not self._links:
            return FALLBACK_REPORT_INTERVAL
        return max(self._links.values()) * MARGIN

    def _readable(self):
        while True:
            try:
                packet = self._sock.recv(260)
            except (BlockingIOError, InterruptedError):
                return
            except OSError as e:
                log.warning("Stopped watching connection intervals: %r", e)
                self.stop()
                return
            if not packet:
                return
            try:
                self._handle(packet)
            except struct.error:
                pass

    def _handle(self, packet):
        if len(packet) < 3 or packet[0] != _HCI_EVENT_PKT:
            return
        event, params = packet[1], packet[3:]
        if event == _EVT_DISCONNECT_COMPLETE:
            status, handle = struct.unpack_from("<BH", params)
            if status == 0:
                self._forget(handle & 0x0FFF)
        elif event == _EVT_LE_META and params:
            self._handle_le(params[0], params[1:])

    def _handle_le(self, subevent, params):
        if subevent in (_LE_ENHANCED_CONNECTION_COMPLETE, _LE_ENHANCED_CONNECTION_COMPLETE_V2):
            status, handle, role = struct.unpack_from("<BHB", params)
            (interval,) = struct.unpack_from("<H", params, 23)
            self._connected(status, handle & 0x0FFF, role, interval)
        elif subevent == _LE_CONNECTION_COMPLETE:
            status, handle, role = struct.unpack_from("<BHB", params)
            (interval,) = struct.unpack_from("<H", params, 11)
            self._connected(status, handle & 0x0FFF, role, interval)
        elif subevent == _LE_CONNECTION_UPDATE_COMPLETE:
            status, handle, interval = struct.unpack_from("<BHH", params)
            handle &= 0x0FFF
            if status == 0 and handle in self._links:
                self._links[handle] = interval * _UNIT
                log.info("Host link %d now at a %.2f ms connection interval", handle, self._links[handle] * 1000)

    def _connected(self, status, handle, role, interval):
        if status != 0 or role != _ROLE_PERIPHERAL:
            return
        self._links[handle] = interval * _UNIT
        log.info("Host link %d connected at a %.2f ms connection interval", handle, self._links[handle] * 1000)

    def _forget(self, handle):
        self._links.pop(handle, None)
