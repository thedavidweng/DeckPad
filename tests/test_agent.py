"""DeckPad accepts Just Works, never unseen confirmation or unrelated services."""

import unittest
from unittest.mock import Mock

from dbus_fast.errors import DBusError
from deckpad.agent import PairingAgent
from deckpad.gatt import uuid16
from deckpad.peripheral import build_application


class AgentAuthorization(unittest.TestCase):
    def setUp(self):
        self.pairing = Mock(return_value=True)
        self.service = Mock(return_value=True)
        self.agent = PairingAgent(self.pairing, self.service, [s.UUID for s in build_application().services])
        self.device = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"

    def invoke(self, member, *args):
        return getattr(self.agent, member).__wrapped__(self.agent, *args)

    def test_just_works_requires_the_pairing_decision(self):
        self.invoke("RequestAuthorization", self.device)
        self.pairing.assert_called_once_with(self.device)
        self.pairing.return_value = False
        with self.assertRaises(DBusError):
            self.invoke("RequestAuthorization", self.device)

    def test_unseen_numeric_confirmation_and_passkey_are_rejected(self):
        for member, args in (("RequestConfirmation", (123456,)),
                             ("DisplayPasskey", (123456, 0))):
            with self.subTest(member=member), self.assertRaises(DBusError):
                self.invoke(member, self.device, *args)
        self.pairing.assert_not_called()

    def test_only_deckpad_services_reach_the_device_decision(self):
        for short in ("1812", "180f", "180a"):
            self.invoke("AuthorizeService", self.device, uuid16(short))
        with self.assertRaises(DBusError):
            self.invoke("AuthorizeService", self.device, uuid16("110b"))
        self.assertEqual(self.service.call_count, 3)
        self.service.return_value = False
        with self.assertRaises(DBusError):
            self.invoke("AuthorizeService", self.device, uuid16("1812"))
