"""Latest-state-wins pacing of Gamepad Reports.

BlueZ queues GATT notifications without bound and the link carries only so many per second, so every
report sent beyond that adds latency that never goes away. The pacer holds at most one pending report
(the latest), sends only when it differs from what the Host last received, and sends at most once
per interval.
"""

import asyncio
import logging

log = logging.getLogger("deckpad.report_pacer")


class ReportPacer:
    def __init__(self, send, interval):
        """`send(report)` returns True if the report went to a Host, False if nobody was listening.

        `interval` is the minimum time between sends in seconds, or a function returning it, which is
        asked again before every send because the link's capacity can change during a session.
        """
        self._send = send
        self._interval = interval if callable(interval) else (lambda: interval)
        self._delivered = None
        self._pending = None
        self._timer = None
        self._closed = False

    def offer(self, report):
        if self._closed:
            return
        if self._timer is not None:
            self._pending = report
            return
        self._transmit(report)

    def close(self):
        self._closed = True
        self._pending = None
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _transmit(self, report):
        if report == self._delivered:
            return
        try:
            delivered = self._send(report)
        except Exception:
            log.exception("Could not send a Gamepad Report")
            delivered = False
        # Forgetting undelivered state makes the next offer go out even if it is unchanged, so a Host
        # that starts listening gets the current state rather than nothing.
        self._delivered = report if delivered else None
        self._timer = asyncio.get_running_loop().call_later(self._interval(), self._tick)

    def _tick(self):
        self._timer = None
        pending, self._pending = self._pending, None
        if pending is not None and not self._closed:
            self._transmit(pending)
