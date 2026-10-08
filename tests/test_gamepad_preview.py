"""A closed Controller Screen must cancel even an in-flight preview."""

import asyncio
import unittest

from deckpad.gamepad_preview import GamepadPreview
from deckpad.gamepad_report import AT_REST


class PreviewSubscription(unittest.IsolatedAsyncioTestCase):
    async def test_unsubscribing_cancels_pending_publish(self):
        entered = asyncio.Event()
        release = asyncio.Event()
        published = []

        async def publish(report):
            entered.set()
            await release.wait()
            published.append(report)

        preview = GamepadPreview(publish, interval=0.01)
        self.addCleanup(preview.close)
        preview.watch(True)
        await entered.wait()
        preview.watch(False)
        release.set()
        await asyncio.sleep(0)
        self.assertEqual(published, [])
        self.assertIsNone(preview._timer)
        preview.watch(True)
        await asyncio.sleep(0)
        self.assertEqual(len(published), 1)

    async def test_repeated_subscription_does_not_bypass_the_update_interval(self):
        published = []

        async def publish(report):
            published.append(report)

        preview = GamepadPreview(publish, interval=0.05)
        self.addCleanup(preview.close)
        preview.watch(True)
        await asyncio.sleep(0)
        preview.show(AT_REST[:-3] + b"\x01\x00\x00")
        preview.watch(True)
        await asyncio.sleep(0)
        self.assertEqual(len(published), 1)
        await asyncio.sleep(0.07)
        self.assertEqual(len(published), 2)
