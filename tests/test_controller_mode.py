"""Controller mode lifecycle, driven through the plugin backend the way Decky and the QAM panel drive it,
and observed from BlueZ's side of the system bus."""

import asyncio
import unittest

from deckpad.bluetooth_watch import BluetoothWatch
from deckpad.peripheral import Peripheral

from tests.support.fake_bluez import STEAM_AGENT
from tests.support.plugin_case import PluginTestCase


class EnteringAndLeavingControllerMode(PluginTestCase):
    async def test_controller_mode_starts_off_and_leaves_bluetooth_untouched(self):
        state = await self.state()

        self.assertFalse(state["enabled"])
        self.assertTrue(self.bluez.is_clean())

    async def test_enabling_puts_the_deck_into_its_peripheral_role(self):
        state = await self.plugin.set_controller_mode(True)

        self.assertTrue(state["enabled"])
        self.assertEqual(state, await self.state())
        self.assertEqual(len(self.bluez.applications), 1)
        self.assertNotEqual(self.bluez.default_agent, STEAM_AGENT)
        self.assertEqual(self.bluez.agents[self.bluez.default_agent], "NoInputNoOutput")

    async def test_the_peripheral_presents_the_controller_identity(self):
        await self.plugin.set_controller_mode(True)

        (objects,) = self.bluez.applications.values()
        pnp_ids = [
            obj["org.bluez.GattCharacteristic1"]
            for obj in objects.values()
            if obj.get("org.bluez.GattCharacteristic1", {}).get("UUID") == "00002a50-0000-1000-8000-00805f9b34fb"
        ]
        self.assertEqual(len(pnp_ids), 1)
        self.assertEqual(bytes(pnp_ids[0]["Value"]), bytes.fromhex("025e04130b0905"))

    async def test_disabling_restores_ordinary_bluetooth(self):
        await self.plugin.set_controller_mode(True)

        state = await self.plugin.set_controller_mode(False)

        self.assertFalse(state["enabled"])
        self.assertIsNone(state["error"])
        self.assertTrue(self.bluez.is_clean(), self.bluez.registrations())
        self.assertEqual(self.bluez.default_agent, STEAM_AGENT)

    async def test_repeated_cycles_leave_bluetooth_clean_every_time(self):
        for _ in range(5):
            on = await self.plugin.set_controller_mode(True)
            self.assertTrue(on["enabled"])
            self.assertEqual(len(self.bluez.applications), 1)
            off = await self.plugin.set_controller_mode(False)
            self.assertFalse(off["enabled"])
            self.assertTrue(self.bluez.is_clean(), self.bluez.registrations())

    async def test_repeated_requests_for_the_current_state_change_nothing(self):
        await self.plugin.set_controller_mode(False)
        self.assertTrue(self.bluez.is_clean())

        await self.plugin.set_controller_mode(True)
        state = await self.plugin.set_controller_mode(True)

        self.assertTrue(state["enabled"])
        self.assertEqual(len(self.bluez.applications), 1)
        self.assertEqual(len(self.bluez.agents), 1)

    async def test_overlapping_requests_settle_on_the_last_one(self):
        await asyncio.gather(
            self.plugin.set_controller_mode(True),
            self.plugin.set_controller_mode(False),
            self.plugin.set_controller_mode(True),
            self.plugin.set_controller_mode(False),
        )

        self.assertFalse((await self.state())["enabled"])
        self.assertTrue(self.bluez.is_clean(), self.bluez.registrations())

    async def test_the_panel_is_told_about_every_transition(self):
        await self.plugin.set_controller_mode(True)
        await self.plugin.set_controller_mode(False)

        statuses = [args[0]["status"] for event, *args in self.decky.events if event == "controller_mode_state"]
        self.assertEqual(statuses, ["starting", "on", "stopping", "off"])


class UnloadingThePlugin(PluginTestCase):
    async def test_unloading_while_on_restores_ordinary_bluetooth(self):
        await self.plugin.set_controller_mode(True)

        await self.plugin._unload()

        self.assertTrue(await self.bluez.wait_until_clean(), self.bluez.registrations())

    async def test_a_reloaded_plugin_starts_off_and_can_enable_again(self):
        await self.plugin.set_controller_mode(True)
        await self.plugin._unload()

        self.plugin = self.main.Plugin()
        await self.plugin._main()

        self.assertFalse((await self.state())["enabled"])
        self.assertTrue((await self.plugin.set_controller_mode(True))["enabled"])
        self.assertEqual(len(self.bluez.applications), 1)

    async def test_requests_after_unload_are_ignored(self):
        await self.plugin._unload()

        state = await self.plugin.set_controller_mode(True)

        self.assertFalse(state["enabled"])
        self.assertTrue(self.bluez.is_clean())

    async def test_unload_completes_without_the_event_loop(self):
        # Decky Loader 3.2.9 closes the plugin's socket while _unload runs, and its socket reader then
        # spins without yielding, so nothing that waits on the event loop ever resumes.
        await self.plugin.set_controller_mode(True)

        unload = self.plugin._unload()
        with self.assertRaises(StopIteration):
            unload.send(None)

        self.assertTrue(await self.bluez.wait_until_clean(), self.bluez.registrations())
        self.assertEqual(self.bluez.default_agent, STEAM_AGENT)

    async def test_unload_finishes_and_releases_bluetooth_even_if_bluez_stops_answering(self):
        await self.plugin.set_controller_mode(True)
        self.bluez.hang_unregister = True

        await asyncio.wait_for(self.plugin._unload(), 20)

        self.assertTrue(await self.bluez.wait_until_clean(), self.bluez.registrations())


class ReleasingASessionTwice(PluginTestCase):
    """Unload can release a session that a start still finishing then releases again."""

    async def test_a_peripheral_can_be_closed_again(self):
        peripheral = Peripheral()
        await peripheral.start()

        peripheral.close()
        peripheral.close()
        await peripheral.stop()

        self.assertTrue(await self.bluez.wait_until_clean(), self.bluez.registrations())

    async def test_a_bluetooth_watch_can_be_stopped_again(self):
        lost = []
        watch = BluetoothWatch(lost.append)
        await watch.start()

        watch.stop()
        watch.stop()
        await self.bluez.restart()
        await asyncio.sleep(0.05)

        self.assertEqual(lost, [])


class BluetoothNotRunning(PluginTestCase):
    bluez_options = None

    async def test_enabling_fails_with_an_actionable_error(self):
        state = await self.plugin.set_controller_mode(True)

        self.assertFalse(state["enabled"])
        self.assertEqual(state["status"], "off")
        self.assertEqual(state["error"]["code"], "bluetooth_unavailable")
        self.assertTrue(state["error"]["message"])


class NoBluetoothAdapter(PluginTestCase):
    bluez_options = {"adapter": False}

    async def test_enabling_fails_with_an_actionable_error(self):
        state = await self.plugin.set_controller_mode(True)

        self.assertFalse(state["enabled"])
        self.assertEqual(state["error"]["code"], "no_adapter")
        self.assertTrue(self.bluez.is_clean())


class BluetoothTurnedOff(PluginTestCase):
    bluez_options = {"powered": False}

    async def test_enabling_fails_and_asks_the_user_to_turn_bluetooth_on(self):
        state = await self.plugin.set_controller_mode(True)

        self.assertFalse(state["enabled"])
        self.assertEqual(state["error"]["code"], "bluetooth_off")
        self.assertIn("Turn it on", state["error"]["message"])
        self.assertTrue(self.bluez.is_clean())


class BluezRejectsThePeripheral(PluginTestCase):
    async def test_a_failed_start_rolls_back_and_can_be_retried(self):
        self.bluez.reject_application = "No valid service object found"

        failed = await self.plugin.set_controller_mode(True)

        self.assertFalse(failed["enabled"])
        self.assertEqual(failed["error"]["code"], "start_failed")
        self.assertTrue(self.bluez.is_clean(), self.bluez.registrations())

        self.bluez.reject_application = None
        retried = await self.plugin.set_controller_mode(True)

        self.assertTrue(retried["enabled"])
        self.assertIsNone(retried["error"])

    async def test_turning_the_toggle_off_dismisses_the_error(self):
        self.bluez.reject_application = "No valid service object found"
        await self.plugin.set_controller_mode(True)

        state = await self.plugin.set_controller_mode(False)

        self.assertIsNone(state["error"])


if __name__ == "__main__":
    unittest.main()
