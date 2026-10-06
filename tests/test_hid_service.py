"""What a Host finds when it discovers the Deck's GATT services while Controller Mode is on (ADR-0001, ADR-0002)."""

import unittest

from tests.support.plugin_case import PluginTestCase

# XboxOneS_1914_HIDDescriptor from ESP32-BLE-CompositeHID's XboxDescriptors.h (MIT), report IDs expanded.
XBOX_1914_REPORT_MAP = bytes.fromhex(
    "05010905a10185010901a10009300931150027ffff0000950275108102c00901a10009320935150027ffff0000950275108102"
    "c0050209c5150026ff039501750a810215002500750695018103050209c4150026ff039501750a810215002500750695018103"
    "05010939150125083500463b016614007504950181427504950115002500350045006500810305091901290f150025017501"
    "950f810215002500750195018103050c0ab2001500250195017501810215002500750795018103050f09218503a102099715"
    "002501750495019102150025007504950191030970150025647508950491020950660110550e150026ff0075089501910209"
    "a7150026ff0075089501910265005500097c150026ff00750895019102c0c0"
)


class AHostDiscoveringTheDeck(PluginTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.plugin.set_controller_mode(True)

    async def test_the_report_map_is_the_xbox_1914_descriptor(self):
        self.assertEqual(await self.bluez.host_reads("2a4b"), XBOX_1914_REPORT_MAP)

    async def test_the_host_reads_hid_information_and_report_protocol(self):
        self.assertEqual(await self.bluez.host_reads("2a4a"), bytes.fromhex("11010002"))
        self.assertEqual(await self.bluez.host_reads("2a4e"), b"\x01")

    async def test_the_gamepad_input_report_starts_at_rest(self):
        reports = self.bluez.gatt_objects("org.bluez.GattCharacteristic1", "2a4d")
        input_index = next(
            i for i in range(len(reports)) if "notify" in reports[i][1]["Flags"]
        )

        reference = await self.bluez.host_reads("2a4d", input_index, descriptor="2908")
        value = await self.bluez.host_reads("2a4d", input_index)

        self.assertEqual(reference, bytes.fromhex("0101"))
        # Sticks centred, triggers released, hat neutral, no buttons.
        self.assertEqual(value, bytes.fromhex("0080008000800080 0000 0000 00 00 00 00".replace(" ", "")))

    async def test_the_rumble_output_report_is_writable(self):
        reports = self.bluez.gatt_objects("org.bluez.GattCharacteristic1", "2a4d")
        output_index = next(i for i in range(len(reports)) if "encrypt-write" in reports[i][1]["Flags"])

        reference = await self.bluez.host_reads("2a4d", output_index, descriptor="2908")

        self.assertEqual(reference, bytes.fromhex("0302"))
        self.assertIn("write-without-response", reports[output_index][1]["Flags"])

    async def test_hid_reads_require_an_encrypted_link(self):
        for uuid in ("2a4a", "2a4b", "2a4d"):
            for _path, props in self.bluez.gatt_objects("org.bluez.GattCharacteristic1", uuid):
                self.assertIn("encrypt-read", props["Flags"], uuid)

    async def test_the_host_finds_the_controller_identity_and_a_battery(self):
        self.assertEqual(await self.bluez.host_reads("2a50"), bytes.fromhex("025e04130b0905"))
        self.assertEqual(len(await self.bluez.host_reads("2a19")), 1)

    async def test_the_hid_service_is_advertised_as_a_primary_service(self):
        services = self.bluez.gatt_objects("org.bluez.GattService1", "1812")

        self.assertEqual(len(services), 1)
        self.assertTrue(services[0][1]["Primary"])


if __name__ == "__main__":
    unittest.main()
