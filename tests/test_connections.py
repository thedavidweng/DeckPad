"""Everyday connection management from the QAM panel: which Paired Host is connected, a returning Host
reconnecting without pairing again, Disconnect, and Forget. Driven through the plugin backend, observed
from BlueZ's side."""

import asyncio
import unittest

from tests.support.fake_bluez import HOST_ADDRESS, HOST_NAME
from tests.support.plugin_case import PluginTestCase
from tests.test_pairing_mode import eventually, eventually_async, settled


def deckpad_work_in_progress():
    """Coroutines of DeckPad's backend still scheduled on the event loop."""
    return [
        task.get_coro().__qualname__
        for task in asyncio.all_tasks()
        if not task.done() and "py_modules/deckpad/" in task.get_coro().cr_code.co_filename
    ]


class ConnectionsCase(PluginTestCase):
    async def pair(self, address=HOST_ADDRESS, name=HOST_NAME):
        """A Host pairs through Pairing Mode, the way a new user sets it up."""
        await self.plugin.set_pairing_mode(True)
        device = await self.bluez.host_connects(address, name)
        await self.bluez.host_pairs(device)
        await settled(self.plugin, "paired")
        return device

    async def reload_plugin(self):
        """Decky reloads the plugin: a fresh backend process reading the same settings directory."""
        await self.plugin._unload()
        self.plugin = self.main.Plugin()
        await self.plugin._main()


class ConnectionStatus(ConnectionsCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.plugin.set_controller_mode(True)

    async def test_with_no_paired_hosts_nothing_is_connected(self):
        state = await self.state()

        self.assertEqual(state["hosts"], [])
        self.assertEqual(state["connection"], "idle")

    async def test_the_panel_shows_which_paired_host_is_connected(self):
        await self.pair()

        state = await when(self.plugin, lambda s: s["connection"] == "connected")

        self.assertEqual(state["hosts"], [{"address": HOST_ADDRESS, "name": HOST_NAME, "connected": True}])

    async def test_a_host_whose_name_bluetooth_learns_later_is_shown_and_remembered_by_name(self):
        device = await self.pair(name="38-F9-D3-C3-E9-69")

        self.bluez.devices[device].update(alias=HOST_NAME)
        state = await when(self.plugin, lambda s: s["hosts"] and s["hosts"][0]["name"] == HOST_NAME)

        self.assertEqual(state["hosts"][0]["name"], HOST_NAME)
        await self.plugin.set_controller_mode(False)
        await self.reload_plugin()
        self.assertEqual((await self.state())["hosts"], [{"address": HOST_ADDRESS, "name": HOST_NAME, "connected": False}])

    async def test_a_host_whose_name_is_still_unknown_has_no_name(self):
        await self.pair(name="38-F9-D3-C3-E9-69")

        state = await when(self.plugin, lambda s: s["connection"] == "connected")

        self.assertIsNone(state["hosts"][0]["name"])

    async def test_the_deck_s_other_bluetooth_devices_are_not_listed(self):
        headphones = self.bluez.device("4C:87:5D:98:4A:A4", "Headphones")
        headphones.update(connected=True, paired=True)
        await asyncio.sleep(0.05)

        self.assertEqual((await self.state())["hosts"], [])


class AReturningHost(ConnectionsCase):
    """A Paired Host comes back in a later Controller Mode session, or after its link dropped."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.plugin.set_controller_mode(True)
        self.device = await self.pair()
        await self.plugin.set_controller_mode(False)

    async def test_the_deck_waits_for_paired_hosts_without_being_listed_in_scans(self):
        state = await self.plugin.set_controller_mode(True)

        self.assertEqual(state["pairing"]["status"], "closed")
        self.assertEqual(state["connection"], "waiting")
        adv = self.bluez.advertisement
        self.assertEqual(adv["Type"], "peripheral")
        self.assertFalse(adv["Discoverable"])

    async def test_reconnects_without_pairing_again(self):
        await self.plugin.set_controller_mode(True)

        await self.bluez.host_reconnects(self.device)

        state = await when(self.plugin, lambda s: s["connection"] == "connected")
        self.assertEqual(state["hosts"], [{"address": HOST_ADDRESS, "name": HOST_NAME, "connected": True}])
        self.assertEqual(state["pairing"]["status"], "closed")
        self.assertTrue(await eventually(lambda: self.bluez.advertisement is None))

    async def test_reconnects_after_its_link_drops(self):
        await self.plugin.set_controller_mode(True)
        await self.bluez.host_reconnects(self.device)
        await when(self.plugin, lambda s: s["connection"] == "connected")

        await self.bluez.host_disconnects(self.device)

        state = await when(self.plugin, lambda s: s["connection"] == "waiting")
        self.assertEqual(state["connection"], "waiting")
        self.assertTrue(await eventually(lambda: self.bluez.advertisement is not None))
        await self.bluez.host_reconnects(self.device)
        self.assertEqual((await when(self.plugin, lambda s: s["connection"] == "connected"))["connection"], "connected")

    async def test_reconnects_after_a_plugin_reload(self):
        await self.reload_plugin()
        await self.plugin.set_controller_mode(True)

        await self.bluez.host_reconnects(self.device)

        self.assertEqual((await when(self.plugin, lambda s: s["connection"] == "connected"))["connection"], "connected")

    async def test_pairing_mode_still_makes_the_deck_discoverable(self):
        await self.plugin.set_controller_mode(True)

        await self.plugin.set_pairing_mode(True)

        self.assertTrue(self.bluez.advertisement["Discoverable"])
        self.assertEqual(len(self.bluez.advertisements), 1)

    async def test_the_deck_waits_again_once_pairing_mode_closes(self):
        await self.plugin.set_controller_mode(True)
        await self.plugin.set_pairing_mode(True)

        await self.plugin.set_pairing_mode(False)

        self.assertTrue(await eventually(lambda: self.bluez.advertisement and not self.bluez.advertisement["Discoverable"]))

    async def test_turning_off_stops_waiting(self):
        await self.plugin.set_controller_mode(True)

        state = await self.plugin.set_controller_mode(False)

        self.assertEqual(state["connection"], "idle")
        self.assertTrue(self.bluez.is_clean(), self.bluez.registrations())


class DisconnectingFromThePanel(ConnectionsCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.plugin.set_controller_mode(True)
        self.device = await self.pair()
        await when(self.plugin, lambda s: s["connection"] == "connected")
        self.bluez.disconnect_requests.clear()

    async def test_disconnect_drops_the_link_and_keeps_the_pairing(self):
        state = await self.plugin.disconnect_host(HOST_ADDRESS)

        self.assertEqual(self.bluez.disconnect_requests, [self.device])
        self.assertTrue(self.bluez.devices[self.device].paired)
        state = await when(self.plugin, lambda s: not s["hosts"][0]["connected"])
        self.assertEqual(state["hosts"], [{"address": HOST_ADDRESS, "name": HOST_NAME, "connected": False}])

    async def test_a_disconnected_host_does_not_come_straight_back(self):
        await self.plugin.disconnect_host(HOST_ADDRESS)

        state = await when(self.plugin, lambda s: s["connection"] == "paused")

        self.assertEqual(state["connection"], "paused")
        await asyncio.sleep(0.05)
        self.assertIsNone(self.bluez.advertisement)
        self.assertTrue(state["enabled"])

    async def test_reconnecting_can_be_allowed_again(self):
        await self.plugin.disconnect_host(HOST_ADDRESS)
        await when(self.plugin, lambda s: s["connection"] == "paused")

        state = await self.plugin.allow_reconnect()

        self.assertEqual(state["connection"], "waiting")
        await self.bluez.host_reconnects(self.device)
        self.assertEqual((await when(self.plugin, lambda s: s["connection"] == "connected"))["connection"], "connected")

    async def test_the_next_controller_mode_session_waits_for_paired_hosts_again(self):
        await self.plugin.disconnect_host(HOST_ADDRESS)
        await self.plugin.set_controller_mode(False)

        state = await self.plugin.set_controller_mode(True)

        self.assertEqual(state["connection"], "waiting")

    async def test_devices_that_are_not_paired_hosts_are_never_disconnected(self):
        headphones = self.bluez.device("4C:87:5D:98:4A:A4", "Headphones")
        headphones.update(connected=True, paired=True)
        await asyncio.sleep(0.05)

        state = await self.plugin.disconnect_host("4C:87:5D:98:4A:A4")

        self.assertEqual(self.bluez.disconnect_requests, [])
        self.assertTrue(headphones.connected)
        self.assertEqual(state["connection"], "connected")


class ForgettingAPairedHost(ConnectionsCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.plugin.set_controller_mode(True)
        self.device = await self.pair()
        await when(self.plugin, lambda s: s["connection"] == "connected")
        self.bluez.disconnect_requests.clear()

    async def test_forget_removes_the_pairing_from_the_deck(self):
        state = await self.plugin.forget_host(HOST_ADDRESS)

        self.assertEqual(state["hosts"], [])
        self.assertEqual(state["connection"], "idle")
        self.assertNotIn(self.device, self.bluez.devices)
        self.assertIsNone(self.bluez.advertisement)
        self.assertTrue(state["enabled"])

    async def test_a_forgotten_host_stays_forgotten_after_a_reload(self):
        await self.plugin.forget_host(HOST_ADDRESS)
        await self.plugin.set_controller_mode(False)

        await self.reload_plugin()

        self.assertEqual((await self.state())["hosts"], [])

    async def test_a_host_can_be_forgotten_while_controller_mode_is_off(self):
        await self.plugin.set_controller_mode(False)

        state = await self.plugin.forget_host(HOST_ADDRESS)

        self.assertEqual(state["hosts"], [])
        self.assertNotIn(self.device, self.bluez.devices)
        self.assertTrue(await self.bluez.wait_until_clean(), self.bluez.registrations())

    async def test_forgetting_one_host_keeps_the_others(self):
        other_address = "AA:BB:CC:DD:EE:01"
        await self.plugin.disconnect_host(HOST_ADDRESS)
        await self.pair(other_address, "living-room-pc")

        state = await self.plugin.forget_host(HOST_ADDRESS)

        self.assertEqual([h["address"] for h in state["hosts"]], [other_address])

    async def test_a_pairing_removed_in_steam_s_settings_drops_out_of_the_list(self):
        await self.bluez.remove_device(self.device)

        state = await when(self.plugin, lambda s: s["hosts"] == [])

        self.assertEqual(state["hosts"], [])

    async def test_a_pairing_removed_while_controller_mode_was_off_drops_out_of_the_list(self):
        await self.plugin.set_controller_mode(False)
        await self.bluez.remove_device(self.device)

        state = await self.plugin.set_controller_mode(True)

        self.assertEqual(state["hosts"], [])
        self.assertIsNone(self.bluez.advertisement)

    async def test_unloading_while_a_removal_is_being_checked_leaves_nothing_running(self):
        await self.bluez.remove_device(self.device)
        await asyncio.sleep(0.05)

        await self.plugin._unload()
        await asyncio.sleep(0)

        self.assertEqual(deckpad_work_in_progress(), [])

    async def test_the_deck_s_other_bluetooth_devices_are_never_removed(self):
        headphones = self.bluez.device("4C:87:5D:98:4A:A4", "Headphones")
        headphones.update(paired=True)

        await self.plugin.forget_host("4C:87:5D:98:4A:A4")
        await self.plugin.set_controller_mode(False)
        await self.plugin.forget_host("4C:87:5D:98:4A:A4")

        self.assertIn(headphones.path, self.bluez.devices)
        self.assertNotIn("RemoveDevice", [c[0] for c in self.bluez.calls])


class WithSeveralPairedHosts(ConnectionsCase):
    async def test_the_connected_host_is_listed_first(self):
        await self.plugin.set_controller_mode(True)
        first = await self.pair("AA:BB:CC:DD:EE:01", "living-room-pc")
        await self.plugin.disconnect_host("AA:BB:CC:DD:EE:01")
        await self.pair()

        state = await when(self.plugin, lambda s: s["connection"] == "connected")

        self.assertEqual(
            state["hosts"],
            [
                {"address": HOST_ADDRESS, "name": HOST_NAME, "connected": True},
                {"address": "AA:BB:CC:DD:EE:01", "name": "living-room-pc", "connected": False},
            ],
        )
        self.assertFalse(self.bluez.devices[first].connected)

    async def test_a_host_paired_while_another_is_connected_takes_over(self):
        await self.plugin.set_controller_mode(True)
        first = await self.pair("AA:BB:CC:DD:EE:01", "living-room-pc")
        await when(self.plugin, lambda s: s["connection"] == "connected")

        second = await self.pair()
        state = await when(self.plugin, lambda s: [h["connected"] for h in s["hosts"]] == [True, False])

        self.assertEqual(
            state["hosts"],
            [
                {"address": HOST_ADDRESS, "name": HOST_NAME, "connected": True},
                {"address": "AA:BB:CC:DD:EE:01", "name": "living-room-pc", "connected": False},
            ],
        )
        self.assertEqual(self.bluez.disconnect_requests, [first])
        self.assertTrue(self.bluez.devices[second].connected)


async def when(plugin, predicate, timeout=2.0):
    """The backend state once `predicate` holds for it, or the last state seen at the timeout."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        state = await plugin.get_state()
        if predicate(state) or loop.time() > deadline:
            return state
        await asyncio.sleep(0.01)


if __name__ == "__main__":
    unittest.main()
