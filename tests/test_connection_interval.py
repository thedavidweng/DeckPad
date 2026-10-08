"""Asking hosts for a shorter connection interval while controller mode is on.

The kernel sends the Deck's LE connection interval range to every host that connects (an L2CAP
Connection Parameter Update Request), so DeckPad sets that range while controller mode is on and puts
the adapter's own values back afterwards, even if the plugin was killed in between.
"""

import os
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
