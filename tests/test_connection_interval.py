"""Asking hosts for a shorter connection interval while controller mode is on.

The kernel sends the Deck's LE connection interval range to every host that connects (an L2CAP
Connection Parameter Update Request), so DeckPad sets that range while controller mode is on and puts
the adapter's own values back afterwards, even if the plugin was killed in between.
"""

import os
import tempfile
import unittest
import json
from unittest.mock import patch

from deckpad import connection_interval

from tests.support.fake_mgmt import FakeMgmtKernel

# 15-20 ms in the 1.25 ms units of the Bluetooth spec.
REQUESTED = (12, 16)


class RequestingAShorterInterval(unittest.TestCase):
    def setUp(self):
        self.kernel = FakeMgmtKernel(index=0, conn_interval=(24, 40))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state_path = os.path.join(tmp.name, "runtime", "connection_interval.json")

    def request(self, index=0):
        return connection_interval.request(index, self.state_path, open_socket=self.kernel.open_socket)

    def test_hosts_are_asked_for_15_to_20_ms(self):
        request = self.request()

        self.assertIsNotNone(request)
        self.assertEqual(self.kernel.conn_interval, REQUESTED)

    def test_the_adapters_own_range_comes_back_afterwards(self):
        self.kernel.config[0x0017], self.kernel.config[0x0018] = 30, 50
        request = self.request()

        request.restore()

        self.assertEqual(self.kernel.conn_interval, (30, 50))

    def test_restoring_twice_is_harmless(self):
        request = self.request()
        request.restore()
        self.kernel.config[0x0017] = 6

        request.restore()

        self.assertEqual(self.kernel.conn_interval, (6, 40))

    def test_other_adapter_settings_are_untouched(self):
        before = {k: v for k, v in self.kernel.config.items() if k not in (0x0017, 0x0018)}

        self.request().restore()

        self.assertEqual({k: v for k, v in self.kernel.config.items() if k not in (0x0017, 0x0018)}, before)

    def test_without_permission_nothing_changes_and_nothing_fails(self):
        self.kernel.refuse = True

        self.assertIsNone(self.request())
        self.assertEqual(self.kernel.conn_interval, (24, 40))

    def test_an_unknown_adapter_is_left_alone(self):
        self.assertIsNone(self.request(index=3))
        self.assertEqual(self.kernel.conn_interval, (24, 40))
        self.assertFalse(os.path.exists(self.state_path))

    def test_a_failed_save_never_changes_the_adapter(self):
        with patch("os.replace", side_effect=PermissionError):
            self.assertIsNone(self.request())
        self.assertEqual(self.kernel.conn_interval, (24, 40))

    def test_a_lost_set_response_is_rolled_back(self):
        handle = self.kernel.handle

        def lost_response(opcode, index, params):
            response = handle(opcode, index, params)
            if opcode == 0x004C and self.kernel.conn_interval == REQUESTED:
                raise TimeoutError("response lost after apply")
            return response

        with patch.object(self.kernel, "handle", side_effect=lost_response):
            self.assertIsNone(self.request())
        self.assertEqual(self.kernel.conn_interval, (24, 40))
        self.assertFalse(os.path.exists(self.state_path))

    def test_a_success_reply_without_a_setting_change_is_not_success(self):
        handle = self.kernel.handle

        def ignored_set(opcode, index, params):
            if opcode == 0x004C:
                return bytes.fromhex("0100000003004c0000")
            return handle(opcode, index, params)

        with patch.object(self.kernel, "handle", side_effect=ignored_set):
            self.assertIsNone(self.request())
        self.assertEqual(self.kernel.conn_interval, (24, 40))

    def test_a_failed_request_with_failed_rollback_keeps_the_original_record(self):
        handle = self.kernel.handle

        def lost_response(opcode, index, params):
            response = handle(opcode, index, params)
            if opcode == 0x004C:
                self.kernel.refuse = True
                raise TimeoutError("response lost after apply")
            return response

        with patch.object(self.kernel, "handle", side_effect=lost_response):
            self.assertIsNone(self.request())
        with open(self.state_path) as f:
            self.assertEqual(json.load(f), {"address": self.kernel.address, "min": 24, "max": 40})
        self.kernel.refuse = False
        self.assertTrue(connection_interval.restore_leftover(self.state_path, self.kernel.open_socket))
        self.assertEqual(self.kernel.conn_interval, (24, 40))

    def test_restore_requires_readback_before_removing_the_record(self):
        request = self.request()
        handle = self.kernel.handle

        def ignored_set(opcode, index, params):
            if opcode == 0x004C:
                return bytes.fromhex("0100000003004c0000")
            return handle(opcode, index, params)

        with patch.object(self.kernel, "handle", side_effect=ignored_set):
            self.assertIs(request.restore(), False)
        self.assertEqual(self.kernel.conn_interval, REQUESTED)
        self.assertTrue(os.path.exists(self.state_path))

    def test_restore_does_not_overwrite_another_programs_change(self):
        request = self.request()
        self.kernel.config[0x0017], self.kernel.config[0x0018] = 32, 48
        self.assertIs(request.restore(), False)
        self.assertEqual(self.kernel.conn_interval, (32, 48))
        self.assertTrue(os.path.exists(self.state_path))

    def test_failed_restore_keeps_the_record_for_a_later_retry(self):
        request = self.request()
        self.kernel.refuse = True
        self.assertIs(request.restore(), False)
        self.assertTrue(os.path.exists(self.state_path))
        self.kernel.refuse = False
        self.assertTrue(connection_interval.restore_leftover(self.state_path, self.kernel.open_socket))
        self.assertEqual(self.kernel.conn_interval, (24, 40))

    def test_an_unresolved_transaction_is_not_replaced_by_a_new_request(self):
        self.request()
        self.kernel.config[0x0017], self.kernel.config[0x0018] = 32, 48
        self.assertIsNone(self.request())
        self.assertEqual(self.kernel.conn_interval, (32, 48))
        with open(self.state_path) as f:
            self.assertEqual(json.load(f), {"address": self.kernel.address, "min": 24, "max": 40})

    def test_restore_follows_the_same_adapter_after_index_changes(self):
        request = self.request()
        self.kernel.index = 1
        self.assertTrue(request.restore())
        self.assertEqual(self.kernel.conn_interval, (24, 40))
        self.assertFalse(os.path.exists(self.state_path))

    def test_restore_never_writes_a_replacement_at_the_old_index(self):
        request = self.request()
        self.kernel.address = "01:02:03:04:05:06"
        self.assertFalse(request.restore())
        self.assertEqual(self.kernel.conn_interval, REQUESTED)
        self.assertTrue(os.path.exists(self.state_path))

    def test_identity_change_during_restore_read_prevents_write(self):
        request = self.request()
        handle = self.kernel.handle

        def changed_adapter(opcode, index, params):
            reply = handle(opcode, index, params)
            if opcode == 0x004B:
                self.kernel.address = "01:02:03:04:05:06"
            return reply

        with patch.object(self.kernel, "handle", side_effect=changed_adapter):
            self.assertFalse(request.restore())
        self.assertEqual(self.kernel.conn_interval, REQUESTED)
        self.assertTrue(os.path.exists(self.state_path))


class NotWhilePairing(unittest.TestCase):
    """A host that switches interval in the middle of pairing can drop the link and cancel the pairing."""

    def setUp(self):
        self.kernel = FakeMgmtKernel(index=0, conn_interval=(24, 40))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.shorter = connection_interval.ShorterInterval(
            0, os.path.join(tmp.name, "connection_interval.json"), open_socket=self.kernel.open_socket
        )

    def test_paired_hosts_reconnecting_are_asked_for_15_to_20_ms(self):
        self.shorter.update(pairing=False)

        self.assertEqual(self.kernel.conn_interval, REQUESTED)

    def test_hosts_connecting_to_pair_keep_their_own_interval(self):
        self.shorter.update(pairing=False)

        self.shorter.update(pairing=True)

        self.assertEqual(self.kernel.conn_interval, (24, 40))

    def test_the_request_returns_when_pairing_mode_closes(self):
        self.shorter.update(pairing=True)
        self.shorter.update(pairing=False)

        self.assertEqual(self.kernel.conn_interval, REQUESTED)

    def test_closing_puts_the_adapters_range_back(self):
        self.shorter.update(pairing=False)

        self.shorter.close()

        self.assertEqual(self.kernel.conn_interval, (24, 40))

    def test_repeated_updates_do_not_touch_the_adapter_again(self):
        self.shorter.update(pairing=False)
        opened = self.kernel.sockets_opened

        self.shorter.update(pairing=False)

        self.assertEqual(self.kernel.sockets_opened, opened)


class AfterThePluginWasKilled(unittest.TestCase):
    def setUp(self):
        self.kernel = FakeMgmtKernel(index=0, conn_interval=(24, 40))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state_path = os.path.join(tmp.name, "connection_interval.json")

    def test_the_next_start_puts_the_adapters_range_back(self):
        connection_interval.request(0, self.state_path, open_socket=self.kernel.open_socket)
        # SIGKILL: restore() never runs.

        restored = connection_interval.restore_leftover(self.state_path, open_socket=self.kernel.open_socket)

        self.assertTrue(restored)
        self.assertEqual(self.kernel.conn_interval, (24, 40))

    def test_a_clean_stop_leaves_nothing_to_restore(self):
        connection_interval.request(0, self.state_path, open_socket=self.kernel.open_socket).restore()
        self.kernel.config[0x0017] = 6

        restored = connection_interval.restore_leftover(self.state_path, open_socket=self.kernel.open_socket)

        self.assertFalse(restored)
        self.assertEqual(self.kernel.conn_interval, (6, 40))

    def test_nothing_to_restore_on_a_first_start(self):
        self.assertFalse(connection_interval.restore_leftover(self.state_path, open_socket=self.kernel.open_socket))
        self.assertEqual(self.kernel.sockets_opened, 0)

    def test_an_invalid_record_is_preserved_without_system_writes(self):
        for value in (True, -1, 65536, "24"):
            with self.subTest(value=value):
                with open(self.state_path, "w") as f:
                    json.dump({"address": self.kernel.address, "min": value, "max": 40}, f)
                self.assertFalse(connection_interval.restore_leftover(self.state_path, self.kernel.open_socket))
                self.assertEqual(self.kernel.sockets_opened, 0)
                self.assertTrue(os.path.exists(self.state_path))

    def test_index_only_record_is_preserved_without_guessing_ownership(self):
        with open(self.state_path, "w") as f:
            json.dump({"index": 0, "min": 24, "max": 40}, f)
        self.assertFalse(connection_interval.restore_leftover(self.state_path, self.kernel.open_socket))
        self.assertEqual(self.kernel.sockets_opened, 0)
        self.assertTrue(os.path.exists(self.state_path))

    def test_invalid_adapter_addresses_are_rejected_before_opening_socket(self):
        for address in (None, "00:00:00:00:00:00", "e8:fb:1c:43:f3:44", "E8FB1C43F344", "not a MAC"):
            with self.subTest(address=address):
                with open(self.state_path, "w") as f:
                    json.dump({"address": address, "min": 24, "max": 40}, f)
                self.assertFalse(connection_interval.restore_leftover(self.state_path, self.kernel.open_socket))
                self.assertEqual(self.kernel.sockets_opened, 0)


class MgmtValidation(unittest.TestCase):
    def test_malformed_controller_information_is_rejected(self):
        for data in (bytes(279), bytes(281), bytes(280)):
            kernel = FakeMgmtKernel()
            mgmt = connection_interval._Mgmt(kernel.open_socket)
            self.addCleanup(mgmt.close)
            with self.subTest(length=len(data)), patch.object(mgmt, "command", return_value=data):
                with self.assertRaises(ValueError):
                    mgmt.read_address(0)

    def test_malformed_index_lists_are_rejected(self):
        for data in (b"", b"\x01", bytes.fromhex("0100"), bytes.fromhex("010000000100"),
                     bytes.fromhex("020000000000"), bytes.fromhex("0100ffff")):
            kernel = FakeMgmtKernel()
            mgmt = connection_interval._Mgmt(kernel.open_socket)
            self.addCleanup(mgmt.close)
            with self.subTest(data=data), patch.object(mgmt, "command", return_value=data):
                with self.assertRaises(ValueError):
                    mgmt.find_adapter(kernel.address)

    def test_malformed_tlvs_are_rejected(self):
        for data in (b"\x17", bytes.fromhex("1700020c"), bytes.fromhex("1700010c"),
                     bytes.fromhex("1700020c001700020d00")):
            with self.subTest(data=data), self.assertRaises(ValueError):
                connection_interval._parse_tlvs(data)

    def test_malformed_replies_are_rejected(self):
        for packet in (bytes.fromhex("0100000004004b0000"), bytes.fromhex("0100000002004b00"),
                       bytes.fromhex("0200000004004b000001")):
            kernel = FakeMgmtKernel()
            with self.subTest(packet=packet), patch.object(kernel, "handle", return_value=packet):
                with self.assertRaises(ValueError):
                    connection_interval.current(0, kernel.open_socket)


if __name__ == "__main__":
    unittest.main()
