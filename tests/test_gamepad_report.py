"""What the Host receives for each Deck Control: Deck State Report in, Xbox 1914 Gamepad Report out.

Expected values follow the Xbox Wireless Controller's BLE input report 0x01 as SDL and Linux read it:
sticks are u16 centred at 0x8000 with Y pointing down, triggers are 10-bit, the hat counts clockwise
from 1 (up) with 0 for neutral, and buttons sit in bytes 13-15.
"""

import struct
import unittest

from deckpad.gamepad_report import describe, gamepad_report

from tests.support.deck_state import deck_state_report

NEUTRAL = bytes.fromhex("00800080008000800000000000000000")


def fields(report):
    lx, ly, rx, ry, lt, rt, hat, b13, b14, b15 = struct.unpack("<HHHHHHBBBB", report)
    return {"lx": lx, "ly": ly, "rx": rx, "ry": ry, "lt": lt, "rt": rt, "hat": hat, "buttons": (b13, b14, b15)}


class ButtonsOnTheHost(unittest.TestCase):
    def test_nothing_held_is_the_report_at_rest(self):
        self.assertEqual(gamepad_report(deck_state_report()), NEUTRAL)

    def test_each_core_button_lights_its_xbox_bit(self):
        expected = {
            "A": (0x01, 0x00, 0x00),
            "B": (0x02, 0x00, 0x00),
            "X": (0x08, 0x00, 0x00),
            "Y": (0x10, 0x00, 0x00),
            "LB": (0x40, 0x00, 0x00),
            "RB": (0x80, 0x00, 0x00),
            "VIEW": (0x00, 0x04, 0x00),
            "MENU": (0x00, 0x08, 0x00),
            "STEAM": (0x00, 0x10, 0x00),
            "L3": (0x00, 0x20, 0x00),
            "R3": (0x00, 0x40, 0x00),
            "QAM": (0x00, 0x00, 0x01),
        }
        for button, bits in expected.items():
            with self.subTest(button=button):
                self.assertEqual(fields(gamepad_report(deck_state_report(button)))["buttons"], bits)

    def test_buttons_held_together_combine(self):
        report = fields(gamepad_report(deck_state_report("A", "Y", "RB", "MENU", "QAM")))

        self.assertEqual(report["buttons"], (0x91, 0x08, 0x01))

    def test_deck_only_controls_do_not_reach_the_host(self):
        # Rear buttons, trackpad clicks and the triggers' digital click have no slot in the 1914 report.
        report = deck_state_report("L4", "L5", "R4", "R5", "LEFT_PAD_CLICK", "RIGHT_PAD_CLICK", "L2", "R2")

        self.assertEqual(gamepad_report(report), NEUTRAL)


class DPadOnTheHost(unittest.TestCase):
    def test_each_direction_is_a_hat_position(self):
        expected = {
            ("UP",): 1,
            ("UP", "RIGHT"): 2,
            ("RIGHT",): 3,
            ("DOWN", "RIGHT"): 4,
            ("DOWN",): 5,
            ("DOWN", "LEFT"): 6,
            ("LEFT",): 7,
            ("UP", "LEFT"): 8,
        }
        for held, hat in expected.items():
            with self.subTest(held=held):
                self.assertEqual(fields(gamepad_report(deck_state_report(*held)))["hat"], hat)

    def test_opposite_directions_cancel_out(self):
        self.assertEqual(fields(gamepad_report(deck_state_report("UP", "DOWN")))["hat"], 0)
        self.assertEqual(fields(gamepad_report(deck_state_report("LEFT", "RIGHT", "UP")))["hat"], 1)

    def test_the_d_pad_does_not_press_buttons(self):
        report = fields(gamepad_report(deck_state_report("UP", "LEFT")))

        self.assertEqual(report["buttons"], (0, 0, 0))


class SticksOnTheHost(unittest.TestCase):
    def test_both_sticks_at_rest_are_centred(self):
        report = fields(gamepad_report(deck_state_report()))

        self.assertEqual((report["lx"], report["ly"], report["rx"], report["ry"]), (0x8000,) * 4)

    def test_full_deflection_reaches_each_end_of_every_axis(self):
        cases = {
            "left stick right": (dict(lx=32767), "lx", 0xFFFF),
            "left stick left": (dict(lx=-32768), "lx", 0x0000),
            "left stick up": (dict(ly=32767), "ly", 0x0000),
            "left stick down": (dict(ly=-32768), "ly", 0xFFFF),
            "right stick right": (dict(rx=32767), "rx", 0xFFFF),
            "right stick left": (dict(rx=-32768), "rx", 0x0000),
            "right stick up": (dict(ry=32767), "ry", 0x0000),
            "right stick down": (dict(ry=-32768), "ry", 0xFFFF),
        }
        for name, (stick, axis, value) in cases.items():
            with self.subTest(name):
                self.assertEqual(fields(gamepad_report(deck_state_report(**stick)))[axis], value)

    def test_partial_deflection_is_proportional(self):
        report = fields(gamepad_report(deck_state_report(lx=16384, ly=16384, rx=-16384, ry=-16384)))

        # Half right, half up, half left, half down, to within one step.
        self.assertAlmostEqual(report["lx"], 0xC000, delta=1)
        self.assertAlmostEqual(report["ly"], 0x4000, delta=1)
        self.assertAlmostEqual(report["rx"], 0x4000, delta=1)
        self.assertAlmostEqual(report["ry"], 0xC000, delta=1)

    def test_each_axis_moves_only_its_own_value(self):
        report = fields(gamepad_report(deck_state_report(rx=1000)))

        self.assertEqual((report["lx"], report["ly"], report["ry"]), (0x8000, 0x8000, 0x8000))
        self.assertEqual(report["rx"], 0x8000 + 1000)


class TriggersOnTheHost(unittest.TestCase):
    def test_released_triggers_read_zero(self):
        report = fields(gamepad_report(deck_state_report()))

        self.assertEqual((report["lt"], report["rt"]), (0, 0))

    def test_fully_pulled_triggers_read_the_10_bit_maximum(self):
        report = fields(gamepad_report(deck_state_report(lt=32767, rt=32767)))

        self.assertEqual((report["lt"], report["rt"]), (1023, 1023))

    def test_a_half_pulled_trigger_reads_about_half(self):
        report = fields(gamepad_report(deck_state_report(lt=16384)))

        self.assertEqual(report["lt"], 511)
        self.assertEqual(report["rt"], 0)

    def test_negative_trigger_noise_reads_as_released(self):
        report = fields(gamepad_report(deck_state_report(lt=-5, rt=-1)))

        self.assertEqual((report["lt"], report["rt"]), (0, 0))


class ReportsThatAreNotDeckState(unittest.TestCase):
    def test_other_controller_reports_are_ignored(self):
        other = bytearray(deck_state_report("A"))
        other[2] = 0x04  # e.g. a battery/status report on the same node

        self.assertIsNone(gamepad_report(bytes(other)))

    def test_short_reads_are_ignored(self):
        self.assertIsNone(gamepad_report(deck_state_report("A")[:40]))


class TheControllerScreensDrawing(unittest.TestCase):
    """`describe` turns the report the Host gets into what the Controller Screen lights up."""

    def drawn(self, *buttons, **axes):
        return describe(gamepad_report(deck_state_report(*buttons, **axes)))

    def test_nothing_held_draws_nothing_lit_and_sticks_centred(self):
        self.assertEqual(
            self.drawn(),
            {"buttons": [], "left_stick": [0, 0], "right_stick": [0, 0], "left_trigger": 0, "right_trigger": 0},
        )

    def test_each_button_the_host_gets_is_named(self):
        expected = {
            "A": "a",
            "B": "b",
            "X": "x",
            "Y": "y",
            "LB": "lb",
            "RB": "rb",
            "VIEW": "view",
            "MENU": "menu",
            "STEAM": "guide",
            "L3": "l3",
            "R3": "r3",
            "QAM": "share",
        }
        for deck_button, name in expected.items():
            with self.subTest(deck_button):
                self.assertEqual(self.drawn(deck_button)["buttons"], [name])

    def test_deck_only_controls_light_nothing(self):
        self.assertEqual(self.drawn("L4", "R5", "LEFT_PAD_CLICK")["buttons"], [])

    def test_a_diagonal_lights_both_d_pad_directions(self):
        self.assertEqual(self.drawn("UP", "LEFT")["buttons"], ["dpad_up", "dpad_left"])

    def test_sticks_run_from_minus_one_to_one_with_y_pointing_down(self):
        drawn = self.drawn(lx=-32768, ly=32767, rx=32767, ry=-32768)

        self.assertEqual(drawn["left_stick"], [-1, -1])
        self.assertEqual(drawn["right_stick"], [1, 1])

    def test_triggers_run_from_zero_to_one(self):
        drawn = self.drawn(lt=0x7FFF, rt=0x3FFF)

        self.assertEqual(drawn["left_trigger"], 1)
        self.assertAlmostEqual(drawn["right_trigger"], 0.5, places=2)


if __name__ == "__main__":
    unittest.main()
