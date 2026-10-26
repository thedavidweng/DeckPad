"""Owned tasks expose failures and cancellation releases all running work."""

import asyncio
import unittest

from deckpad.tasks import Tasks


class OwnedTasks(unittest.IsolatedAsyncioTestCase):
    async def test_failure_is_logged_and_removed(self):
        tasks = Tasks()

        async def fail():
            raise RuntimeError("advertisement failed")

        with self.assertLogs("deckpad.tasks", level="ERROR") as logs:
            tasks.spawn(fail())
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        self.assertIn("advertisement failed", "\n".join(logs.output))
        self.assertFalse(tasks._tasks)

    async def test_repeated_synchronous_cancel_releases_running_tasks(self):
        tasks = Tasks()
        released = asyncio.Event()

        async def run():
            try:
                await asyncio.Future()
            finally:
                released.set()

        tasks.spawn(run())
        await asyncio.sleep(0)
        tasks.cancel_all()
        tasks.cancel_all()
        await asyncio.wait_for(released.wait(), 1)
        await asyncio.sleep(0)
        self.assertFalse(tasks._tasks)
