"""Background coroutines that one object starts and cancels together."""

import asyncio
import logging

log = logging.getLogger("deckpad.tasks")


class Tasks:
    def __init__(self):
        self._tasks = set()

    def spawn(self, coro):
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._finished)
        return task

    def _finished(self, task):
        self._tasks.discard(task)
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                log.error("Background task failed: %r", error, exc_info=error)

    def cancel_all(self):
        """Synchronous, so it can run during plugin unload."""
        for task in list(self._tasks):
            task.cancel()
