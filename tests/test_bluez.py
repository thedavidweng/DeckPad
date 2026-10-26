"""The single D-Bus call boundary preserves BlueZ errors and bounds unresponsive calls."""

import asyncio
import unittest
from unittest.mock import Mock, patch

from dbus_fast import Message, MessageType
from deckpad import bluez


class CallBoundary(unittest.IsolatedAsyncioTestCase):
    async def test_immediate_disconnect_write_failure_is_observed(self):
        sent = asyncio.get_running_loop().create_future()
        sent.set_exception(BrokenPipeError("bus closed"))
        bus = Mock(send=Mock(return_value=sent))
        with self.assertRaises(BrokenPipeError):
            bluez.send_disconnect_device(bus, "/org/bluez/hci0/dev_AA")

    async def test_pending_disconnect_write_failure_is_logged(self):
        sent = asyncio.get_running_loop().create_future()
        bus = Mock(send=Mock(return_value=sent))
        bluez.send_disconnect_device(bus, "/org/bluez/hci0/dev_AA")
        with self.assertLogs("deckpad.bluez", level="WARNING") as logs:
            sent.set_exception(BrokenPipeError("bus closed"))
            await asyncio.sleep(0)
        self.assertIn("Disconnect write failed", logs.output[0])

    async def test_an_unresponsive_daemon_becomes_an_unavailable_error(self):
        class UnresponsiveBus:
            async def call(self, message):
                await asyncio.Future()

        with patch.object(bluez, "CALL_TIMEOUT", 0.01, create=True):
            with self.assertRaises(bluez.BluezError) as failure:
                await asyncio.wait_for(bluez.managed_objects(UnresponsiveBus()), 0.1)
        self.assertTrue(failure.exception.service_unavailable)

    async def test_a_closed_bus_becomes_an_unavailable_error(self):
        class ClosedBus:
            async def call(self, message):
                raise ConnectionError("bus closed")

        with self.assertRaises(bluez.BluezError) as failure:
            await bluez.managed_objects(ClosedBus())
        self.assertTrue(failure.exception.service_unavailable)

    async def test_bluez_error_identity_is_preserved(self):
        class RefusingBus:
            async def call(self, message):
                return Message(message_type=MessageType.ERROR, error_name="org.bluez.Error.NotPermitted",
                               reply_serial=1, signature="s", body=["Permission refused"])

        with self.assertRaises(bluez.BluezError) as failure:
            await bluez.disconnect_device(RefusingBus(), "/org/bluez/hci0/dev_AA")
        self.assertEqual(failure.exception.name, "org.bluez.Error.NotPermitted")
        self.assertEqual(failure.exception.text, "Permission refused")
