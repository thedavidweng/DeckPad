"""Only valid Bluetooth identities enter DeckPad's Paired Host record."""

import json
import tempfile
import unittest
from pathlib import Path

from deckpad.hosts import Host, PairedHosts


class HostIdentity(unittest.TestCase):
    def test_addresses_are_validated_and_canonicalized(self):
        self.assertEqual(Host("aa:bb:cc:dd:ee:ff").address, "AA:BB:CC:DD:EE:FF")
        for address in (None, "", "AA:BB:CC:DD:EE", "AA:BB:CC:DD:EE:GG", " AA:BB:CC:DD:EE:FF", 42):
            with self.subTest(address=address), self.assertRaises(ValueError):
                Host(address)
        with self.assertRaises(ValueError):
            Host("AA:BB:CC:DD:EE:FF", name=123)

    def test_one_invalid_record_does_not_partially_load_the_host_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paired_hosts.json"
            path.write_text(json.dumps({"hosts": [
                {"address": "AA:BB:CC:DD:EE:FF", "name": "Host"},
                {"address": "invalid", "name": "Other Host"},
            ]}))
            self.assertEqual(PairedHosts(str(path)).all(), [])

    def test_valid_addresses_and_names_survive_reload_without_connection_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paired_hosts.json"
            hosts = PairedHosts(str(path))
            host = Host("AA:BB:CC:DD:EE:FF", "Host")
            hosts.add(host)
            self.assertEqual(PairedHosts(str(path)).all(), [host])
            self.assertEqual(json.loads(path.read_text()), {"hosts": [host.to_dict()]})
