"""Forwards the reports sent to the host to the controller screen.

Reports arrive at the link's pace (about 50 per second) and each one crosses Decky's websocket to the
frontend, so at most one per PREVIEW_INTERVAL is forwarded, always the latest, and none while the
controller screen is closed.
"""

import asyncio
import logging

from .gamepad_report import AT_REST, describe

log = logging.getLogger("deckpad.gamepad_preview")

PREVIEW_INTERVAL = 1 / 30


class GamepadPreview:
    def __init__(self, publish, interval=PREVIEW_INTERVAL):
        self._publish = publish
        self._interval = interval
        self._watching = False
        self._latest = AT_REST
        self._published = None
        self._timer = None
        self._task = None

    @property
    def watching(self):
        return self._watching

    def watch(self, enabled):
        """Starting sends the current state at once, so the drawing is never blank."""
        self._watching = bool(enabled)
        if self._watching:
            self._published = None
            self._flush()
        else:
            self._cancel_timer()

    def show(self, report):
        self._latest = report
        if self._watching and self._timer is None:
            self._flush()

    def reset(self):
        self.show(AT_REST)

    def close(self):
        """Synchronous, so it can run during plugin unload."""
        self._watching = False
        self._cancel_timer()
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def _flush(self):
        self._timer = None
        if not self._watching or self._latest == self._published:
            return
        self._published = self._latest
        if self._task is not None and not self._task.done():
            # The previous report is still crossing to the frontend; the timer picks up this one next.
            self._published = None
        else:
            self._task = asyncio.get_running_loop().create_task(self._send(describe(self._latest)))
        self._timer = asyncio.get_running_loop().call_later(self._interval, self._flush)

    async def _send(self, described):
        try:
            await self._publish(described)
        except Exception as e:
            log.warning("Could not publish a Gamepad Report preview: %r", e)

    def _cancel_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
