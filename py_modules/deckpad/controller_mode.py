"""Controller Mode: the user-facing on/off state and the lifecycle of the Peripheral session behind it.

Status moves off -> starting -> on -> stopping -> off. A failed start returns to off with an error the
QAM panel can show; the error clears on the next attempt. Transitions are serialised, so requests that
arrive mid-transition are applied in order against the settled state.
"""

import asyncio
import logging

from . import errors
from .peripheral import Peripheral

log = logging.getLogger("deckpad.controller_mode")

OFF = "off"
STARTING = "starting"
ON = "on"
STOPPING = "stopping"

START_TIMEOUT = 10.0
STOP_TIMEOUT = 5.0


class ControllerMode:
    def __init__(self, on_change=None, start_timeout=START_TIMEOUT, stop_timeout=STOP_TIMEOUT):
        self._on_change = on_change
        self._start_timeout = start_timeout
        self._stop_timeout = stop_timeout
        self._lock = asyncio.Lock()
        self._status = OFF
        self._error = None
        self._peripheral = None
        self._closed = False

    def snapshot(self):
        return {
            "enabled": self._status == ON,
            "status": self._status,
            "error": self._error.to_dict() if self._error else None,
        }

    async def set_enabled(self, enabled):
        async with self._lock:
            if self._closed:
                return self.snapshot()
            if enabled and self._status == OFF:
                await self._start()
            elif not enabled and self._status == ON:
                await self._stop()
            elif not enabled and self._error:
                self._error = None
                await self._changed()
        return self.snapshot()

    def shutdown(self):
        """Return the Deck to ordinary SteamOS Bluetooth behaviour immediately, for plugin unload.

        This must not wait on the event loop. Decky Loader 3.2.9 closes the plugin's socket while
        `_unload` runs, and its socket reader then spins without yielding, so awaited D-Bus replies and
        timers never resume and Decky SIGKILLs the plugin after 5 s. Closing the bus connection makes
        BlueZ drop the application, advertisement, and agent (restoring Steam's default agent) without
        a round trip.
        """
        self._closed = True
        if self._peripheral is not None:
            self._peripheral.close()
            self._peripheral = None
        self._status = OFF
        log.info("Controller Mode off (unload)")

    async def _start(self):
        self._error = None
        await self._set_status(STARTING)
        peripheral = Peripheral()
        self._peripheral = peripheral
        try:
            await asyncio.wait_for(peripheral.start(), self._start_timeout)
        except errors.ControllerModeError as e:
            self._fail(peripheral, e)
        except asyncio.TimeoutError:
            self._fail(peripheral, errors.start_failed("Bluetooth did not respond in time"))
        except Exception as e:
            log.exception("Controller Mode failed to start")
            self._fail(peripheral, errors.start_failed(repr(e)))
        else:
            if self._closed:
                peripheral.close()
                return
            log.info("Controller Mode on")
            await self._set_status(ON)
            return
        await self._set_status(OFF)

    def _fail(self, peripheral, error):
        log.warning("Controller Mode could not start: %s (%s)", error.code, error.detail)
        peripheral.close()
        self._peripheral = None
        self._error = error

    async def _stop(self):
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
