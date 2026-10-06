"""The Hosts that paired through DeckPad, remembered across sessions and plugin reloads.

bluetoothd's bond list also holds the user's headphones, keyboards and other peripherals, so DeckPad
keeps its own record of which bonds are Paired Hosts. Only these are ever disconnected (or, later,
listed and forgotten) by DeckPad.
"""

import json
import logging
import os

log = logging.getLogger("deckpad.hosts")


class PairedHosts:
    def __init__(self, path=None):
        self._path = path
        self._hosts = {}
        if path and os.path.exists(path):
            try:
                with open(path) as f:
                    self._hosts = {h["address"]: h for h in json.load(f)["hosts"]}
            except (OSError, ValueError, KeyError, TypeError) as e:
                log.warning("Ignoring unreadable Paired Host list %s: %r", path, e)

    def __contains__(self, address):
        return address in self._hosts

    def all(self):
        return [dict(h) for h in self._hosts.values()]

    def add(self, address, name):
        self._hosts[address] = {"address": address, "name": name}
        self._save()

    def _save(self):
        if not self._path:
            return
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"hosts": self.all()}, f, indent=2)
            os.replace(tmp, self._path)
        except OSError as e:
            log.warning("Could not save the Paired Host list: %r", e)
