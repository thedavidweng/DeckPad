"""Loss of the raw controller releases state and re-arms Quit Combo."""

import asyncio
import os
import unittest
from unittest.mock import patch

from deckpad.deck_controls import DeckControls
from deckpad.gamepad_report import AT_REST
from tests.support.deck_state import deck_state_report


class ControllerLoss(unittest.IsolatedAsyncioTestCase):
    async def test_reader_registration_failure_closes_the_opened_fd(self):
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        controls = DeckControls(lambda _: False, 0.05)
        self.addCleanup(controls.stop)
        with patch("deckpad.deck_controls.find_controller_node", return_value="/dev/hidraw2"), \
                patch("deckpad.deck_controls.os.open", return_value=read_fd), \
                patch.object(asyncio.get_running_loop(), "add_reader", side_effect=OSError("reader unavailable")):
            controls.start()
        with self.assertRaises(OSError):
            os.fstat(read_fd)
        self.assertFalse(controls.available)
        self.assertIsNotNone(controls._retry)

    async def test_loss_releases_state_discards_pending_input_and_rearms_quit(self):
        sent, quit_calls = [], []
        controls = DeckControls(lambda report: sent.append(report) or True, 0.05,
                                on_quit_combo=lambda: quit_calls.append(True))
        self.addCleanup(controls.stop)
        controls._running = True
        controls._quit_combo_held = True
        controls._pacer.offer(b"held")
        controls._pacer.offer(b"pending")
        controls._lost("controller reset")
        self.assertEqual(sent[-1], AT_REST)
        self.assertFalse(controls._quit_combo_held)
        await asyncio.sleep(0.07)
        self.assertEqual(sent[-1], AT_REST)
        with patch("deckpad.deck_controls.os.read", side_effect=[
                deck_state_report("MENU", "VIEW", "LB", "RB"), BlockingIOError()]):
            controls._readable()
        self.assertEqual(quit_calls, [True])
