"""The Hosts that paired through DeckPad, remembered across sessions and plugin reloads.

bluetoothd's bond list also holds the user's headphones, keyboards and other peripherals, so DeckPad
keeps its own record of which bonds are Paired Hosts. Only these are ever listed, disconnected or
forgotten by DeckPad.
"""

import json
import logging
import os

log = logging.getLogger("deckpad.hosts")


def display_name(device):
    """The name a person would recognise for a Device1, or None while bluetoothd only knows its address."""
    address = device.get("Address")
    name = device.get("Alias") or device.get("Name")
    if not name or (address and name == address.replace(":", "-")):
        return None
    return name


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

    def rename(self, address, name):
        """Record a Paired Host's new name. Returns whether anything changed."""
        host = self._hosts.get(address)
        if host is None or not name or host["name"] == name:
            return False
        host["name"] = name
        self._save()
        return True

    def remove(self, address):
        if self._hosts.pop(address, None) is not None:
            self._save()

    def erase(self):
        """Forget every Paired Host and delete the record's file."""
        self._hosts = {}
        if self._path:
            for path in (self._path, self._path + ".tmp"):
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
                except OSError as e:
                    log.warning("Could not delete %s: %r", path, e)

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
