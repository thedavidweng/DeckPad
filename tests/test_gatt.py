"""ATT permissions, offsets, writes, and notification state for DeckPad's actual GATT application."""

import unittest

from dbus_fast import Variant
from dbus_fast.errors import DBusError
from deckpad.peripheral import build_application


def invoke(obj, member, *args):
    return getattr(obj, member).__wrapped__(obj, *args)


class GattRequests(unittest.TestCase):
    def setUp(self):
        self.hosts = []
        self.app = build_application(self.hosts.append)
        self.chars = self.app.services[0].characteristics
        self.options = {"device": Variant("o", "/org/bluez/hci0/dev_AA")}

    def test_read_offsets_are_exact(self):
        char = self.chars[0]
        self.assertEqual(invoke(char, "ReadValue", {"offset": Variant("q", 1)}), b"\x01\x00\x02")
        self.assertEqual(invoke(char, "ReadValue", {"offset": Variant("q", 4)}), b"")

    def test_invalid_read_offsets_are_rejected_before_claiming_a_host(self):
        for offset in (Variant("q", 5), Variant("i", -1), Variant("s", "0")):
            with self.subTest(offset=offset), self.assertRaises(DBusError):
                invoke(self.chars[0], "ReadValue", dict(self.options, offset=offset))
        self.assertEqual(self.hosts, [])

    def test_descriptor_offsets_are_validated(self):
        descriptor = self.app.gamepad_input.descriptors[0]
        self.assertEqual(invoke(descriptor, "ReadValue", {"offset": Variant("q", 1)}), b"\x01")
        with self.assertRaises(DBusError):
            invoke(descriptor, "ReadValue", {"offset": Variant("q", 3)})

    def test_permissions_are_enforced(self):
        with self.assertRaises(DBusError):
            invoke(self.chars[2], "ReadValue", {})
        with self.assertRaises(DBusError):
            invoke(self.app.gamepad_input, "WriteValue", bytes(16), {})
        with self.assertRaises(DBusError):
            invoke(self.chars[0], "StartNotify")
        self.assertFalse(self.chars[0].notifying)

    def test_invalid_writes_are_rejected_before_claiming_a_host(self):
        for char, value, options in (
            (self.chars[2], b"", self.options),
            (self.chars[2], b"\x02", self.options),
            (self.chars[2], b"\x01", dict(self.options, offset=Variant("q", 1))),
            (self.chars[3], b"\x00", self.options),
            (self.chars[5], bytes(7), self.options),
            (self.chars[5], bytes(9), self.options),
        ):
            with self.subTest(value=value, uuid=char.UUID), self.assertRaises(DBusError):
                invoke(char, "WriteValue", value, options)
        self.assertEqual(self.hosts, [])

    def test_valid_hid_writes_keep_the_report_protocol_and_claim_the_host(self):
        for char, value in ((self.chars[2], b"\x00"), (self.chars[2], b"\x01"),
                            (self.chars[3], b"\x01"), (self.chars[5], bytes(8))):
            invoke(char, "WriteValue", value, self.options)
        self.assertEqual(invoke(self.chars[3], "ReadValue", {}), b"\x01")
        self.assertEqual(set(self.hosts), {"/org/bluez/hci0/dev_AA"})

    def test_subscription_changes_are_idempotent(self):
        char = self.app.gamepad_input
        invoke(char, "StartNotify")
        invoke(char, "StartNotify")
        self.assertTrue(char.notifying)
        invoke(char, "StopNotify")
        invoke(char, "StopNotify")
        self.assertFalse(char.notifying)
