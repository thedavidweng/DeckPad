"""Failures underneath a running Controller Mode, and what the user sees about them. Driven through the
plugin backend the way Decky and the QAM panel drive it, against a fake org.bluez that can be
restarted or switched off."""

import asyncio
import unittest
from unittest import mock

from deckpad import controller_mode

from tests.support.fake_bluez import HOST_ADDRESS, STEAM_AGENT
from tests.support.plugin_case import PluginTestCase
from tests.test_connections import when
from tests.test_pairing_mode import settled


class FailureCase(PluginTestCase):
    async def asyncSetUp(self):
        for name, value in (("RECOVERY_TIMEOUT", 1.0), ("RECOVERY_RETRY_DELAY", 0.05)):
            patcher = mock.patch.object(controller_mode, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        await super().asyncSetUp()

    async def pair(self):
        await self.plugin.set_pairing_mode(True)
        device = await self.bluez.host_connects()
        await self.bluez.host_pairs(device)
        await settled(self.plugin, "paired")
        return device


class BluetoothRestartedUnderControllerMode(FailureCase):
    async def test_controller_mode_comes_back_on_by_itself(self):
        await self.plugin.set_controller_mode(True)

        await self.bluez.restart()
        state = await when(self.plugin, lambda s: s["status"] == "on" and self.bluez.applications, timeout=3)

        self.assertEqual(state["status"], "on")
        self.assertIsNone(state["error"])
        self.assertEqual(len(self.bluez.applications), 1)
        self.assertNotEqual(self.bluez.default_agent, STEAM_AGENT)

    async def test_the_panel_shows_controller_mode_waiting_for_bluetooth(self):
        await self.plugin.set_controller_mode(True)

        await self.bluez.stop_service()
        state = await when(self.plugin, lambda s: s["status"] == "recovering")

        self.assertEqual(state["status"], "recovering")
        self.assertIsNone(state["error"])

    async def test_bluetooth_that_does_not_come_back_turns_controller_mode_off_with_an_error(self):
        await self.plugin.set_controller_mode(True)

        await self.bluez.stop_service()
        state = await when(self.plugin, lambda s: s["status"] == "off", timeout=3)

        self.assertEqual(state["status"], "off")
        self.assertEqual(state["error"]["code"], "bluetooth_stopped")
        self.assertEqual(state["error"]["title"], "Controller Mode turned off")
        self.assertIn("Turn Controller Mode on again", state["error"]["message"])

    async def test_turning_controller_mode_off_while_waiting_keeps_it_off(self):
        await self.plugin.set_controller_mode(True)
        await self.bluez.stop_service()
        await when(self.plugin, lambda s: s["status"] == "recovering")

        state = await self.plugin.set_controller_mode(False)
        await self.bluez.start()
        await asyncio.sleep(0.3)

        self.assertEqual(state["status"], "off")
        self.assertEqual((await self.state())["status"], "off")
        self.assertTrue(self.bluez.is_clean(), self.bluez.registrations())

    async def test_unloading_while_waiting_leaves_bluetooth_alone_when_it_returns(self):
        await self.plugin.set_controller_mode(True)
        await self.bluez.stop_service()
        await when(self.plugin, lambda s: s["status"] == "recovering")

        await self.plugin._unload()
        await self.bluez.start()
        await asyncio.sleep(0.3)

        self.assertTrue(self.bluez.is_clean(), self.bluez.registrations())

    async def test_a_paired_host_is_still_paired_and_can_reconnect_afterwards(self):
        await self.plugin.set_controller_mode(True)
        device = await self.pair()

        await self.bluez.restart()
        state = await when(self.plugin, lambda s: s["status"] == "on" and s["connection"] == "waiting", timeout=3)

        self.assertEqual([h["address"] for h in state["hosts"]], [HOST_ADDRESS])
        self.assertEqual(state["connection"], "waiting")
        await self.bluez.host_reconnects(device)
        state = await when(self.plugin, lambda s: s["connection"] == "connected")
        self.assertEqual(state["connection"], "connected")


class AdapterSwitchedOffUnderControllerMode(FailureCase):
    async def test_switching_it_back_on_resumes_controller_mode(self):
        await self.plugin.set_controller_mode(True)

        self.bluez.set_powered(False)
        await when(self.plugin, lambda s: s["status"] == "recovering")
        self.bluez.set_powered(True)
        state = await when(self.plugin, lambda s: s["status"] == "on", timeout=3)

        self.assertEqual(state["status"], "on")
        self.assertEqual(len(self.bluez.applications), 1)

    async def test_leaving_it_off_turns_controller_mode_off_and_says_how_to_fix_it(self):
        await self.plugin.set_controller_mode(True)

        self.bluez.set_powered(False)
        state = await when(self.plugin, lambda s: s["status"] == "off", timeout=3)

        self.assertEqual(state["error"]["code"], "bluetooth_turned_off")
        self.assertIn("Turn it on in Steam's Bluetooth settings", state["error"]["message"])
        self.assertTrue(self.bluez.is_clean(), self.bluez.registrations())


class PanelActionsThatFail(FailureCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.plugin.set_controller_mode(True)
        self.device = await self.pair()

    async def test_a_forget_that_bluetooth_refuses_keeps_the_host_and_says_so(self):
        self.bluez.reject_remove_device = "Not Ready"

        state = await self.plugin.forget_host(HOST_ADDRESS)

        self.assertEqual([h["address"] for h in state["hosts"]], [HOST_ADDRESS])
        self.assertEqual(state["error"]["code"], "forget_failed")
        self.assertEqual(state["error"]["title"], "Could not forget mbp2019")
        self.assertIn("Steam's Bluetooth settings", state["error"]["message"])

    async def test_the_next_action_that_works_clears_the_error(self):
        self.bluez.reject_remove_device = "Not Ready"
        await self.plugin.forget_host(HOST_ADDRESS)
        self.bluez.reject_remove_device = None

        state = await self.plugin.forget_host(HOST_ADDRESS)

        self.assertEqual(state["hosts"], [])
        self.assertIsNone(state["error"])

    async def test_a_disconnect_that_bluetooth_refuses_says_so(self):
        self.bluez.reject_disconnect = "Not Connected"

        state = await self.plugin.disconnect_host(HOST_ADDRESS)

        self.assertEqual(state["error"]["code"], "disconnect_failed")
        self.assertEqual(state["error"]["title"], "Could not disconnect mbp2019")

    async def test_forgetting_while_controller_mode_is_off_and_bluetooth_is_not_running_says_so(self):
        await self.plugin.set_controller_mode(False)
        await self.bluez.stop_service()

        state = await self.plugin.forget_host(HOST_ADDRESS)

        self.assertEqual([h["address"] for h in state["hosts"]], [HOST_ADDRESS])
        self.assertEqual(state["error"]["code"], "forget_failed")

    async def test_paired_hosts_that_cannot_be_invited_back_are_explained(self):
        await self.plugin.set_controller_mode(False)
        self.bluez.reject_advertisement = "Maximum advertisements reached"

        state = await self.plugin.set_controller_mode(True)

        self.assertEqual(state["status"], "on")
        self.assertEqual(state["error"]["code"], "reconnect_unavailable")
        self.assertIn("Turn Controller Mode off and on", state["error"]["message"])


class StartStopStress(FailureCase):
    async def test_rapid_requests_from_the_panel_leave_bluetooth_clean(self):
        await self.plugin.set_controller_mode(True)
        device = await self.pair()

        requests = []
        for i in range(20):
            requests.append(self.plugin.set_controller_mode(i % 2 == 0))
            requests.append(self.plugin.set_pairing_mode(i % 3 == 0))
            requests.append(self.plugin.allow_reconnect())
        await asyncio.gather(*requests)
        await self.plugin.set_controller_mode(False)

        state = await self.state()
        self.assertEqual(state["status"], "off")
        self.assertTrue(await self.bluez.wait_until_clean(), self.bluez.registrations())
        self.assertFalse(self.bluez.devices[device].connected)
        self.assertEqual([h["address"] for h in state["hosts"]], [HOST_ADDRESS])

    async def test_bluetooth_restarting_in_the_middle_of_cycles_settles(self):
        for i in range(6):
            await self.plugin.set_controller_mode(True)
            if i == 2:
                await self.bluez.restart()
                await when(self.plugin, lambda s: s["status"] == "on", timeout=3)
            await self.plugin.set_controller_mode(False)

        self.assertEqual((await self.state())["status"], "off")
        self.assertTrue(await self.bluez.wait_until_clean(), self.bluez.registrations())


class TheNextLoadAfterTheBackendWasKilled(FailureCase):
    """Decky SIGKILLs a plugin that is slow to stop, so nothing ran to disconnect the Host."""

    async def kill_backend_with_a_host_connected(self):
        await self.plugin.set_controller_mode(True)
        device = await self.pair()
        await self.plugin._unload()
        # A killed process never sends Disconnect, so the Host keeps its link to bluetoothd.
        self.bluez.devices[device].update(connected=True)
        return device

    async def load_again(self):
        self.plugin = self.main.Plugin()
        await self.plugin._main()

    async def test_the_stale_host_link_is_dropped(self):
        device = await self.kill_backend_with_a_host_connected()

        await self.load_again()

        self.assertIn(("Disconnect", device), self.bluez.calls)
        self.assertFalse(self.bluez.devices[device].connected)

    async def test_other_connected_devices_are_left_alone(self):
        await self.kill_backend_with_a_host_connected()
        headphones = self.bluez.device("11:22:33:44:55:66", "Headphones")
        headphones.update(paired=True, connected=True)

        await self.load_again()

        self.assertNotIn(("Disconnect", headphones.path), self.bluez.calls)
        self.assertTrue(headphones.connected)

    async def test_controller_mode_is_off_and_can_be_turned_on(self):
        await self.kill_backend_with_a_host_connected()
        await self.load_again()

        self.assertEqual((await self.state())["status"], "off")
        state = await self.plugin.set_controller_mode(True)
        self.assertEqual(state["status"], "on")


if __name__ == "__main__":
    unittest.main()
