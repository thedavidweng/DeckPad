"""Session resources must be released even when connection setup or teardown is cancelled."""

import asyncio
import unittest
from unittest.mock import patch

from deckpad import peripheral, bluez
from tests.support.plugin_case import PluginTestCase


class CancelledConnection(unittest.IsolatedAsyncioTestCase):
    async def test_cancelling_a_connect_closes_the_owned_bus(self):
        class PendingBus:
            closed = False

            async def connect(self):
                await asyncio.Future()

            def disconnect(self):
                self.closed = True

        bus = PendingBus()
        session = peripheral.Peripheral()
        with patch.object(peripheral, "MessageBus", return_value=bus):
            task = asyncio.create_task(session.start())
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(bus.closed)


class CancelledTeardown(PluginTestCase):
    async def test_failed_advertisement_removal_keeps_ownership_visible(self):
        session = peripheral.Peripheral()
        await session.start()
        self.addCleanup(session.close)
        await session.advertise()
        with patch.object(bluez, "unregister_advertisement", side_effect=bluez.BluezError("org.bluez.Error.Failed", "busy")):
            with self.assertRaises(bluez.BluezError):
                await session.stop_advertising()
        self.assertEqual(session.advertising, "discoverable")
        await session.stop_advertising()
        self.assertIsNone(session.advertising)

    async def test_an_advertisement_reply_after_close_cannot_revive_session_state(self):
        session = peripheral.Peripheral()
        await session.start()
        self.addCleanup(session.close)
        register = bluez.register_advertisement

        async def closed_before_reply(*args):
            await register(*args)
            session.close()

        with patch.object(bluez, "register_advertisement", side_effect=closed_before_reply):
            await session.advertise()
        self.assertIsNone(session.advertising)
        self.assertTrue(await self.bluez.wait_until_clean(), self.bluez.registrations())

    async def test_cancelled_teardown_releases_every_registration(self):
        session = peripheral.Peripheral()
        await session.start()
        self.addCleanup(session.close)
        self.bluez.hang_unregister = True
        task = asyncio.create_task(session.stop())
        await asyncio.sleep(0.02)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(await self.bluez.wait_until_clean(), self.bluez.registrations())
