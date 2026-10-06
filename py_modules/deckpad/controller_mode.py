"""Controller Mode: the user-facing on/off state and the lifecycle of the Peripheral session behind it.

Status moves off -> starting -> on -> stopping -> off. A failed start returns to off with an error the
QAM panel can show; the error clears on the next attempt. If Bluetooth goes away underneath a running
session (bluetoothd restarts, the adapter is switched off), status moves on -> recovering -> on once it
is back, or -> off with an error if it does not come back in time. Transitions are serialised, so
requests that arrive mid-transition are applied in order against the settled state.
"""

import asyncio
import collections
import logging
import os
import time

from . import connection_interval, errors
from .bluetooth_watch import BluetoothWatch
from .connections import Connections
from .deck_input import DeckInput
from .link_monitor import FALLBACK_REPORT_INTERVAL, LinkMonitor
from .hosts import PairedHosts
from .pairing import PairingMode
from .peripheral import Peripheral

log = logging.getLogger("deckpad.controller_mode")

OFF = "off"
STARTING = "starting"
ON = "on"
STOPPING = "stopping"

RECOVERING = "recovering"

START_TIMEOUT = 10.0
STOP_TIMEOUT = 5.0
# How long Controller Mode waits for Bluetooth to come back after it went away underneath it, and how
# often it checks. A `systemctl restart bluetooth` takes a few seconds.
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
    ):
        self._on_change = on_change
        self._interval_state_path = interval_state_path
        self._paired_hosts = paired_hosts if paired_hosts is not None else PairedHosts()
        self._start_timeout = start_timeout
        self._stop_timeout = stop_timeout
        self._lock = asyncio.Lock()
        self._status = OFF
        self._current_error = None
        # (wall-clock time, error) of recent errors, for diagnostics after the panel has cleared them.
        self._error_history = collections.deque(maxlen=10)
        self._peripheral = None
        self._input = None
        self._link = None
        self._shorter_interval = None
        self._watch = None
        # Gamepad Reports of the current session, by whether a Host received them, for diagnostics.
        self._reports = {True: 0, False: 0}
        self._tasks = set()
        self._closed = False
        self._pairing = PairingMode(on_change=self._pairing_changed, on_paired=self._paired_hosts.add)
        self._connections = Connections(self._paired_hosts, self._pairing, on_change=self._changed)

    @property
    def _error(self):
        return self._current_error

    @_error.setter
    def _error(self, error):
        self._current_error = error
        if error is not None:
            self._error_history.append((time.time(), error))

    def diagnostics(self):
        """Internal state for the Troubleshooting surface; not part of the panel's normal state."""
        errors_seen = list(self._error_history)
        if self._connections.error is not None:
            errors_seen.append((time.time(), self._connections.error))
        if self._pairing.error is not None:
            errors_seen.append((time.time(), self._pairing.error))
        return {
            "status": self._status,
            "pairing": self._pairing.snapshot()["status"],
            "connection": self._connections.snapshot()["connection"],
            "advertising": self._peripheral.advertising if self._peripheral is not None else None,
            "controls_reading": self._input.available if self._input is not None else None,
            "controls_problem": self._input.problem if self._input is not None else None,
            "link_intervals": self._link.intervals() if self._link is not None else [],
            "reports_delivered": self._reports[True],
            "reports_undelivered": self._reports[False],
            "errors": errors_seen,
        }

    def snapshot(self):
        error = self._error or self._connections.error
        return {
            "enabled": self._status == ON,
            "status": self._status,
            "error": error.to_dict() if error else None,
            "pairing": self._pairing.snapshot(),
            "controls": self._controls(),
            **self._connections.snapshot(),
        }

    def _controls(self):
        if self._input is None:
            return None
        if self._input.available:
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

    async def set_pairing_mode(self, enabled):
        """Open or close Pairing Mode. It only exists while Controller Mode is on; otherwise this does nothing."""
        async with self._lock:
            if self._status == ON:
                if enabled:
                    # Before the advertisement goes up, so a Host connecting to pair keeps its interval.
                    self._update_interval(pairing=True)
                    await self._pairing.open()
                else:
                    await self._pairing.close()
        return self.snapshot()

    async def disconnect_host(self, address):
        """Disconnect a Connected Host from the panel; it stays a Paired Host."""
        async with self._lock:
            if self._status == ON:
                await self._run(self._connections.disconnect(address), errors.disconnect_failed, address)
        return self.snapshot()

    async def forget_host(self, address):
        """Remove a Paired Host and its pairing on the Deck. Works whether or not Controller Mode is on."""
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

    async def recover_from_previous_run(self):
        """At backend start: undo what a previous backend that was killed left behind."""
        async with self._lock:
            if self._status != OFF:
                return
            try:
                await asyncio.wait_for(self._connections.drop_stale_links(), self._stop_timeout)
            except Exception as e:
                log.info("Could not check for Hosts left connected by a previous run: %r", e)

    async def _run(self, action, failure, address=None):
        """Run a panel action; if it fails, the panel says what went wrong instead of nothing happening."""
        try:
            await action
        except Exception as e:
            log.warning("Connection action failed: %r", e)
            if address is None:
                self._error = failure(repr(e))
            else:
                self._error = failure(self._host_name(address), repr(e))
        else:
            self._error = None
        await self._changed()

    def _host_name(self, address):
        for host in self._paired_hosts.all():
            if host["address"] == address:
                return host["name"]
        return None

    def shutdown(self):
        """Return the Deck to ordinary SteamOS Bluetooth behaviour immediately, for plugin unload.

        This must not wait on the event loop. Decky Loader 3.2.9 closes the plugin's socket while
        `_unload` runs, and its socket reader then spins without yielding, so awaited D-Bus replies and
        timers never resume and Decky SIGKILLs the plugin after 5 s. Closing the bus connection makes
        BlueZ drop the application, advertisement, and agent (restoring Steam's default agent) without
        a round trip.
        """
        self._closed = True
        for task in list(self._tasks):
            task.cancel()
        self._end_session()
        self._status = OFF
        log.info("Controller Mode off (unload)")

    async def _start(self):
        self._error = None
        await self._set_status(STARTING)
        try:
            opened = await self._open_session()
        except errors.ControllerModeError as e:
            self._error = e
            await self._set_status(OFF)
            return
        if opened:
            log.info("Controller Mode on")
            await self._set_status(ON)

    async def _open_session(self):
        """Start a Peripheral and everything that runs with it. Returns False if unload began meanwhile.

        On failure everything is released again and the ControllerModeError is raised.
        """
        peripheral = Peripheral(listener=_Listeners(self._pairing, self._connections), paired_hosts=self._paired_hosts)
        watch = BluetoothWatch(lambda reason: self._session_lost(watch, reason))
        self._peripheral = peripheral
        self._watch = watch
        try:
            await asyncio.wait_for(peripheral.start(), self._start_timeout)
            # After the Peripheral: a loss during its start already fails the start.
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
            # Host connect, because the kernel only asks for it when the connection comes up.
            self._start_input(peripheral)
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

    def _end_session(self):
        """Synchronous, so it also serves plugin unload."""
        self._pairing.detach()
        self._connections.detach()
        self._stop_input()
        if self._peripheral is not None:
            self._peripheral.close()
            self._peripheral = None
        self._stop_watch()

    def _stop_watch(self):
        if self._watch is not None:
            self._watch.stop()
            self._watch = None

    async def _stop(self):
        self._pairing.detach()
        self._connections.detach()
        self._stop_input()
        self._stop_watch()
        self._error = None
        await self._set_status(STOPPING)
        peripheral, self._peripheral = self._peripheral, None
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
            self._spawn(self._recover(watch, reason))

    async def _recover(self, watch, reason):
        """Bluetooth went away underneath the session: drop it, and start a new one once Bluetooth is back.

        bluetoothd forgets every registration when it restarts and an adapter that powers off drops
        every link, so there is nothing to keep. Controller Mode stays on from the user's point of view
        while it waits; if Bluetooth does not come back in time, it turns off with an error.
        """
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
                    self._error = errors.session_lost(e)
                    await self._set_status(OFF)
                    return

    async def _pairing_changed(self):
        self._update_interval(pairing=self._pairing.accepting)
        # Once Pairing Mode stops accepting, Paired Hosts get their reconnect advertisement back.
        await self._connections.reconcile()
        await self._changed()

    def _start_input(self, peripheral):
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
        self._reports = {True: 0, False: 0}

        def send(report):
            delivered = peripheral.send_gamepad_report(report)
            self._reports[bool(delivered)] += 1
            return delivered

        self._input = DeckInput(send, report_interval, self._controls_changed)
        self._input.start()

    def _controls_changed(self):
        if self._status == ON:
            self._spawn(self._changed())

    def _spawn(self, coro):
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _stop_input(self):
        """Synchronous, so it also serves plugin unload."""
        if self._input is not None:
            self._input.stop()
            self._input = None
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


class _Listeners:
    """Pairing Mode decides pairing requests; both Pairing Mode and Connections follow Device1 changes."""

    def __init__(self, pairing, connections):
        self._pairing = pairing
        self._connections = connections

    def pairing_requested(self, device):
        return self._pairing.pairing_requested(device)

    def device_changed(self, path, before, after):
        self._pairing.device_changed(path, before, after)
        self._connections.device_changed(path, before, after)

    def device_removed(self, path, device):
        self._connections.device_removed(path, device)
