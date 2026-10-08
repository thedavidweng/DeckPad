"""Background coroutines that one object starts and cancels together."""

import asyncio


class Tasks:
    def __init__(self):
        self._tasks = set()

    def spawn(self, coro):
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def cancel_all(self):
        """Synchronous, so it can run during plugin unload."""
        for task in list(self._tasks):
            task.cancel()
