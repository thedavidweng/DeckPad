"""Paired hosts while controller mode is on: reconnecting, Disconnect, and Forget.

While no paired host is connected, the Deck sends a connectable but non-discoverable advertisement so
one can reconnect by itself. BlueZ offers no directed advertising, so any paired host in range may be
the one that does. Disconnect pauses this until the user allows it again or controller mode restarts;
otherwise a host that auto-connects would come straight back.

Advertising stops while a host is connected, because a connectable advertisement during a connection
can make the controller drop the link. Only one host is connected at a time: one that connects or pairs
while another is connected (only possible through pairing mode's advertisement) takes over.

Only devices in `PairedHosts` are listed, disconnected or removed; the Deck's other Bluetooth devices
are left alone.
"""

import asyncio
import logging

from . import bluez, errors
from .hosts import display_name
from .tasks import Tasks

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
    """`pairing` owns the advertisement while pairing mode is open."""

    def __init__(self, paired_hosts, pairing, on_change):
        self._paired_hosts = paired_hosts
        self._pairing = pairing
        self._on_change = on_change
        self._peripheral = None
        self._paused = False
        self._error = None
        self._tasks = Tasks()

    @property
    def error(self):
        """Why paired hosts cannot reconnect right now, or None."""
        return self._error

    def snapshot(self):
        return {"hosts": self._hosts(), "connection": self.status}

    @property
    def status(self):
        hosts = self._hosts()
        if any(h["connected"] for h in hosts):
            return CONNECTED
        if hosts and self._peripheral is not None and self._peripheral.advertising:
            return WAITING
        if hosts and self._peripheral is not None and self._paused:
            return PAUSED
        return IDLE

    def _hosts(self):
        """Connected host first."""
        devices = self._devices_by_address()
        hosts = [
            dict(host.to_dict(), connected=bool(devices.get(host.address, {}).get("Connected")))
            for host in self._paired_hosts.all()
        ]
        hosts.sort(key=lambda h: (not h["connected"], (h["name"] or "").lower(), h["address"]))
        return hosts

    async def reconcile(self):
        """Advertise for paired hosts exactly while one could reconnect and pairing mode is closed."""
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
        """Drop the link, keep the pairing, and pause reconnecting."""
        device = self._devices_by_address().get(address)
        if self._peripheral is None or address not in self._paired_hosts or not device or not device.get("Connected"):
            return
        self._paused = True
        log.info("Disconnecting %s", address)
        await self._peripheral.disconnect_device(device["path"])
        await self.reconcile()

    async def forget(self, address):
        if self._peripheral is None or address not in self._paired_hosts:
            return
        device = self._devices_by_address().get(address)
        log.info("Forgetting %s", address)
        if device is not None:
            await self._peripheral.remove_device(device["path"])
        self._paired_hosts.remove(address)
        await self.reconcile()

    async def forget_offline(self, address):
        """Forget while controller mode is off, over a bus connection that lasts only for this call."""
        if address not in self._paired_hosts:
            return
        log.info("Forgetting %s", address)
        async with bluez.temporary_connection() as bus:
            adapter_path, _adapter = await bluez.find_adapter(bus)
            await _remove_pairing(bus, adapter_path, address)
        self._paired_hosts.remove(address)

    async def forget_all_offline(self):
        """For uninstall. A host whose pairing could not be removed stays in the record."""
        if not self._paired_hosts.all():
            return
        async with bluez.temporary_connection() as bus:
            adapter_path, _adapter = await bluez.find_adapter(bus)
            for host in self._paired_hosts.all():
                log.info("Forgetting %s", host.address)
                try:
                    await _remove_pairing(bus, adapter_path, host.address)
                except bluez.BluezError as e:
                    log.warning("Could not remove the pairing with %s: %s", host.address, e)
                else:
                    self._paired_hosts.remove(host.address)

    async def drop_stale_links(self):
        """Disconnect paired hosts left connected by a killed previous backend.

        Such a host keeps a link to a Deck that no longer serves its controller, and does not rebuild
        the controller until that link drops.
        """
        if not self._paired_hosts.all():
            return
        async with bluez.temporary_connection() as bus:
            for path, interfaces in (await bluez.managed_objects(bus)).items():
                device = bluez.device_properties(interfaces.get(bluez.DEVICE, {}))
                if device.get("Connected") and device.get("Address") in self._paired_hosts:
                    log.info("Disconnecting %s, left connected by a previous run", device["Address"])
                    await bluez.disconnect_device(bus, path)

    def device_removed(self, path, device):
        if device.get("Address") in self._paired_hosts:
            self._tasks.spawn(self._confirm_removed(device["Address"]))

    async def _confirm_removed(self, address):
        """Forget a host whose pairing was removed elsewhere, such as Steam's Bluetooth settings."""
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
            if host.address not in known:
                log.info("%s was unpaired outside DeckPad; forgetting it", host.address)
                self._paired_hosts.remove(host.address)
        for device in peripheral.devices():
            self._refresh_name(device)

    def detach(self):
        """Does not wait, so it can run during plugin unload."""
        self._tasks.cancel_all()
        self._peripheral = None
        self._error = None

    def device_changed(self, path, before, after):
        if after.get("Address") not in self._paired_hosts:
            return
        renamed = self._refresh_name(after)
        if _connected_and_paired(after) and not _connected_and_paired(before):
            self._tasks.spawn(self._take_over(after))
        elif before.get("Connected") != after.get("Connected"):
            self._tasks.spawn(self._update())
        elif renamed:
            self._tasks.spawn(self._on_change())

    async def _take_over(self, device):
        """The host that connected (or paired) last gets the controls; the others are disconnected."""
        peripheral = self._peripheral
        others = [d for d in self._connected_hosts() if d["path"] != device["path"]]
        for other in others:
            log.info("%s connected; disconnecting %s", device.get("Address"), other.get("Address"))
            try:
                await peripheral.disconnect_device(other["path"])
            except Exception as e:
                log.warning("Could not disconnect %s: %r", other.get("Address"), e)
        await self._update()

    async def _update(self):
        await self.reconcile()
        await self._on_change()

    def _connected_hosts(self):
        return [d for d in self._devices_by_address().values() if d.get("Connected") and d.get("Address") in self._paired_hosts]

    def _refresh_name(self, device):
        """Hosts are often recorded before bluetoothd learns their name."""
        return self._paired_hosts.rename(device.get("Address"), display_name(device))

    def _devices_by_address(self):
        if self._peripheral is None:
            return {}
        return {d.get("Address"): d for d in self._peripheral.devices()}


def _connected_and_paired(device):
    return bool(device.get("Connected") and device.get("Paired"))


async def _devices(bus, address):
    found = []
    for path, interfaces in (await bluez.managed_objects(bus)).items():
        if bluez.DEVICE in interfaces:
            props = bluez.device_properties(interfaces[bluez.DEVICE])
            if props.get("Address") == address:
                found.append((path, props))
    return found


async def _remove_pairing(bus, adapter_path, address):
    for path, _props in await _devices(bus, address):
        await bluez.remove_device(bus, adapter_path, path)


async def _unpaired(address):
    """Whether bluetoothd is up and no longer holds a pairing with the device.

    Steam scans all the time, so a removed device can already be back as an unpaired object.
    """
    async with bluez.temporary_connection() as bus:
        await bluez.find_adapter(bus)
        return not any(props.get("Paired") for _path, props in await _devices(bus, address))
