"""Everything DeckPad registers with BlueZ for one controller mode session.

Each session owns its own system-bus connection. BlueZ binds every registration to the connection
that made it, so closing the connection is the backstop that releases anything a failed or
interrupted teardown left behind.
"""

import asyncio
import logging
import os

from dbus_fast import BusType, MessageType
from dbus_fast.aio import MessageBus

from . import bluez, device_id, errors, gatt, identity
from .advertisement import Advertisement
from .agent import CAPABILITY, PairingAgent

log = logging.getLogger("deckpad.peripheral")

APP_PATH = "/io/github/thedavidweng/deckpad/app"
AGENT_PATH = "/io/github/thedavidweng/deckpad/agent"
ADVERTISEMENT_PATH = "/io/github/thedavidweng/deckpad/advertisement"

REPORT_REFERENCE = gatt.uuid16("2908")
_REPORT_TYPE_INPUT = 0x01
_REPORT_TYPE_OUTPUT = 0x02

_DEVICE_KEYS = ("Address", "Alias", "Name", "Connected", "Paired")

# Fixed ATT handles for DeckPad's services. Without them bluetoothd puts each registration above the
# highest handle it has ever used, so every controller mode session moves the services. Paired hosts
# keep their GATT cache and trust the Database Hash, which bluetoothd 5.83 stops updating once its
# handles pass 1023 (one writev with an iovec per handle), so they would keep using handles that no
# longer exist. The handles stay below 1024 and are spaced so the HID service can grow.
HID_HANDLE = 0x0200
BATTERY_HANDLE = 0x0230
DEVICE_INFORMATION_HANDLE = 0x0240


def build_application(on_host=None):
    """HID-over-GATT gamepad, plus Battery and Device Information services."""
    app = gatt.Application(APP_PATH, on_host)

    hid = app.add_service(gatt.uuid16("1812"), HID_HANDLE)
    # bcdHID 1.11, country 0, flags: NormallyConnectable.
    hid.add_characteristic(gatt.uuid16("2a4a"), ["encrypt-read"], bytes([0x11, 0x01, 0x00, 0x02]))
    hid.add_characteristic(gatt.uuid16("2a4b"), ["encrypt-read"], identity.REPORT_MAP)
    # Hosts write suspend/exit-suspend here; there is nothing to do about it.
    hid.add_characteristic(gatt.uuid16("2a4c"), ["write-without-response"], b"\x00")
    hid.add_characteristic(gatt.uuid16("2a4e"), ["read", "write-without-response"], b"\x01")
    # `notify` rather than `encrypt-notify`: the encrypted reads already make the host bond first.
    gamepad = hid.add_characteristic(
        gatt.uuid16("2a4d"), ["encrypt-read", "notify"], identity.NEUTRAL_GAMEPAD_REPORT
    )
    gamepad.add_descriptor(REPORT_REFERENCE, ["read"], bytes([identity.INPUT_REPORT_ID, _REPORT_TYPE_INPUT]))
    app.gamepad_input = gamepad
    rumble = hid.add_characteristic(
        gatt.uuid16("2a4d"),
        ["encrypt-read", "encrypt-write", "write-without-response"],
        bytes(identity.OUTPUT_REPORT_SIZE),
    )
    rumble.add_descriptor(REPORT_REFERENCE, ["read"], bytes([identity.OUTPUT_REPORT_ID, _REPORT_TYPE_OUTPUT]))

    battery = app.add_service(gatt.uuid16("180f"), BATTERY_HANDLE)
    battery.add_characteristic(gatt.uuid16("2a19"), ["read", "notify"], bytes([100]))

    dis = app.add_service(gatt.uuid16("180a"), DEVICE_INFORMATION_HANDLE)
    dis.add_characteristic(gatt.uuid16("2a50"), ["read"], identity.PNP_ID)
    return app


async def restore_leftover_device_id():
    """Undo a DeviceID override that a killed DeckPad process left in bluetoothd.

    Decky SIGKILLs plugins that are slow to stop (for instance during a full loader shutdown).
    """
    if os.geteuid() != 0:
        return
    try:
        async with bluez.temporary_connection() as bus:
            _path, adapter = await bluez.find_adapter(bus)
            pid = await bluez.service_pid(bus)
            if device_id.restore_leftover(pid, adapter.get("Modalias"), identity.DEVICE_ID):
                log.info("Restored bluetoothd's DeviceID left over from a previous run")
    except Exception as e:
        log.info("Could not check bluetoothd's DeviceID: %r", e)


class _NoListener:
    def pairing_requested(self, device):
        return False

    def service_requested(self, device):
        return False

    def device_changed(self, path, before, after):
        pass

    def device_removed(self, path, device):
        pass


class Peripheral:
    """`listener` decides pairing and service authorization requests, and is told about Device1 changes."""

    def __init__(self, listener=None, paired_hosts=()):
        self._listener = listener or _NoListener()
        self._paired_hosts = paired_hosts
        self._bus = None
        self._adapter_path = None
        self.local_name = None
        # Remote devices as bluetoothd reports them, keyed by object path.
        self._devices = {}
        # Devices that paired with DeckPad or used its GATT service in this session.
        self._hosts = set()
        self._advertising = False
        self._advertisement = None
        self._advertising_lock = asyncio.Lock()
        self._device_id_override = None
        self._gamepad_input = None
        # Teardown steps, run newest first.
        self._undo = []

    async def start(self):
        try:
            await self._start()
        except BaseException:
            await self.stop()
            raise

    async def _start(self):
        try:
            self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        except Exception as e:
            raise errors.bluetooth_unavailable(repr(e)) from e

        self._adapter_path, adapter = await bluez.find_adapter(self._bus)
        if not adapter.get("Powered"):
            raise errors.bluetooth_off()
        # Hosts show the advertised name while scanning and the adapter's alias (the GAP name) once
        # connected, so advertise the alias to keep the two the same.
        self.local_name = adapter.get("Alias") or adapter.get("Name") or "Steam Deck"

        bus = self._bus
        try:
            bus.add_message_handler(self._on_message)
            await bluez.watch_devices(bus)
            self._load_devices(await bluez.managed_objects(bus))

            agent = PairingAgent(self._allow_pairing, self._allow_service)
            bus.export(AGENT_PATH, agent)
            await bluez.register_agent(bus, AGENT_PATH, CAPABILITY)
            self._undo.append(("unregister agent", lambda: bluez.unregister_agent(bus, AGENT_PATH)))
            await bluez.request_default_agent(bus, AGENT_PATH)

            app = build_application(self._hosts.add)
            app.export(bus)
            self._gamepad_input = app.gamepad_input
            adapter_path = self._adapter_path
            try:
                await bluez.register_application(bus, adapter_path, APP_PATH)
            except bluez.BluezError as e:
                if e.service_unavailable:
                    raise
                # Another BlueZ client already holds those handles.
                log.warning("Could not register at DeckPad's fixed GATT handles (%s); letting BlueZ pick them", e)
                app.let_bluez_pick_handles()
                await bluez.register_application(bus, adapter_path, APP_PATH)
            self._undo.append(
                ("unregister application", lambda: bluez.unregister_application(bus, adapter_path, APP_PATH))
            )
            self._advertisement = Advertisement(self.local_name)
            bus.export(ADVERTISEMENT_PATH, self._advertisement)
            await self._override_device_id(adapter.get("Modalias"))
        except bluez.BluezError as e:
            if e.service_unavailable:
                raise errors.bluetooth_unavailable(str(e)) from e
            raise errors.start_failed(str(e)) from e

    async def _override_device_id(self, modalias):
        if os.geteuid() != 0:
            log.info("Not running as root; Hosts may read BlueZ's DeviceID instead of the Controller Identity")
            return
        pid = await bluez.service_pid(self._bus)
        self._device_id_override = device_id.override(pid, modalias, identity.DEVICE_ID)

    def _restore_device_id(self):
        if self._device_id_override is not None:
            self._device_id_override.restore()
            self._device_id_override = None

    @property
    def adapter_index(self):
        """None before start."""
        return bluez.adapter_index(self._adapter_path)

    async def advertise(self, discoverable=True):
        """Discoverable for pairing mode, or only connectable for paired hosts.

        Switching between the two re-registers the advertisement. Calls are serialised, so the last
        one wins even when callers race.
        """
        async with self._advertising_lock:
            if self._bus is None:
                return
            if self._advertising and self._advertisement.discoverable == discoverable:
                return
            await self._unregister_advertisement()
            self._advertisement.discoverable = discoverable
            await bluez.register_advertisement(self._bus, self._adapter_path, ADVERTISEMENT_PATH)
            self._advertising = True

    async def stop_advertising(self):
        async with self._advertising_lock:
            await self._unregister_advertisement()

    @property
    def advertising(self):
        """None, "discoverable", or "connectable"."""
        if not self._advertising:
            return None
        return "discoverable" if self._advertisement.discoverable else "connectable"

    async def _unregister_advertisement(self):
        if not self._advertising or self._bus is None:
            return
        self._advertising = False
        try:
            await bluez.unregister_advertisement(self._bus, self._adapter_path, ADVERTISEMENT_PATH)
        except bluez.BluezError as e:
            log.warning("Could not stop advertising: %s", e)

    def send_gamepad_report(self, report):
        """Returns False if no host is listening. Hosts that poll with ReadValue get the latest value
        either way."""
        gamepad = self._gamepad_input
        if gamepad is None or self._bus is None:
            return False
        gamepad.value = report
        if not gamepad.notifying or not self._connected_hosts():
            return False
        gamepad.emit_properties_changed({"Value": report})
        return True

    async def disconnect_device(self, path):
        if self._bus is not None:
            await bluez.disconnect_device(self._bus, path)

    async def remove_device(self, path):
        if self._bus is not None:
            await bluez.remove_device(self._bus, self._adapter_path, path)

    def _connected_hosts(self):
        return sorted(
            path
            for path, device in self._devices.items()
            if device.get("Connected") and (path in self._hosts or device.get("Address") in self._paired_hosts)
        )

    async def stop(self):
        """Safe to call repeatedly.

        Connected hosts are disconnected first: if the application just disappears, the host keeps a
        stale link and does not rebuild its controller until that link drops.
        """
        if self._bus is not None:
            for path in self._connected_hosts():
                try:
                    await bluez.disconnect_device(self._bus, path)
                except bluez.BluezError as e:
                    log.warning("Could not disconnect %s: %s", path, e)
            await self.stop_advertising()
        self._restore_device_id()
        while self._undo:
            label, step = self._undo.pop()
            try:
                await step()
            except Exception as e:
                log.warning("Teardown step %r failed: %r", label, e)
        self.close()

    def close(self):
        """Drop the bus connection immediately; BlueZ then releases anything still registered.

        Disconnect requests go out without waiting for replies, so this works when the event loop can
        no longer run (plugin unload).
        """
        self._undo.clear()
        if self._bus is not None:
            for path in self._connected_hosts():
                try:
                    bluez.send_disconnect_device(self._bus, path)
                except Exception as e:
                    log.warning("Could not disconnect %s: %r", path, e)
            self._bus.disconnect()
            self._bus = None
        self._advertising = False
        self._restore_device_id()

    def _allow_pairing(self, path):
        device = self._device(path)
        allowed = self._listener.pairing_requested(device)
        if allowed:
            self._hosts.add(path)
        return allowed

    def _allow_service(self, path):
        return self._listener.service_requested(self._device(path))

    def _device(self, path):
        return dict(self._devices.get(path, {}), path=path)

    def devices(self):
        return [self._device(path) for path in sorted(self._devices)]

    def _load_devices(self, objects):
        for path, interfaces in objects.items():
            if bluez.DEVICE in interfaces:
                self._devices[path] = _pick(bluez.device_properties(interfaces[bluez.DEVICE]))

    def _on_message(self, msg):
        if msg.message_type != MessageType.SIGNAL:
            return False
        if msg.member == "PropertiesChanged" and msg.body and msg.body[0] == bluez.DEVICE:
            self._update_device(msg.path, bluez.device_properties(msg.body[1]))
        elif msg.member == "InterfacesAdded" and bluez.DEVICE in msg.body[1]:
            self._update_device(msg.body[0], bluez.device_properties(msg.body[1][bluez.DEVICE]))
        elif msg.member == "InterfacesRemoved" and bluez.DEVICE in msg.body[1]:
            device = self._device(msg.body[0])
            self._devices.pop(msg.body[0], None)
            try:
                self._listener.device_removed(msg.body[0], device)
            except Exception:
                log.exception("Device removal handler failed for %s", msg.body[0])
        return False

    def _update_device(self, path, changes):
        before = self._device(path)
        self._devices[path] = dict(self._devices.get(path, {}), **_pick(changes))
        after = self._device(path)
        try:
            self._listener.device_changed(path, before, after)
        except Exception:
            log.exception("Device change handler failed for %s", path)


def _pick(props):
    return {k: props[k] for k in _DEVICE_KEYS if k in props}
