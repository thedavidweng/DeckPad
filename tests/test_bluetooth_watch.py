"""A watch reports each interruption once and owns its connection even during a cancelled start."""

import asyncio
import unittest
from unittest.mock import patch

from deckpad.bluetooth_watch import BluetoothWatch, SERVICE_STOPPED
from tests.support.plugin_case import PluginTestCase


class WatchInterruptions(PluginTestCase):
    async def test_loss_of_the_watch_bus_is_reported_once(self):
        lost = []
        watch = BluetoothWatch(lost.append)
        await watch.start()
        self.addCleanup(watch.stop)
        watch._bus.disconnect()
        await asyncio.sleep(0.05)
        self.assertEqual(lost, [SERVICE_STOPPED])
        watch.stop()
        await self.bluez.restart()
        await asyncio.sleep(0.05)
        self.assertEqual(lost, [SERVICE_STOPPED])


class CancelledWatchStart(unittest.IsolatedAsyncioTestCase):
    async def test_a_cancelled_connect_releases_its_bus(self):
        class PendingBus:
            closed = False

            async def connect(self):
                await asyncio.Future()

            def disconnect(self):
                self.closed = True

        bus = PendingBus()
        watch = BluetoothWatch(lambda reason: None)
        with patch("deckpad.bluetooth_watch.MessageBus", return_value=bus):
            task = asyncio.create_task(watch.start())
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(bus.closed)
