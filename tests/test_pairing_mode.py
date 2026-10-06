"""Pairing Mode: a new Host finds the Deck in its normal Bluetooth settings and pairs with it as a controller,
while the QAM panel shows what is happening. Driven through the plugin backend, observed from BlueZ's side."""

import asyncio
import unittest
from unittest import mock

from deckpad import pairing

from tests.support.fake_bluez import HOST_ADDRESS, HOST_NAME
from tests.support.plugin_case import PluginTestCase

HID_SERVICE = "00001812-0000-1000-8000-00805f9b34fb"
GAMEPAD_APPEARANCE = 0x03C4


class EnteringPairingMode(PluginTestCase):
    async def test_controller_mode_alone_does_not_make_the_deck_discoverable(self):
        state = await self.plugin.set_controller_mode(True)

        self.assertEqual(state["pairing"]["status"], "closed")
        self.assertIsNone(self.bluez.advertisement)

    async def test_pairing_mode_makes_the_deck_discoverable_as_a_gamepad(self):
        await self.plugin.set_controller_mode(True)

        state = await self.plugin.set_pairing_mode(True)

        self.assertEqual(state["pairing"]["status"], "discoverable")
        self.assertEqual(state, await self.state())
        adv = self.bluez.advertisement
        self.assertEqual(adv["Type"], "peripheral")
        self.assertEqual(adv["ServiceUUIDs"], [HID_SERVICE])
        self.assertEqual(adv["Appearance"], GAMEPAD_APPEARANCE)
        self.assertTrue(adv["Discoverable"])

    async def test_the_panel_names_the_deck_as_the_host_will_list_it(self):
        await self.plugin.set_controller_mode(True)

        state = await self.plugin.set_pairing_mode(True)

        self.assertEqual(state["pairing"]["name"], "steamdeck")
        self.assertEqual(self.bluez.advertisement["LocalName"], "steamdeck")

    async def test_the_panel_shows_how_long_pairing_mode_stays_open(self):
        await self.plugin.set_controller_mode(True)

        state = await self.plugin.set_pairing_mode(True)

        self.assertGreater(state["pairing"]["seconds_left"], 60)

    async def test_pairing_mode_needs_controller_mode(self):
        state = await self.plugin.set_pairing_mode(True)

        self.assertEqual(state["pairing"]["status"], "closed")
        self.assertTrue(self.bluez.is_clean())

    async def test_asking_twice_keeps_one_advertisement(self):
        await self.plugin.set_controller_mode(True)
        await self.plugin.set_pairing_mode(True)

        await self.plugin.set_pairing_mode(True)

        self.assertEqual(len(self.bluez.advertisements), 1)


class FirstPairing(PluginTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.plugin.set_controller_mode(True)
        await self.plugin.set_pairing_mode(True)

    async def test_a_new_host_pairs_and_the_panel_shows_which_one(self):
        device = await self.bluez.host_connects()

        paired = await self.bluez.host_pairs(device)

        self.assertTrue(paired)
        state = await settled(self.plugin, "paired")
        self.assertEqual(state["pairing"]["status"], "paired")
        self.assertEqual(state["pairing"]["host"], {"address": HOST_ADDRESS, "name": HOST_NAME})
        self.assertIsNone(state["pairing"]["error"])

    async def test_the_panel_shows_the_hosts_name_once_bluetooth_learns_it(self):
        # bluetoothd only learns a new Host's name after the link is up; until then its Alias is the
        # address with dashes.
        device = await self.bluez.host_connects(name="38-F9-D3-C3-E9-69")
        await self.bluez.host_pairs(device)
        await settled(self.plugin, "paired")

        self.bluez.devices[device].update(alias=HOST_NAME)

        self.assertTrue(await eventually_async(self.plugin, lambda s: s["pairing"]["host"]["name"] == HOST_NAME))

    async def test_the_deck_stops_advertising_once_a_host_connects(self):
        await self.bluez.host_connects()

        state = await settled(self.plugin, "pairing")

        self.assertEqual(state["pairing"]["status"], "pairing")
        self.assertEqual(state["pairing"]["host"]["name"], HOST_NAME)
        self.assertTrue(await eventually(lambda: self.bluez.advertisement is None))


class PairingOutsidePairingMode(PluginTestCase):
    async def test_pairing_is_refused_once_pairing_mode_ends(self):
        await self.plugin.set_controller_mode(True)
        await self.plugin.set_pairing_mode(True)
        device = await self.bluez.host_connects()
        await self.plugin.set_pairing_mode(False)

        paired = await self.bluez.host_pairs(device)

        self.assertFalse(paired)
        self.assertEqual((await self.state())["pairing"]["status"], "closed")

    async def test_cancelling_pairing_mode_hides_the_deck_again(self):
        await self.plugin.set_controller_mode(True)
        await self.plugin.set_pairing_mode(True)

        state = await self.plugin.set_pairing_mode(False)

        self.assertEqual(state["pairing"]["status"], "closed")
        self.assertIsNone(self.bluez.advertisement)
        self.assertEqual(len(self.bluez.applications), 1)


class ServiceAuthorization(PluginTestCase):
    """bluetoothd asks the default agent before a paired but untrusted device may use a local service."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.plugin.set_controller_mode(True)

    async def test_a_device_that_is_not_a_paired_host_is_refused(self):
        stranger = self.bluez.device("4C:87:5D:98:4A:A4", "Someone's phone")
        stranger.update(paired=True)

        self.assertFalse(await self.bluez.device_uses_a_service(stranger.path))

    async def test_a_paired_host_is_allowed(self):
        await self.plugin.set_pairing_mode(True)
        device = await self.bluez.host_connects()
        await self.bluez.host_pairs(device)
        await settled(self.plugin, "paired")
        await self.plugin.set_pairing_mode(False)

        self.assertTrue(await self.bluez.device_uses_a_service(device))

    async def test_a_host_pairing_in_pairing_mode_is_allowed(self):
        await self.plugin.set_pairing_mode(True)
        device = await self.bluez.host_connects()

        self.assertTrue(await self.bluez.device_uses_a_service(device))


class PairingFailures(PluginTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.plugin.set_controller_mode(True)

    async def test_a_host_that_leaves_before_pairing_finishes_is_reported(self):
        await self.plugin.set_pairing_mode(True)
        device = await self.bluez.host_connects()
        await settled(self.plugin, "pairing")

        await self.bluez.host_disconnects(device)

        state = await settled(self.plugin, "failed")
        self.assertEqual(state["pairing"]["status"], "failed")
        self.assertEqual(state["pairing"]["error"]["code"], "pairing_failed")
        self.assertIn(HOST_NAME, state["pairing"]["error"]["message"])
        self.assertIsNone(self.bluez.advertisement)

    async def test_a_host_whose_name_is_unknown_is_called_the_other_device(self):
        # A Host with a stale bond fails encryption before bluetoothd ever learns its name.
        await self.plugin.set_pairing_mode(True)
        device = await self.bluez.host_connects(name="38-F9-D3-C3-E9-69")
        await settled(self.plugin, "pairing")

        await self.bluez.host_disconnects(device)

        state = await settled(self.plugin, "failed")
        self.assertIsNone(state["pairing"]["host"]["name"])
        self.assertIn("the other device", state["pairing"]["error"]["message"])
        self.assertNotIn("38-F9", state["pairing"]["error"]["message"])

    async def test_pairing_mode_times_out_with_an_explanation(self):
        with mock.patch.object(pairing, "TIMEOUT", 0.05):
            await self.plugin.set_pairing_mode(True)

            state = await settled(self.plugin, "failed")

        self.assertEqual(state["pairing"]["status"], "failed")
        self.assertEqual(state["pairing"]["error"]["code"], "pairing_timed_out")
        self.assertTrue(state["pairing"]["error"]["message"])
        self.assertTrue(await eventually(lambda: self.bluez.advertisement is None))

    async def test_after_a_timeout_pairing_is_refused(self):
        with mock.patch.object(pairing, "TIMEOUT", 0.05):
            await self.plugin.set_pairing_mode(True)
            device = await self.bluez.host_connects()
            await settled(self.plugin, "failed")

        self.assertFalse(await self.bluez.host_pairs(device))

    async def test_failing_to_advertise_is_reported(self):
        self.bluez.reject_advertisement = "Maximum advertisements reached"

        state = await self.plugin.set_pairing_mode(True)

        self.assertEqual(state["pairing"]["status"], "failed")
        self.assertEqual(state["pairing"]["error"]["code"], "advertising_failed")
        self.assertTrue(state["enabled"])

    async def test_trying_again_after_a_failure_clears_it(self):
        await self.plugin.set_pairing_mode(True)
        device = await self.bluez.host_connects()
        await settled(self.plugin, "pairing")
        await self.bluez.host_disconnects(device)
        await settled(self.plugin, "failed")

        state = await self.plugin.set_pairing_mode(True)

        self.assertEqual(state["pairing"]["status"], "discoverable")
        self.assertIsNone(state["pairing"]["error"])
        self.assertIsNotNone(self.bluez.advertisement)


class PairingModeAndControllerMode(PluginTestCase):
    async def test_turning_controller_mode_off_ends_pairing_mode_cleanly(self):
        await self.plugin.set_controller_mode(True)
        await self.plugin.set_pairing_mode(True)

        state = await self.plugin.set_controller_mode(False)

        self.assertEqual(state["pairing"]["status"], "closed")
        self.assertTrue(self.bluez.is_clean(), self.bluez.registrations())

    async def test_unloading_during_pairing_mode_withdraws_the_advertisement(self):
        await self.plugin.set_controller_mode(True)
        await self.plugin.set_pairing_mode(True)

        await self.plugin._unload()

        self.assertTrue(await self.bluez.wait_until_clean(), self.bluez.registrations())

    async def test_the_panel_is_told_about_every_pairing_step(self):
        await self.plugin.set_controller_mode(True)
        await self.plugin.set_pairing_mode(True)
        device = await self.bluez.host_connects()
        await self.bluez.host_pairs(device)
        await settled(self.plugin, "paired")
        await asyncio.sleep(0.05)

        statuses = [args[0]["pairing"]["status"] for event, *args in self.decky.events if event == "controller_mode_state"]
        deduplicated = [s for i, s in enumerate(statuses) if i == 0 or statuses[i - 1] != s]
        self.assertEqual(deduplicated, ["closed", "discoverable", "pairing", "paired"])


class LeavingWithAPairedHostConnected(PluginTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.plugin.set_controller_mode(True)
        await self.plugin.set_pairing_mode(True)
        self.device = await self.bluez.host_connects()
        await self.bluez.host_pairs(self.device)
        await settled(self.plugin, "paired")

    async def test_turning_off_disconnects_the_host_before_removing_the_controller(self):
        await self.plugin.set_controller_mode(False)

        self.assertEqual(self.bluez.disconnect_requests, [self.device])
        calls = [c[0] for c in self.bluez.calls]
        self.assertLess(calls.index("Disconnect"), calls.index("UnregisterApplication"))
        self.assertTrue(self.bluez.is_clean(), self.bluez.registrations())

    async def test_unloading_disconnects_the_host_without_the_event_loop(self):
        unload = self.plugin._unload()
        with self.assertRaises(StopIteration):
            unload.send(None)

        self.assertTrue(await eventually(lambda: self.bluez.disconnect_requests == [self.device]))
        self.assertTrue(await self.bluez.wait_until_clean(), self.bluez.registrations())

    async def test_a_host_that_already_left_is_not_disconnected_again(self):
        await self.bluez.host_disconnects(self.device)
        await asyncio.sleep(0.05)

        await self.plugin.set_controller_mode(False)

        self.assertEqual(self.bluez.disconnect_requests, [])

    async def test_devices_that_never_used_deckpad_are_left_alone(self):
        headphones = self.bluez.device("4C:87:5D:98:4A:A4", "Headphones")
        headphones.update(connected=True)
        await asyncio.sleep(0.05)

        await self.plugin.set_controller_mode(False)

        self.assertNotIn(headphones.path, self.bluez.disconnect_requests)


class APairedHostInALaterSession(PluginTestCase):
    """A Paired Host reconnects with its cached GATT database: it reads nothing and never meets the agent."""

    async def pair_then_restart(self, reload_plugin):
        await self.plugin.set_controller_mode(True)
        await self.plugin.set_pairing_mode(True)
        device = await self.bluez.host_connects()
        await self.bluez.host_pairs(device)
        await settled(self.plugin, "paired")
        await self.plugin.set_controller_mode(False)
        self.bluez.disconnect_requests.clear()
        if reload_plugin:
            await self.plugin._unload()
            self.plugin = self.main.Plugin()
            await self.plugin._main()
        await self.plugin.set_controller_mode(True)
        await self.plugin.set_pairing_mode(True)
        await self.bluez.host_connects()
        await asyncio.sleep(0.05)
        return device

    async def test_is_disconnected_when_controller_mode_turns_off(self):
        device = await self.pair_then_restart(reload_plugin=False)

        await self.plugin.set_controller_mode(False)

        self.assertEqual(self.bluez.disconnect_requests, [device])

    async def test_is_remembered_across_a_plugin_reload(self):
        device = await self.pair_then_restart(reload_plugin=True)

        unload = self.plugin._unload()
        with self.assertRaises(StopIteration):
            unload.send(None)

        self.assertTrue(await eventually(lambda: self.bluez.disconnect_requests == [device]))


async def settled(plugin, status, timeout=2.0):
    """The backend state once Pairing Mode reaches `status` (Bluetooth events arrive asynchronously)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        state = await plugin.get_state()
        if state["pairing"]["status"] == status or loop.time() > deadline:
            return state
        await asyncio.sleep(0.01)


async def eventually_async(plugin, predicate, timeout=2.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate(await plugin.get_state()) and loop.time() < deadline:
        await asyncio.sleep(0.01)
    return predicate(await plugin.get_state())


async def eventually(predicate, timeout=2.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate() and loop.time() < deadline:
        await asyncio.sleep(0.01)
    return predicate()


if __name__ == "__main__":
    unittest.main()
