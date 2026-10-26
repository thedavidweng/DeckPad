"""Pacing gamepad reports to the connected host's actual connection interval.

The link carries about one notification per connection event at worst, and the host decides the
interval (it may refuse DeckPad's request). DeckPad learns it from the controller's HCI events.
HCI packets below follow the Bluetooth Core spec, Vol 4 Part E 7.7 (with the H:4 packet type byte).
"""

import asyncio
import socket
import struct
import unittest
from unittest.mock import Mock

from deckpad.link_monitor import FALLBACK_REPORT_INTERVAL, LinkMonitor

PERIPHERAL = 0x01
CENTRAL = 0x00
HOST = bytes.fromhex("69e9c3d3f938")  # 38:F9:D3:C3:E9:69, little-endian


def le_enhanced_connection_complete(handle, role, interval, status=0):
    params = struct.pack("<BBHBB6s6s6sHHHB", 0x0A, status, handle, role, 0, HOST, bytes(6), bytes(6), interval, 0, 42, 0)
    return bytes([0x04, 0x3E, len(params)]) + params


def le_connection_complete(handle, role, interval):
    params = struct.pack("<BBHBB6sHHHB", 0x01, 0, handle, role, 0, HOST, interval, 0, 42, 0)
    return bytes([0x04, 0x3E, len(params)]) + params


def le_connection_update_complete(handle, interval, status=0):
    params = struct.pack("<BBHHHH", 0x03, status, handle, interval, 0, 42)
    return bytes([0x04, 0x3E, len(params)]) + params


def disconnect_complete(handle):
    return bytes([0x04, 0x05, 4]) + struct.pack("<BHB", 0, handle, 0x13)


def le_advertising_report():
    params = bytes([0x0D, 1]) + bytes(24)
    return bytes([0x04, 0x3E, len(params)]) + params


class LinkCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.controller, ours = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(self.controller.close)
        self.opened = []

        def open_socket(index):
            self.opened.append(index)
            return ours

        self.monitor = LinkMonitor(0, open_socket=open_socket)
        self.monitor.start()
        self.addCleanup(self.monitor.stop)

    async def events(self, *packets):
        for packet in packets:
            self.controller.send(packet)
        await asyncio.sleep(0.05)


class PacingToTheConnectedHost(LinkCase):
    async def test_until_a_host_connects_the_pace_is_conservative(self):
        self.assertEqual(self.monitor.report_interval(), FALLBACK_REPORT_INTERVAL)
        # Safe even for the longest interval seen on a host (48.75 ms).
        self.assertGreaterEqual(FALLBACK_REPORT_INTERVAL, 0.05)

    async def test_a_host_at_its_default_interval_gets_about_one_report_per_connection_event(self):
        await self.events(le_enhanced_connection_complete(24, PERIPHERAL, 0x27))  # 48.75 ms

        self.assertGreater(self.monitor.report_interval(), 0.04875)
        self.assertLess(self.monitor.report_interval(), 0.06)

    async def test_accepting_a_shorter_interval_speeds_reports_up(self):
        await self.events(
            le_enhanced_connection_complete(24, PERIPHERAL, 0x27),
            le_connection_update_complete(24, 0x0F),  # 18.75 ms
        )

        self.assertGreater(self.monitor.report_interval(), 0.01875)
        self.assertLess(self.monitor.report_interval(), 0.025)

    async def test_legacy_connection_complete_events_count_too(self):
        await self.events(le_connection_complete(7, PERIPHERAL, 0x18))  # 30 ms

        self.assertGreater(self.monitor.report_interval(), 0.030)
        self.assertLess(self.monitor.report_interval(), 0.036)

    async def test_enhanced_v2_events_keep_the_same_interval_layout(self):
        v1 = le_enhanced_connection_complete(24, PERIPHERAL, 15)
        params = b"\x29" + v1[4:] + bytes.fromhex("ffffff")
        await self.events(bytes([4, 0x3E, len(params)]) + params)
        self.assertGreater(self.monitor.report_interval(), 0.01875)
        self.assertLess(self.monitor.report_interval(), 0.025)

    async def test_the_shortest_interval_carries_over_100_reports_per_second(self):
        await self.events(le_enhanced_connection_complete(24, PERIPHERAL, 6))  # 7.5 ms

        self.assertGreater(self.monitor.report_interval(), 0.0075)
        self.assertLess(self.monitor.report_interval(), 0.01)

    async def test_after_the_host_disconnects_the_pace_is_conservative_again(self):
        await self.events(le_enhanced_connection_complete(24, PERIPHERAL, 0x0F), disconnect_complete(24))

        self.assertEqual(self.monitor.report_interval(), FALLBACK_REPORT_INTERVAL)

    async def test_the_slowest_of_several_hosts_sets_the_pace(self):
        await self.events(
            le_enhanced_connection_complete(24, PERIPHERAL, 0x0F),
            le_enhanced_connection_complete(25, PERIPHERAL, 0x27),
        )

        self.assertGreater(self.monitor.report_interval(), 0.04875)


class LinksThatAreNotHosts(LinkCase):
    async def test_devices_the_deck_connects_to_itself_are_ignored(self):
        # e.g. a BLE controller or keyboard paired to the Deck: the Deck is central there.
        await self.events(le_enhanced_connection_complete(30, CENTRAL, 6), le_connection_update_complete(30, 6))

        self.assertEqual(self.monitor.report_interval(), FALLBACK_REPORT_INTERVAL)

    async def test_failed_connections_and_updates_change_nothing(self):
        await self.events(
            le_enhanced_connection_complete(24, PERIPHERAL, 0x27),
            le_enhanced_connection_complete(26, PERIPHERAL, 6, status=0x3E),
            le_connection_update_complete(24, 6, status=0x3B),
        )

        self.assertGreater(self.monitor.report_interval(), 0.04875)

    async def test_scan_results_and_garbage_are_ignored(self):
        await self.events(le_advertising_report(), b"\x04\x3e", b"\x02\x18\x00", le_connection_update_complete(99, 6))

        self.assertEqual(self.monitor.report_interval(), FALLBACK_REPORT_INTERVAL)

    async def test_bad_lengths_handles_roles_and_intervals_cannot_change_the_pace(self):
        valid = le_enhanced_connection_complete(24, PERIPHERAL, 15)
        packets = (
            valid[:-1], valid + b"\x00", valid[:2] + b"\x00" + valid[3:],
            le_enhanced_connection_complete(0x1018, PERIPHERAL, 15),
            le_enhanced_connection_complete(0x0F00, PERIPHERAL, 15),
            le_enhanced_connection_complete(24, 2, 15),
            le_enhanced_connection_complete(24, PERIPHERAL, 0),
            le_enhanced_connection_complete(24, PERIPHERAL, 3201),
        )
        for packet in packets:
            with self.subTest(packet=packet):
                await self.events(packet)
                self.assertEqual(self.monitor.report_interval(), FALLBACK_REPORT_INTERVAL)

    async def test_invalid_updates_and_disconnects_do_not_alias_a_live_handle(self):
        await self.events(le_enhanced_connection_complete(24, PERIPHERAL, 39))
        before = self.monitor.report_interval()
        await self.events(le_connection_update_complete(0x1018, 6), disconnect_complete(0x1018),
                          le_connection_update_complete(24, 0))
        self.assertEqual(self.monitor.report_interval(), before)

    async def test_a_closed_event_socket_restores_conservative_pacing(self):
        await self.events(le_enhanced_connection_complete(24, PERIPHERAL, 15))
        self.controller.close()
        await asyncio.sleep(0.05)
        self.assertEqual(self.monitor.report_interval(), FALLBACK_REPORT_INTERVAL)


class WithoutAccessToTheController(unittest.IsolatedAsyncioTestCase):
    async def test_reader_registration_failure_closes_the_socket(self):
        sock = Mock()
        sock.fileno.return_value = -1
        monitor = LinkMonitor(0, open_socket=lambda index: sock)
        monitor.start()
        sock.close.assert_called_once()
        self.assertEqual(monitor.report_interval(), FALLBACK_REPORT_INTERVAL)

    async def test_the_pace_stays_conservative(self):
        def refuse(index):
            raise PermissionError(1, "Operation not permitted")

        monitor = LinkMonitor(0, open_socket=refuse)
        monitor.start()
        monitor.stop()

        self.assertEqual(monitor.report_interval(), FALLBACK_REPORT_INTERVAL)


if __name__ == "__main__":
    unittest.main()
