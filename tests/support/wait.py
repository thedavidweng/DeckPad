"""Wait for asynchronous input and BlueZ events in behavior tests."""

import asyncio


async def when(plugin, predicate, timeout=2.0):
    """The backend state once `predicate` holds for it, or the last state seen at the timeout."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        state = await plugin.get_state()
        if predicate(state) or loop.time() > deadline:
            return state
        await asyncio.sleep(0.01)



async def settled(plugin, status, timeout=2.0):
    """The backend state once pairing mode reaches `status` (Bluetooth events arrive asynchronously)."""
    return await when(plugin, lambda state: state["pairing"]["status"] == status, timeout)


async def eventually(predicate, timeout=2.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate() and loop.time() < deadline:
        await asyncio.sleep(0.01)
    return predicate()

