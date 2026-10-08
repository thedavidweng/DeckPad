"""The single D-Bus call boundary preserves BlueZ errors and bounds unresponsive calls."""

import asyncio
import unittest
from unittest.mock import patch

from dbus_fast import Message, MessageType
from deckpad import bluez


class CallBoundary(unittest.IsolatedAsyncioTestCase):
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
