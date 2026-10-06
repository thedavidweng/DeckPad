"""Troubleshooting diagnostics: what the panel's secondary Troubleshooting section shows and copies.

Driven through the plugin backend against a fake org.bluez on a private bus. The tests do not run as
root, as DeckPad would on a misconfigured Decky."""

import unittest
from unittest import mock

from tests.support.deck_state import deck_state_report
from tests.support.fake_bluez import HOST_ADDRESS
from tests.support.plugin_case import PluginTestCase
from tests.test_input_pipeline import A_HELD, InputCase
from tests.test_pairing_mode import settled


class Diagnostics(PluginTestCase):
    async def test_they_describe_controller_mode_and_bluetooth(self):
        await self.plugin.set_controller_mode(True)

        diagnostics = await self.plugin.get_diagnostics()

        self.assertIn("Controller Mode: on", diagnostics["text"])
        self.assertIn("Bluetooth service: running", diagnostics["text"])
        self.assertIn("E8:FB:1C:43:F3:44", diagnostics["text"])
        self.assertIn("dbus-fast 5.2.0", diagnostics["text"])

    async def test_they_list_paired_hosts(self):
        await self.plugin.set_controller_mode(True)
        await self.plugin.set_pairing_mode(True)
        device = await self.bluez.host_connects()
        await self.bluez.host_pairs(device)
        await settled(self.plugin, "paired")

        diagnostics = await self.plugin.get_diagnostics()

        self.assertIn("%s mbp2019 (connected)" % HOST_ADDRESS, diagnostics["text"])

    async def test_they_say_which_root_only_features_are_unavailable(self):
        diagnostics = await self.plugin.get_diagnostics()

        self.assertIn("Running as root: no", diagnostics["text"])
        self.assertIn("Controller Identity override: unavailable (needs root)", diagnostics["text"])
        self.assertIn("Shorter connection interval: unavailable (needs root)", diagnostics["text"])

    async def test_they_include_recent_log_lines(self):
        await self.plugin.set_controller_mode(True)

        diagnostics = await self.plugin.get_diagnostics()

        self.assertIn("Controller Mode on", diagnostics["text"])

    async def test_they_are_saved_to_a_file_in_the_plugin_log_directory(self):
        diagnostics = await self.plugin.get_diagnostics()

        self.assertTrue(diagnostics["path"].startswith(self.decky.DECKY_PLUGIN_LOG_DIR))
        with open(diagnostics["path"]) as f:
            self.assertEqual(f.read(), diagnostics["text"])

    async def test_the_summary_gives_the_panel_short_label_value_pairs(self):
        await self.plugin.set_controller_mode(True)

        diagnostics = await self.plugin.get_diagnostics()

        summary = dict(diagnostics["summary"])
        self.assertEqual(summary["Bluetooth service"], "running")
        self.assertEqual(summary["Deck's controls"], "not found")


class DiagnosticsWhenSomethingIsWrong(PluginTestCase):
    bluez_options = {"powered": False}

    async def test_they_include_the_detail_behind_an_error(self):
        await self.plugin.set_controller_mode(True)

        diagnostics = await self.plugin.get_diagnostics()

        self.assertIn("Last error: bluetooth_off", diagnostics["text"])
        self.assertIn("powered no", diagnostics["text"])


class WhenErrorsHappened(PluginTestCase):
    async def test_errors_still_on_the_panel_keep_the_time_they_happened(self):
        await self.plugin.set_controller_mode(True)
        self.bluez.reject_advertisement = "Maximum advertisements reached"
        with mock.patch("time.time", return_value=HAPPENED):
            await self.plugin.set_pairing_mode(True)

        with mock.patch("time.time", return_value=HAPPENED + 3600):
            diagnostics = await self.plugin.get_diagnostics()

        self.assertIn("  2026-10-06T12:00:00Z advertising_failed:", diagnostics["text"])
        self.assertNotIn("13:00:00Z advertising_failed", diagnostics["text"])


# 2026-10-06T12:00:00Z
HAPPENED = 1791288000


class DiagnosticsWithoutBluetooth(PluginTestCase):
    bluez_options = None

    async def test_they_say_the_bluetooth_service_is_not_running(self):
        diagnostics = await self.plugin.get_diagnostics()

        self.assertEqual(dict(diagnostics["summary"])["Bluetooth service"], "not running")


class DiagnosticsAboutInput(InputCase):
    async def test_they_count_gamepad_reports_the_host_received(self):
        await self.connect_host()
        await self.press(deck_state_report("A"), until=lambda: A_HELD in self.bluez.gamepad_reports())

        diagnostics = await self.plugin.get_diagnostics()

        self.assertRegex(diagnostics["text"], r"Gamepad Reports: [1-9]\d* delivered")

    async def test_they_show_reports_going_nowhere_when_the_host_never_subscribed(self):
        await self.connect_host(subscribe=False)
        await self.press(deck_state_report("A"), timeout=0.3)

        diagnostics = await self.plugin.get_diagnostics()

        self.assertRegex(diagnostics["text"], r"Gamepad Reports: 0 delivered, [1-9]\d* not delivered")


if __name__ == "__main__":
    unittest.main()
