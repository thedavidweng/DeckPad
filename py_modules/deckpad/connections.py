"""Connection management for Paired Hosts while Controller Mode is on: which one is connected, letting a
returning Host reconnect, Disconnect, and Forget.

`connection` moves between idle (nothing to wait for), waiting (no Paired Host connected; the Deck sends
a connectable but non-discoverable advertisement so a Paired Host can reconnect by itself), connected,
and paused. Disconnect pauses reconnecting until the user allows it again or the next Controller Mode
session: otherwise a Host that auto-connects would come straight back.
BlueZ offers no directed advertising, so any Paired Host in range may be the one that reconnects.
Advertising stops while a Host is connected, because a connectable advertisement during a connection
can make the controller drop the link.

Only Paired Hosts (the `PairedHosts` record) are ever listed, disconnected or removed; the Deck's other
Bluetooth devices are left alone.
"""

import asyncio
import logging

from dbus_fast import BusType
from dbus_fast.aio import MessageBus

from . import bluez, errors
from .hosts import display_name

log = logging.getLogger("deckpad.connections")

CONNECTED = "connected"
WAITING = "waiting"
PAUSED = "paused"
IDLE = "idle"

# bluetoothd also unregisters every device object (keeping the bonds) when it exits or loses the
# adapter, so a removal is only believed once Bluetooth still reports it a moment later.
REMOVAL_CHECK_DELAY = 0.5
REMOVAL_CHECK_TIMEOUT = 3.0


class Connections:
    """`pairing` is the Pairing Mode, which owns the advertisement while it accepts new Hosts."""

    def __init__(self, paired_hosts, pairing, on_change):
        self._paired_hosts = paired_hosts
        self._pairing = pairing
        self._on_change = on_change
        self._peripheral = None
        self._paused = False
        self._error = None
        self._tasks = set()

    @property
    def error(self):
        """Why Paired Hosts cannot reconnect right now, or None."""
        return self._error

    def snapshot(self):
        devices = self._devices_by_address()
        hosts = []
        for host in self._paired_hosts.all():
            device = devices.get(host["address"], {})
            hosts.append(
                {
                    "address": host["address"],
                    "name": host["name"],
                    "connected": bool(device.get("Connected")),
                }
            )
        hosts.sort(key=lambda h: (not h["connected"], (h["name"] or "").lower(), h["address"]))
        if any(h["connected"] for h in hosts):
            status = CONNECTED
        elif hosts and self._peripheral is not None and self._peripheral.advertising:
            status = WAITING
        elif hosts and self._peripheral is not None and self._paused:
            status = PAUSED
        else:
            status = IDLE
        return {"hosts": hosts, "connection": status}

    async def reconcile(self):
        """Advertise for Paired Hosts exactly while one could reconnect and Pairing Mode is not advertising."""
        peripheral = self._peripheral
        if peripheral is None or self._pairing.accepting:
            return
        try:
            if self._paired_hosts.all() and not self._paused and not self._connected_hosts():
                await peripheral.advertise(discoverable=False)
            else:
                await peripheral.stop_advertising()
        except Exception as e:
            log.warning("Could not update the reconnect advertisement: %r", e)
            if self._peripheral is peripheral:
                self._error = errors.reconnect_unavailable(repr(e))
        else:
            self._error = None

    async def disconnect(self, address):
        """Drop a Connected Host's link, keeping its pairing, and pause reconnecting."""
        device = self._devices_by_address().get(address)
        if self._peripheral is None or address not in self._paired_hosts or not device or not device.get("Connected"):
            return
        self._paused = True
        log.info("Disconnecting %s", address)
        await self._peripheral.disconnect_device(device["path"])
        await self.reconcile()

    async def forget(self, address):
        """Remove a Paired Host's pairing on the Deck (disconnecting it if needed) and drop its record."""
        if self._peripheral is None or address not in self._paired_hosts:
            return
        device = self._devices_by_address().get(address)
        log.info("Forgetting %s", address)
        if device is not None:
            await self._peripheral.remove_device(device["path"])
        self._paired_hosts.remove(address)
        await self.reconcile()

    async def forget_offline(self, address):
        """Forget while Controller Mode is off, over a connection that lasts only for this call."""
        if address not in self._paired_hosts:
            return
        log.info("Forgetting %s", address)
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        try:
            adapter_path, _adapter = await bluez.find_adapter(bus)
            for path in await _device_paths(bus, address):
                await bluez.remove_device(bus, adapter_path, path)
        finally:
            bus.disconnect()
        self._paired_hosts.remove(address)

    async def drop_stale_links(self):
        """While Controller Mode is off, disconnect Paired Hosts that are still connected.

        That only happens when a previous backend was killed (Decky SIGKILLs plugins that are slow to
        stop) before it could disconnect them. The Host then keeps a link to a Deck that no longer
        serves its controller, and does not rebuild the controller until that link drops.
        """
        if not self._paired_hosts.all():
            return
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        try:
            for path, interfaces in (await bluez.managed_objects(bus)).items():
                device = bluez.device_properties(interfaces.get(bluez.DEVICE, {}))
                if device.get("Connected") and device.get("Address") in self._paired_hosts:
                    log.info("Disconnecting %s, left connected by a previous run", device["Address"])
                    await bluez.disconnect_device(bus, path)
        finally:
            bus.disconnect()

    def device_removed(self, path, device):
        if device.get("Address") in self._paired_hosts:
            self._spawn(self._confirm_removed(device["Address"]))

    async def _confirm_removed(self, address):
        """Forget a Paired Host whose pairing was removed elsewhere (Steam's Bluetooth settings)."""
        await asyncio.sleep(REMOVAL_CHECK_DELAY)
        if self._peripheral is None:
            # The session ended; the next one checks the record against what bluetoothd reports.
            return
        try:
            gone = await asyncio.wait_for(_unpaired(address), REMOVAL_CHECK_TIMEOUT)
        except Exception as e:
            log.info("Keeping %s: could not check whether it is still paired: %r", address, e)
            return
        if gone and address in self._paired_hosts:
            log.info("%s was unpaired outside DeckPad; forgetting it", address)
            self._paired_hosts.remove(address)
            await self._update()

    async def allow_reconnect(self):
        if self._peripheral is None:
            return
        self._paused = False
        await self.reconcile()

    def attach(self, peripheral):
        self._peripheral = peripheral
        self._paused = False
        self._error = None
        known = {d.get("Address") for d in peripheral.devices()}
        for host in self._paired_hosts.all():
            if host["address"] not in known:
                log.info("%s was unpaired outside DeckPad; forgetting it", host["address"])
                self._paired_hosts.remove(host["address"])
        for device in peripheral.devices():
            self._refresh_name(device)

    def detach(self):
        """The session is ending: drop its background work without waiting, so it also serves unload."""
        for task in list(self._tasks):
            task.cancel()
        self._peripheral = None
        self._error = None

    def device_changed(self, path, before, after):
        if after.get("Address") not in self._paired_hosts:
            return
        renamed = self._refresh_name(after)
        if before.get("Connected") != after.get("Connected"):
            self._spawn(self._update())
        elif renamed:
            self._spawn(self._on_change())

    async def _update(self):
        await self.reconcile()
        await self._on_change()

    def _connected_hosts(self):
        return [d for d in self._devices_by_address().values() if d.get("Connected") and d.get("Address") in self._paired_hosts]

    def _refresh_name(self, device):
        """Paired Hosts are often recorded before bluetoothd learns their name; keep the record current."""
        return self._paired_hosts.rename(device.get("Address"), display_name(device))

    def _devices_by_address(self):
        if self._peripheral is None:
            return {}
        return {d.get("Address"): d for d in self._peripheral.devices()}

    def _spawn(self, coro):
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


async def _devices(bus, address):
    """(path, properties) of bluetoothd's device objects with this address."""
    found = []
    for path, interfaces in (await bluez.managed_objects(bus)).items():
        if bluez.DEVICE in interfaces:
            props = bluez.device_properties(interfaces[bluez.DEVICE])
            if props.get("Address") == address:
                found.append((path, props))
    return found


async def _device_paths(bus, address):
    return [path for path, _props in await _devices(bus, address)]


async def _unpaired(address):
    """Whether bluetoothd is running with its adapter and no longer holds a pairing with the device.

    Steam scans all the time, so a removed device can already be back as an unpaired object.
    """
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        await bluez.find_adapter(bus)
        return not any(props.get("Paired") for _path, props in await _devices(bus, address))
    finally:
        bus.disconnect()
