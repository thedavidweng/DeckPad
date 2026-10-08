"""Turns controller mode on and off and runs the Bluetooth session behind it.

If Bluetooth goes away while it is on (bluetoothd restarts, the adapter is switched off), the session
is rebuilt once Bluetooth is back, or controller mode turns off with an error if that takes too long.
"""

import asyncio
import collections
import logging
import os
import threading

from . import connection_interval, errors
from .bluetooth_watch import BluetoothWatch
from .connections import Connections
from .deck_controls import DeckControls
from .gamepad_preview import GamepadPreview
from .link_monitor import FALLBACK_REPORT_INTERVAL, LinkMonitor
from .hosts import PairedHosts
from .pairing import PairingMode
from .peripheral import Peripheral, restore_leftover_device_id
from .settings import Settings
from .tasks import Tasks

log = logging.getLogger("deckpad.controller_mode")

OFF = "off"
STARTING = "starting"
ON = "on"
STOPPING = "stopping"

RECOVERING = "recovering"

START_TIMEOUT = 10.0
STOP_TIMEOUT = 5.0
UNINSTALL_TIMEOUT = 3.0
# How long to wait for Bluetooth to come back, and how often to check. `systemctl restart bluetooth`
# takes a few seconds.
RECOVERY_TIMEOUT = 20.0
RECOVERY_RETRY_DELAY = 1.0

CONTROLS_UNAVAILABLE = (
    "DeckPad cannot read the Deck's controls right now, so the connected device gets no input. DeckPad "
    "keeps trying; if this lasts, restart the Deck."
)


class ControllerMode:
    def __init__(
        self,
        on_change=None,
        start_timeout=START_TIMEOUT,
        stop_timeout=STOP_TIMEOUT,
        paired_hosts=None,
        interval_state_path=None,
        settings=None,
        on_gamepad_report=None,
    ):
        """`on_gamepad_report(described_report)` is a coroutine function. It gets the reports sent to the
        host while the controller screen is open (see `watch_gamepad`)."""
        self._on_change = on_change
        self._interval_state_path = interval_state_path
        self._paired_hosts = paired_hosts if paired_hosts is not None else PairedHosts()
        self._settings = settings if settings is not None else Settings()
        self._start_timeout = start_timeout
        self._stop_timeout = stop_timeout
        self._lock = asyncio.Lock()
        self._status = OFF
        self._error = None
        # Recent errors, for diagnostics after the panel has cleared them.
        self._error_history = collections.deque(maxlen=10)
        self._peripheral = None
        self._deck_controls = None
        self._link = None
        self._shorter_interval = None
        self._watch = None
        # Report counts for the current session, for diagnostics.
        self._reports = _ReportCount()
        self._tasks = Tasks()
        self._closed = False
        self._preview = GamepadPreview(on_gamepad_report or _ignore)
        self._pairing = PairingMode(on_change=self._pairing_changed, on_paired=self._paired_hosts.add)
        self._connections = Connections(self._paired_hosts, self._pairing, on_change=self._changed)

    def _record_error(self, error):
        self._error = error
        self._error_history.append(error)

    def diagnostics(self):
        errors_seen = list(self._error_history)
        for error in (self._connections.error, self._pairing.error):
            if error is not None and error not in errors_seen:
                errors_seen.append(error)
        errors_seen.sort(key=lambda e: e.occurred_at)
        return {
            "status": self._status,
            "pairing": self._pairing.status,
            "connection": self._connections.status,
            "advertising": self._peripheral.advertising if self._peripheral is not None else None,
            "controls_reading": self._deck_controls.available if self._deck_controls is not None else None,
            "controls_problem": self._deck_controls.problem if self._deck_controls is not None else None,
            "link_intervals": self._link.intervals() if self._link is not None else [],
            "reports_delivered": self._reports.delivered,
            "reports_undelivered": self._reports.undelivered,
            "errors": errors_seen,
        }

    def snapshot(self):
        error = self._error or self._connections.error
        return {
            "enabled": self._status == ON,
            "status": self._status,
            "error": error.to_dict() if error else None,
            "pairing": self._pairing.snapshot(),
            "controls": self._controls_state(),
            "quit_combo": self._settings.quit_combo,
            **self._connections.snapshot(),
        }

    def _controls_state(self):
        if self._deck_controls is None:
            return None
        if self._deck_controls.available:
            return {"available": True, "message": None}
        return {"available": False, "message": CONTROLS_UNAVAILABLE}

    async def set_enabled(self, enabled):
        async with self._lock:
            if self._closed:
                return self.snapshot()
            if enabled and self._status == OFF:
                await self._start()
            elif not enabled and self._status == ON:
                await self._stop()
            elif not enabled and self._status == RECOVERING:
                log.info("Controller Mode off (while waiting for Bluetooth)")
                await self._set_status(OFF)
            elif not enabled and self._error:
                self._error = None
                await self._changed()
        return self.snapshot()

    async def set_quit_combo(self, enabled):
        """When off, the quit combo goes to the host like any other press."""
        self._settings.set_quit_combo(enabled)
        await self._changed()
        return self.snapshot()

    def watch_gamepad(self, enabled):
        """Whether reports sent to the host are also passed to `on_gamepad_report`."""
        if not self._closed:
            self._preview.watch(enabled)

    def _quit_combo_pressed(self):
        if self._status == ON:
            log.info("Controller Mode off (Quit Combo)")
            self._tasks.spawn(self.set_enabled(False))

    async def set_pairing_mode(self, enabled):
        """Does nothing unless controller mode is on."""
        async with self._lock:
            if self._status == ON:
                if enabled:
                    # Before the advertisement goes up, so a host connecting to pair keeps its interval.
                    self._update_interval(pairing=True)
                    await self._pairing.open()
                else:
                    await self._pairing.close()
        return self.snapshot()

    async def disconnect_host(self, address):
        """The host stays paired."""
        async with self._lock:
            if self._status == ON:
                await self._run(self._connections.disconnect(address), errors.disconnect_failed, address)
        return self.snapshot()

    async def forget_host(self, address):
        """Remove a host's pairing on the Deck, with controller mode on or off."""
        async with self._lock:
            if self._status == ON:
                await self._run(self._connections.forget(address), errors.forget_failed, address)
            elif self._status == OFF:
                await self._run(self._connections.forget_offline(address), errors.forget_failed, address)
        return self.snapshot()

    async def allow_reconnect(self):
        async with self._lock:
            if self._status == ON:
                await self._run(self._connections.allow_reconnect(), errors.reconnect_unavailable)
        return self.snapshot()

    async def clean_up_after_previous_run(self):
        """Undo what a killed previous backend left behind.

        Decky SIGKILLs plugins that are slow to stop, and then nothing restores bluetoothd's DeviceID or
        the adapter's connection interval, or disconnects the host that was connected.
        """
        async with self._lock:
            if self._status != OFF:
                return
            await restore_leftover_device_id()
            try:
                await asyncio.wait_for(self._connections.drop_stale_links(), self._stop_timeout)
            except Exception as e:
                log.info("Could not check for Hosts left connected by a previous run: %r", e)
            if self._interval_state_path and os.geteuid() == 0:
                if connection_interval.restore_leftover(self._interval_state_path):
                    log.info("Restored the adapter's connection interval left over from a previous run")

    async def _run(self, action, failure, address=None):
        try:
            await action
        except Exception as e:
            log.warning("Connection action failed: %r", e)
            if address is None:
                self._record_error(failure(repr(e)))
            else:
                self._record_error(failure(self._paired_hosts.name(address), repr(e)))
        else:
            self._error = None
        await self._changed()

    def shutdown(self):
        """Return Bluetooth to normal immediately, for plugin unload.

        This must not wait on the event loop. Decky Loader 3.2.9 closes the plugin's socket while
        `_unload` runs, and its socket reader then spins without yielding, so awaited D-Bus replies and
        timers never resume and Decky SIGKILLs the plugin after 5 s. Closing the bus connection makes
        BlueZ drop the application, advertisement, and agent (restoring Steam's default agent) without
        a round trip.
        """
        self._closed = True
        self._tasks.cancel_all()
        self._preview.close()
        self._end_session()
        self._status = OFF
        log.info("Controller Mode off (unload)")

    def uninstall(self):
        """Remove the pairings DeckPad made (and no others), leftovers of a killed run, and DeckPad's files.

        Decky runs this right after `_unload`, with the event loop just as stuck (see `shutdown`), so the
        Bluetooth part runs on its own event loop in a worker thread, joined with a timeout that keeps
        the whole stop under Decky's 5 s.
        """
        self.shutdown()
        worker = threading.Thread(
            target=asyncio.run, args=(self._remove_bluetooth_traces(),), name="deckpad-uninstall", daemon=True
        )
        worker.start()
        worker.join(UNINSTALL_TIMEOUT)
        if worker.is_alive():
            log.warning("Bluetooth did not answer in time; remove leftover Paired Hosts in Steam's settings")
        if self._interval_state_path:
            if os.geteuid() == 0:
                connection_interval.restore_leftover(self._interval_state_path)
            connection_interval.forget_leftover(self._interval_state_path)
        self._paired_hosts.erase()
        self._settings.erase()
        log.info("DeckPad uninstalled")

    async def _remove_bluetooth_traces(self):
        try:
            await asyncio.wait_for(self._connections.forget_all_offline(), UNINSTALL_TIMEOUT)
        except Exception as e:
            log.warning("Could not remove the pairings of Paired Hosts: %r", e)
        await restore_leftover_device_id()

    async def _start(self):
        self._error = None
        await self._set_status(STARTING)
        try:
            opened = await self._open_session()
        except errors.ControllerModeError as e:
            self._record_error(e)
            await self._set_status(OFF)
            return
        if opened:
            log.info("Controller Mode on")
            await self._set_status(ON)

    async def _open_session(self):
        """Returns False if unload began meanwhile. On failure, releases everything and raises."""
        peripheral = Peripheral(
            listener=_Listeners(self._pairing, self._connections, self._paired_hosts), paired_hosts=self._paired_hosts
        )
        watch = BluetoothWatch(lambda reason: self._session_lost(watch, reason))
        self._peripheral = peripheral
        self._watch = watch
        try:
            await asyncio.wait_for(peripheral.start(), self._start_timeout)
            # Started second: losing Bluetooth while the peripheral starts already fails the start.
            await asyncio.wait_for(watch.start(), self._start_timeout)
        except errors.ControllerModeError as e:
            error = e
        except asyncio.TimeoutError:
            error = errors.start_failed("Bluetooth did not respond in time")
        except Exception as e:
            log.exception("Controller Mode failed to start")
            error = errors.start_failed(repr(e))
        else:
            if self._closed:
                watch.stop()
                peripheral.close()
                return False
            # Input first: the connection interval range must be set before any advertisement lets a
            # host connect, because the kernel only asks for it when the connection comes up.
            self._start_deck_controls(peripheral)
            self._pairing.attach(peripheral)
            self._connections.attach(peripheral)
            await self._connections.reconcile()
            return True
        log.warning("Controller Mode could not start: %s (%s)", error.code, error.detail)
        watch.stop()
        peripheral.close()
        self._peripheral = None
        self._watch = None
        raise error

    def _end_session(self, keep_peripheral=False):
        """Synchronous, so it can run during plugin unload. With `keep_peripheral`, the peripheral is
        returned still open so `_stop` can tear it down in order."""
        self._pairing.detach()
        self._connections.detach()
        self._stop_deck_controls()
        self._preview.reset()
        if self._watch is not None:
            self._watch.stop()
            self._watch = None
        peripheral, self._peripheral = self._peripheral, None
        if keep_peripheral:
            return peripheral
        if peripheral is not None:
            peripheral.close()
        return None

    async def _stop(self):
        peripheral = self._end_session(keep_peripheral=True)
        self._error = None
        await self._set_status(STOPPING)
        try:
            await asyncio.wait_for(peripheral.stop(), self._stop_timeout)
        except Exception as e:
            log.warning("Controller Mode teardown did not finish cleanly: %r", e)
        finally:
            peripheral.close()
        log.info("Controller Mode off")
        await self._set_status(OFF)

    def _session_lost(self, watch, reason):
        if not self._closed:
            self._tasks.spawn(self._recover(watch, reason))

    async def _recover(self, watch, reason):
        """bluetoothd forgets every registration when it restarts, and an adapter that powers off drops
        every link, so nothing of the old session is worth keeping."""
        async with self._lock:
            # The lock also waits out a start that is still finishing with this watch.
            if self._closed or self._status != ON or self._watch is not watch:
                return
            log.warning("Bluetooth went away (%s); Controller Mode resumes when it is back", reason)
            self._end_session()
            await self._set_status(RECOVERING)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + RECOVERY_TIMEOUT
        while True:
            await asyncio.sleep(RECOVERY_RETRY_DELAY)
            async with self._lock:
                if self._closed or self._status != RECOVERING:
                    return
                try:
                    if await self._open_session():
                        log.info("Controller Mode resumed: Bluetooth is back")
                        await self._set_status(ON)
                    return
                except errors.ControllerModeError as e:
                    if loop.time() < deadline:
                        continue
                    log.warning("Bluetooth did not come back; Controller Mode is off")
                    self._record_error(errors.session_lost(e))
                    await self._set_status(OFF)
                    return

    async def _pairing_changed(self):
        self._update_interval(pairing=self._pairing.accepting)
        # Once pairing mode closes, paired hosts get their reconnect advertisement back.
        await self._connections.reconcile()
        await self._changed()

    def _start_deck_controls(self, peripheral):
        report_interval = lambda: FALLBACK_REPORT_INTERVAL  # noqa: E731
        index = peripheral.adapter_index
        # Both need root: MGMT configuration commands and HCI event filters are privileged.
        if os.geteuid() == 0 and index is not None:
            if self._interval_state_path:
                self._shorter_interval = connection_interval.ShorterInterval(index, self._interval_state_path)
                self._update_interval(pairing=False)
            self._link = LinkMonitor(index)
            self._link.start()
            report_interval = self._link.report_interval
        self._reports = _ReportCount()

        def send(report):
            delivered = peripheral.send_gamepad_report(report)
            self._reports.count(delivered)
            self._preview.show(report)
            return delivered

        self._deck_controls = DeckControls(
            send,
            report_interval,
            self._controls_changed,
            on_quit_combo=self._quit_combo_pressed,
            quit_combo_enabled=lambda: self._settings.quit_combo,
        )
        self._deck_controls.start()

    def _controls_changed(self):
        if self._status == ON:
            self._tasks.spawn(self._changed())

    def _stop_deck_controls(self):
        if self._deck_controls is not None:
            self._deck_controls.stop()
            self._deck_controls = None
        if self._link is not None:
            self._link.stop()
            self._link = None
        if self._shorter_interval is not None:
            self._shorter_interval.close()
            self._shorter_interval = None

    def _update_interval(self, pairing):
        if self._shorter_interval is not None:
            self._shorter_interval.update(pairing)

    async def _set_status(self, status):
        self._status = status
        await self._changed()

    async def _changed(self):
        # After unload starts, Decky has already closed the frontend socket.
        if self._on_change is None or self._closed:
            return
        try:
            await self._on_change(self.snapshot())
        except Exception as e:
            log.warning("Could not publish Controller Mode state: %r", e)


async def _ignore(_):
    pass


class _Listeners:
    """A device may use the Deck's services while pairing mode is open, or if it is a paired host."""

    def __init__(self, pairing, connections, paired_hosts):
        self._pairing = pairing
        self._connections = connections
        self._paired_hosts = paired_hosts

    def pairing_requested(self, device):
        return self._pairing.pairing_requested(device)

    def service_requested(self, device):
        return self._pairing.accepting or device.get("Address") in self._paired_hosts

    def device_changed(self, path, before, after):
        self._pairing.device_changed(path, before, after)
        self._connections.device_changed(path, before, after)

    def device_removed(self, path, device):
        self._connections.device_removed(path, device)


class _ReportCount:
    def __init__(self):
        self.delivered = 0
        self.undelivered = 0

    def count(self, delivered):
        if delivered:
            self.delivered += 1
        else:
            self.undelivered += 1
