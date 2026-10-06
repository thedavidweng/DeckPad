"""Pairing Mode: the time-limited sub-state of Controller Mode in which a new Host can find the Deck and pair.

Status moves closed -> discoverable -> pairing (a Host connected) -> paired or failed. An outcome
(paired/failed) stays visible until Pairing Mode is opened again or Controller Mode stops. While the
status is discoverable or pairing, DeckPad's agent accepts Just Works pairing; at any other time it
refuses (ADR-0005).
"""

import asyncio
import logging

from . import errors

log = logging.getLogger("deckpad.pairing")

CLOSED = "closed"
DISCOVERABLE = "discoverable"
PAIRING = "pairing"
PAIRED = "paired"
FAILED = "failed"

TIMEOUT = 180.0


class PairingMode:
    def __init__(self, on_change, on_paired=None):
        self._on_change = on_change
        self._on_paired = on_paired
        self._peripheral = None
        self._status = CLOSED
        self._host = None
        self._candidate = None
        self._error = None
        self._deadline = None
        self._timer = None
        self._tasks = set()

    def snapshot(self):
        seconds_left = None
        if self._deadline is not None:
            seconds_left = max(0, round(self._deadline - asyncio.get_running_loop().time()))
        return {
            "status": self._status,
            "name": self._peripheral.local_name if self._peripheral else None,
            "seconds_left": seconds_left,
            "host": {"address": self._host["address"], "name": self._host["name"]} if self._host else None,
            "error": self._error.to_dict() if self._error else None,
        }

    @property
    def error(self):
        return self._error

    @property
    def accepting(self):
        return self._status in (DISCOVERABLE, PAIRING)

    def attach(self, peripheral):
        """Controller Mode is on: Pairing Mode can now be opened on this Peripheral."""
        self._peripheral = peripheral

    def detach(self):
        """Controller Mode is stopping: forget everything without waiting (the Peripheral tears down
        its own advertisement)."""
        self._cancel_timer()
        for task in self._tasks:
            task.cancel()
        self._peripheral = None
        self._reset(CLOSED)

    async def open(self):
        if self._peripheral is None or self.accepting:
            return
        self._reset(DISCOVERABLE)
        try:
            await self._peripheral.advertise()
        except Exception as e:
            log.warning("Could not start advertising: %r", e)
            self._reset(FAILED, error=errors.advertising_failed(repr(e)))
            await self._publish()
            return
        timeout = TIMEOUT
        loop = asyncio.get_running_loop()
        self._deadline = loop.time() + timeout
        self._timer = loop.call_later(timeout, self._expired)
        log.info("Pairing Mode open for %ds", timeout)
        await self._publish()

    async def close(self):
        if self._status == CLOSED:
            return
        self._reset(CLOSED)
        await self._withdraw()
        await self._publish()

    # Called synchronously by the Peripheral from the agent and the Device1 watch.

    def pairing_requested(self, device):
        if not self.accepting:
            log.info("Refused pairing from %s: Pairing Mode is not open", device.get("Address"))
            return False
        if self._status == DISCOVERABLE:
            self._host_connected(device)
        return True

    def device_changed(self, path, before, after):
        if self._host is not None and self._host["path"] == path and _host(after) != self._host:
            # bluetoothd learns a new Host's name only after the link is up.
            self._host = _host(after)
            self._spawn(self._publish())
        if not self.accepting:
            return
        if self._status == DISCOVERABLE and after.get("Connected") and not before.get("Connected"):
            if after.get("Paired"):
                # A Paired Host reconnecting is not a new pairing.
                return
            self._host_connected(after)
        if self._candidate is not None and path != self._candidate:
            return
        if after.get("Paired") and not before.get("Paired"):
            self._host = _host(after)
            log.info("Paired with %s", self._host["address"])
            if self._on_paired is not None:
                self._on_paired(self._host["address"], self._host["name"])
            self._finish(PAIRED)
        elif self._status == PAIRING and before.get("Connected") and not after.get("Connected"):
            log.info("%s disconnected before pairing finished", after.get("Address"))
            self._finish(FAILED, errors.pairing_failed(self._host["name"]))

    def _host_connected(self, device):
        self._candidate = device["path"]
        self._host = _host(device)
        self._status = PAIRING
        # Advertise only while no Host is connected: a connectable advertisement during a connection
        # can make the controller drop the link.
        self._spawn(self._withdraw())
        self._spawn(self._publish())

    def _expired(self):
        self._timer = None
        log.info("Pairing Mode timed out")
        self._finish(FAILED, errors.pairing_timed_out())

    def _finish(self, status, error=None):
        host = self._host
        self._reset(status, error=error)
        self._host = host
        self._spawn(self._withdraw())
        self._spawn(self._publish())

    def _reset(self, status, error=None):
        self._cancel_timer()
        self._status = status
        self._host = None
        self._candidate = None
        self._error = error
        self._deadline = None

    def _cancel_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    async def _withdraw(self):
        if self._peripheral is not None:
            await self._peripheral.stop_advertising()

    async def _publish(self):
        await self._on_change()

    def _spawn(self, coro):
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


def _host(device):
    address = device.get("Address")
    name = device.get("Alias") or device.get("Name")
    if address and name == address.replace(":", "-"):
        # bluetoothd's placeholder Alias for a device whose name it has not learned.
        name = None
    return {"path": device["path"], "address": address, "name": name}
