"""Pacing Gamepad Reports to what the Bluetooth link carries.

BlueZ queues notifications without bound, so anything sent faster than the link delivers arrives later
and later. The pacer keeps only the latest state, sends it only when it changed, and never sends more
than once per interval.
"""

import asyncio
import unittest

from deckpad.report_pacer import ReportPacer

INTERVAL = 0.05


class Link:
    """Stands in for the Connected Host: records what was sent, or refuses while nobody listens."""

    def __init__(self):
        self.sent = []
        self.listening = True

    def send(self, report):
        if not self.listening:
            return False
        self.sent.append(report)
        return True


class PacingGamepadReports(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.link = Link()
        self.pacer = ReportPacer(self.link.send, INTERVAL)
        self.addCleanup(self.pacer.close)

    async def test_a_change_after_a_quiet_spell_goes_out_at_once(self):
        self.pacer.offer(b"A")

        self.assertEqual(self.link.sent, [b"A"])

    async def test_an_unchanged_state_is_not_sent_again(self):
        self.pacer.offer(b"A")
        await asyncio.sleep(INTERVAL * 1.5)

        self.pacer.offer(b"A")
        await asyncio.sleep(INTERVAL * 1.5)

        self.assertEqual(self.link.sent, [b"A"])

    async def test_a_burst_of_changes_collapses_to_the_latest_state(self):
        for report in (b"A", b"B", b"C", b"D"):
            self.pacer.offer(report)

        await asyncio.sleep(INTERVAL * 1.5)

        self.assertEqual(self.link.sent, [b"A", b"D"])

    async def test_a_change_that_reverts_within_an_interval_is_not_sent(self):
        self.pacer.offer(b"A")
        self.pacer.offer(b"B")
        self.pacer.offer(b"A")

        await asyncio.sleep(INTERVAL * 1.5)

        self.assertEqual(self.link.sent, [b"A"])

    async def test_continuous_changes_are_capped_at_one_report_per_interval(self):
        loop = asyncio.get_running_loop()
        start = loop.time()
        n = 0
        while loop.time() - start < INTERVAL * 10:
            self.pacer.offer(b"%d" % n)
            n += 1
            await asyncio.sleep(0.004)
        elapsed = loop.time() - start

        self.assertGreater(n, 50)
        self.assertLessEqual(len(self.link.sent), elapsed / INTERVAL + 1)
        self.assertGreaterEqual(len(self.link.sent), 7)

    async def test_the_latest_state_is_what_the_host_ends_up_with(self):
        for n in range(30):
            self.pacer.offer(b"%d" % n)
            await asyncio.sleep(0.004)

        await asyncio.sleep(INTERVAL * 1.5)

        self.assertEqual(self.link.sent[-1], b"29")

    async def test_state_that_nobody_received_is_sent_once_a_host_listens(self):
        self.link.listening = False
        self.pacer.offer(b"A")
        await asyncio.sleep(INTERVAL * 1.5)

        self.link.listening = True
        self.pacer.offer(b"A")

        self.assertEqual(self.link.sent, [b"A"])

    async def test_the_pace_follows_what_the_link_carries_now(self):
        link_interval = [INTERVAL]
        pacer = ReportPacer(self.link.send, lambda: link_interval[0])
        self.addCleanup(pacer.close)
        # The link slows down (for example, a Host that kept a long connection interval).
        link_interval[0] = INTERVAL * 4
        loop = asyncio.get_running_loop()
        start = loop.time()
        n = 0
        while loop.time() - start < INTERVAL * 8:
            pacer.offer(b"%d" % n)
            n += 1
            await asyncio.sleep(0.004)

        self.assertLessEqual(len(self.link.sent), 3)

    async def test_a_report_sent_now_skips_the_wait_and_replaces_what_was_pending(self):
        self.pacer.offer(b"A")
        self.pacer.offer(b"B")

        self.pacer.send_now(b"REST")
        await asyncio.sleep(INTERVAL * 1.5)

        self.assertEqual(self.link.sent, [b"A", b"REST"])

    async def test_after_closing_nothing_more_is_sent(self):
        self.pacer.offer(b"A")
        self.pacer.offer(b"B")

        self.pacer.close()
        self.pacer.offer(b"C")
        await asyncio.sleep(INTERVAL * 1.5)

        self.assertEqual(self.link.sent, [b"A"])


if __name__ == "__main__":
    unittest.main()
