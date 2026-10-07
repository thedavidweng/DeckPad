"""Deck Controls reach the Connected Host: the controller's hidraw node in, GATT notifications out.

Driven through the plugin backend with a fake controller node and a fake org.bluez on a private bus.
"""

import asyncio
import unittest
from unittest import mock

from deckpad import deck_controls
from deckpad.link_monitor import FALLBACK_REPORT_INTERVAL

from tests.support.deck_state import deck_state_report
from tests.support.fake_controller import FakeController
from tests.support.plugin_case import PluginTestCase
from tests.test_connections import when

AT_REST = bytes.fromhex("00800080008000800000000000000000")
A_HELD = bytes.fromhex("00800080008000800000000000010000")


async def eventually(condition, timeout=2.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition() and loop.time() < deadline:
        await asyncio.sleep(0.01)
    return condition()


class InputCase(PluginTestCase):
    plugged_in = True

    async def asyncSetUp(self):
        self.controller = FakeController()
        self.addCleanup(self.controller.cleanup)
        if self.plugged_in:
            self.controller.plug_in()
        for name, value in (
            ("HIDRAW_CLASS", self.controller.hidraw_class),
            ("DEV_DIR", self.controller.dev_dir),
            ("REOPEN_DELAY", 0.05),
        ):
            patcher = mock.patch.object(deck_controls, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        await super().asyncSetUp()

    async def connect_host(self, subscribe=True):
        await self.plugin.set_controller_mode(True)
        await self.plugin.set_pairing_mode(True)
        device = await self.bluez.host_connects()
        self.assertTrue(await self.bluez.host_pairs(device))
        if subscribe:
            await self.bluez.host_subscribes()
        return device

    async def press(self, report, until=None, timeout=2.0):
        """Keep the controller streaming `report` (as the real one does at 250 Hz) until `until()` holds."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            self.controller.send(report)
            await asyncio.sleep(0.004)
            if until is not None and until():
                return True
        return until is None


class AConnectedHostReceivesTheDeckControls(InputCase):
    async def test_a_pressed_button_reaches_the_host(self):
        await self.connect_host()

        delivered = await self.press(deck_state_report("A"), until=lambda: A_HELD in self.bluez.gamepad_reports())

        self.assertTrue(delivered)

    async def test_releasing_it_returns_the_host_to_rest(self):
        await self.connect_host()
        await self.press(deck_state_report("A"), until=lambda: A_HELD in self.bluez.gamepad_reports())

        await self.press(deck_state_report(), until=lambda: self.bluez.gamepad_reports()[-1] == AT_REST)

        self.assertEqual(self.bluez.gamepad_reports()[-1], AT_REST)

    async def test_a_steady_state_is_sent_once(self):
        await self.connect_host()

        await self.press(deck_state_report("A"), timeout=0.5)

        self.assertEqual(self.bluez.gamepad_reports(), [A_HELD])

    async def test_the_host_reading_the_report_gets_the_current_state(self):
        await self.connect_host()
        await self.press(deck_state_report("A"), until=lambda: A_HELD in self.bluez.gamepad_reports())

        index = [p for p, _ in self.bluez.gatt_objects("org.bluez.GattCharacteristic1", "2a4d")].index(
            self.bluez.input_report_path()
        )

        self.assertEqual(await self.bluez.host_reads("2a4d", index), A_HELD)

    async def test_sustained_movement_is_paced_to_what_the_link_carries(self):
        await self.connect_host()
        loop = asyncio.get_running_loop()
        start = loop.time()
        n = 0
        while loop.time() - start < 1.0:
            # A stick sweeping without pause: every Deck State Report differs from the last.
            self.controller.send(deck_state_report(lx=n * 100 - 30000))
            n += 1
            await asyncio.sleep(0.004)
        elapsed = loop.time() - start

        sent = len(self.bluez.gamepad_reports())
        # Without root (as in these tests) DeckPad cannot learn the link's interval and paces conservatively.
        self.assertLessEqual(sent, elapsed / FALLBACK_REPORT_INTERVAL + 1)
        self.assertGreaterEqual(sent, 0.5 * elapsed / FALLBACK_REPORT_INTERVAL)


class AHostReturningInALaterSession(InputCase):
    """A Paired Host keeps the GATT database it discovered and reuses it when it reconnects. On the Deck,
    bluetoothd's Database Hash stops updating once its handles pass 1023, so the Host never learns of
    a new layout; the HID service must come back at the handles the Host already knows."""

    async def test_reports_reach_it_after_controller_mode_is_turned_off_and_on(self):
        device = await self.connect_host()
        cached = self.bluez.handle_of(self.bluez.input_report_path())
        await self.plugin.set_controller_mode(False)

        await self.plugin.set_controller_mode(True)
        await self.bluez.host_reconnects(device)
        await self.bluez.host_subscribes(handle=cached)
        delivered = await self.press(deck_state_report("A"), until=lambda: A_HELD in self.bluez.gamepad_reports())

        self.assertTrue(delivered)


class NobodyListening(InputCase):
    async def test_nothing_is_sent_before_the_host_subscribes(self):
        await self.connect_host(subscribe=False)

        await self.press(deck_state_report("A"), timeout=0.3)
        self.assertEqual(self.bluez.gamepad_reports(), [])

        await self.bluez.host_subscribes()
        delivered = await self.press(deck_state_report("A"), until=lambda: A_HELD in self.bluez.gamepad_reports())

        self.assertTrue(delivered)

    async def test_nothing_is_sent_while_no_host_is_connected(self):
        device = await self.connect_host()
        await self.bluez.host_disconnects(device)
        await asyncio.sleep(0.05)

        await self.press(deck_state_report("B"), timeout=0.3)

        self.assertEqual(self.bluez.gamepad_reports(), [])


class ReadingTheController(InputCase):
    async def test_the_controller_is_read_only_while_controller_mode_is_on(self):
        self.assertFalse(self.controller.is_open())

        await self.plugin.set_controller_mode(True)
        self.assertTrue(await eventually(self.controller.is_open))

        await self.plugin.set_controller_mode(False)
        self.assertFalse(self.controller.is_open())

    async def test_unloading_the_plugin_stops_reading_the_controller(self):
        await self.plugin.set_controller_mode(True)
        self.assertTrue(await eventually(self.controller.is_open))

        await self.plugin._unload()

        self.assertFalse(self.controller.is_open())

    async def test_lizard_mode_interfaces_are_never_opened(self):
        await self.plugin.set_controller_mode(True)
        await eventually(self.controller.is_open)

        self.assertTrue(self.controller.is_open())
        self.assertEqual(self.controller.opened_nodes(), {self.controller.node})


    async def test_the_panel_shows_the_controls_are_being_read(self):
        await self.plugin.set_controller_mode(True)
        await eventually(self.controller.is_open)

        state = await self.state()

        self.assertEqual(state["controls"], {"available": True, "message": None})

    async def test_a_controller_that_goes_away_is_reported_to_the_panel(self):
        await self.plugin.set_controller_mode(True)
        await eventually(self.controller.is_open)

        self.controller.unplug()
        state = await when(self.plugin, lambda s: not s["controls"]["available"])

        self.assertFalse(state["controls"]["available"])
        self.assertIn("cannot read the Deck's controls", state["controls"]["message"])

    async def test_without_controller_mode_nothing_is_reported(self):
        self.assertIsNone((await self.state())["controls"])


QUIT_COMBO = ("MENU", "VIEW", "LB", "RB")
QUIT_COMBO_HELD = bytes.fromhex("00800080008000800000000000c00c00")


class TheQuitCombo(InputCase):
    """Menu + View + L1 + R1 held together, as Moonlight's quit combo: leaves Controller Mode from the
    Deck's controls alone, even when Steam's UI on the Deck is not responding to them."""

    async def test_it_turns_controller_mode_off(self):
        await self.connect_host()

        await self.press(deck_state_report(*QUIT_COMBO), until=lambda: self.plugin_status() != "on")
        state = await when(self.plugin, lambda s: s["status"] == "off")

        self.assertEqual(state["status"], "off")

    async def test_the_host_is_left_with_nothing_held(self):
        await self.connect_host()
        await self.press(deck_state_report("A"), until=lambda: A_HELD in self.bluez.gamepad_reports())
        # Controller Mode off unregisters the GATT application, so note where the reports went first.
        path = self.bluez.input_report_path()

        await self.press(deck_state_report(*QUIT_COMBO), until=lambda: self.plugin_status() != "on")
        await when(self.plugin, lambda s: s["status"] == "off")

        reports = [value for p, value in self.bluez.notifications if p == path]
        self.assertNotIn(QUIT_COMBO_HELD, reports)
        self.assertEqual(reports[-1], AT_REST)

    async def test_another_button_held_with_it_is_sent_to_the_host_instead(self):
        await self.connect_host()

        await self.press(deck_state_report(*QUIT_COMBO, "A"), timeout=0.3)

        self.assertEqual(self.plugin_status(), "on")

    async def test_a_d_pad_direction_held_with_it_is_sent_to_the_host_instead(self):
        await self.connect_host()

        await self.press(deck_state_report(*QUIT_COMBO, "UP"), timeout=0.3)

        self.assertEqual(self.plugin_status(), "on")

    async def test_it_is_on_by_default(self):
        self.assertTrue((await self.state())["quit_combo"])

    async def test_turned_off_the_combo_goes_to_the_host(self):
        await self.plugin.set_quit_combo(False)
        await self.connect_host()

        delivered = await self.press(
            deck_state_report(*QUIT_COMBO), until=lambda: QUIT_COMBO_HELD in self.bluez.gamepad_reports()
        )

        self.assertTrue(delivered)
        self.assertEqual(self.plugin_status(), "on")

    async def test_turning_it_off_is_remembered_across_plugin_reloads(self):
        state = await self.plugin.set_quit_combo(False)
        self.assertFalse(state["quit_combo"])

        await self.plugin._unload()
        self.plugin = self.main.Plugin()

        self.assertFalse((await self.state())["quit_combo"])

    def plugin_status(self):
        return self.plugin._controller_mode.snapshot()["status"]


class TheControllerScreensPreview(InputCase):
    """While the Controller Screen watches, it gets the Gamepad Reports going to the Host (ADR-0013)."""

    def previews(self):
        return [args[0] for event, *args in self.decky.events if event == "gamepad_report"]

    def lit(self):
        previews = self.previews()
        return previews[-1]["buttons"] if previews else None

    async def test_a_pressed_button_lights_up(self):
        await self.connect_host()
        await self.plugin.watch_gamepad(True)

        lit = await self.press(deck_state_report("A"), until=lambda: self.lit() == ["a"])

        self.assertTrue(lit)

    async def test_it_works_before_any_host_is_connected(self):
        await self.plugin.set_controller_mode(True)
        await self.plugin.watch_gamepad(True)

        lit = await self.press(deck_state_report("B"), until=lambda: self.lit() == ["b"])

        self.assertTrue(lit)

    async def test_watching_starts_with_the_current_state(self):
        await self.plugin.watch_gamepad(True)

        self.assertTrue(await eventually(lambda: self.lit() == []))

    async def test_nothing_is_forwarded_while_nobody_watches(self):
        await self.connect_host()

        await self.press(deck_state_report("A"), until=lambda: A_HELD in self.bluez.gamepad_reports())

        self.assertEqual(self.previews(), [])

    async def test_it_stops_when_the_screen_stops_watching(self):
        await self.connect_host()
        await self.plugin.watch_gamepad(True)
        await self.press(deck_state_report("A"), until=lambda: self.lit() == ["a"])

        await self.plugin.watch_gamepad(False)
        await asyncio.sleep(0.05)
        seen = len(self.previews())
        await self.press(deck_state_report("X"), timeout=0.2)

        self.assertEqual(len(self.previews()), seen)

    async def test_it_is_paced_well_below_the_controllers_rate(self):
        await self.plugin.set_controller_mode(True)
        await self.plugin.watch_gamepad(True)

        # Alternating presses at 250 Hz for half a second: 125 changes.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 0.5
        held = False
        while loop.time() < deadline:
            held = not held
            self.controller.send(deck_state_report("A") if held else deck_state_report())
            await asyncio.sleep(0.004)

        self.assertGreater(len(self.previews()), 5)
        self.assertLessEqual(len(self.previews()), 0.5 * 30 + 3)

    async def test_the_quit_combo_shows_nothing_held(self):
        await self.connect_host()
        await self.plugin.watch_gamepad(True)

        await self.press(deck_state_report(*QUIT_COMBO), until=lambda: self.plugin_status() != "on")
        await when(self.plugin, lambda s: s["status"] == "off")

        self.assertTrue(await eventually(lambda: self.lit() == []))
        self.assertNotIn(["lb", "rb", "view", "menu"], self.previews())

    def plugin_status(self):
        return self.plugin._controller_mode.snapshot()["status"]


class AControllerThatAppearsLater(InputCase):
    plugged_in = False

    async def test_the_panel_says_the_controls_cannot_be_read(self):
        state = await self.plugin.set_controller_mode(True)

        self.assertFalse(state["controls"]["available"])
        self.assertIn("keeps trying", state["controls"]["message"])

    async def test_the_message_clears_once_it_appears(self):
        await self.plugin.set_controller_mode(True)

        self.controller.plug_in()
        state = await when(self.plugin, lambda s: s["controls"]["available"])

        self.assertTrue(state["controls"]["available"])

    async def test_controller_mode_turns_on_without_it(self):
        state = await self.plugin.set_controller_mode(True)

        self.assertEqual(state["status"], "on")

    async def test_input_flows_once_it_appears(self):
        await self.connect_host()
        await asyncio.sleep(0.1)

        self.controller.plug_in()
        delivered = await self.press(deck_state_report("A"), until=lambda: A_HELD in self.bluez.gamepad_reports())

        self.assertTrue(delivered)


if __name__ == "__main__":
    unittest.main()
