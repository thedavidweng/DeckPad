"""Uninstalling DeckPad from Decky's settings: Decky calls `_unload` and then `_uninstall` in the plugin
process, with the plugin's event loop starved (see test_controller_mode), and deletes the plugin
directory afterwards. Observed from BlueZ's side and in the plugin's directories."""

import asyncio
import os
import unittest

from tests.support.fake_bluez import HOST_ADDRESS
from tests.support.plugin_case import PluginTestCase
from tests.test_connections import ConnectionsCase, when

OTHER_HOST = "AA:BB:CC:DD:EE:01"
HEADPHONES = "4C:87:5D:98:4A:A4"


def completes_without_the_event_loop(coro):
    """Run a coroutine as Decky's starved loop would: one step, and it must finish in that step."""
    try:
        coro.send(None)
    except StopIteration:
        return True
    coro.close()
    return False


class UninstallingDeckPad(ConnectionsCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.plugin.set_controller_mode(True)
        self.other = await self.pair(OTHER_HOST, "living-room-pc")
        await self.plugin.disconnect_host(OTHER_HOST)
        self.host = await self.pair()
        await when(self.plugin, lambda s: s["connection"] == "connected")
        self.headphones = self.bluez.device(HEADPHONES, "Headphones")
        self.headphones.update(paired=True, connected=True)
        await self.plugin.get_diagnostics()

    async def uninstall(self):
        await self.plugin._unload()
        # The fake BlueZ needs this test's loop, so the plugin's starved loop is played by another thread.
        return await asyncio.to_thread(completes_without_the_event_loop, self.plugin._uninstall())

    async def test_it_finishes_without_the_event_loop(self):
        self.assertTrue(await self.uninstall())

    async def test_it_removes_the_pairings_of_paired_hosts(self):
        await self.uninstall()

        self.assertNotIn(self.host, self.bluez.devices)
        self.assertNotIn(self.other, self.bluez.devices)

    async def test_it_leaves_the_deck_s_other_bluetooth_devices_alone(self):
        await self.uninstall()

        self.assertIn(self.headphones.path, self.bluez.devices)
        self.assertTrue(self.headphones.connected)
        self.assertNotIn(("RemoveDevice", self.headphones.path), self.bluez.calls)

    async def test_it_deletes_deckpad_s_files(self):
        # Left by a killed run; restoring it needs root, which the tests do not have.
        interval_state = os.path.join(self.decky.DECKY_PLUGIN_RUNTIME_DIR, "connection_interval.json")
        os.makedirs(self.decky.DECKY_PLUGIN_RUNTIME_DIR, exist_ok=True)
        with open(interval_state, "w") as f:
            f.write('{"index": 0, "min": 24, "max": 40}')
        await self.plugin.set_quit_combo(False)

        await self.uninstall()

        self.assertFalse(os.path.exists(interval_state))
        self.assertFalse(os.path.exists(os.path.join(self.decky.DECKY_PLUGIN_SETTINGS_DIR, "paired_hosts.json")))
        self.assertFalse(os.path.exists(os.path.join(self.decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")))
        self.assertFalse(os.path.exists(os.path.join(self.decky.DECKY_PLUGIN_LOG_DIR, "diagnostics.txt")))

    async def test_it_leaves_bluetooth_as_it_was_before_deckpad(self):
        await self.uninstall()

        self.assertTrue(await self.bluez.wait_until_clean(), self.bluez.registrations())


class UninstallingWithoutBluetooth(PluginTestCase):
    async def test_it_still_finishes_and_deletes_deckpad_s_files(self):
        await self.plugin.set_controller_mode(True)
        await self.plugin.set_pairing_mode(True)
        device = await self.bluez.host_connects()
        await self.bluez.host_pairs(device)
        await self.plugin._unload()
        # Unload sends Disconnect without waiting; let the fake answer it before it leaves the bus.
        await asyncio.sleep(0.02)
        await self.bluez.stop_service()

        finished = await asyncio.to_thread(completes_without_the_event_loop, self.plugin._uninstall())

        self.assertTrue(finished)
        self.assertFalse(os.path.exists(os.path.join(self.decky.DECKY_PLUGIN_SETTINGS_DIR, "paired_hosts.json")))
        self.assertEqual(HOST_ADDRESS, self.bluez.devices[device].address)


if __name__ == "__main__":
    unittest.main()
