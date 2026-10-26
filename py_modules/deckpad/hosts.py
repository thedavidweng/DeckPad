"""The hosts that paired through DeckPad.

bluetoothd's bond list also holds the user's headphones, keyboards and other peripherals, so DeckPad
keeps its own list of the bonds it made. It never lists, disconnects or removes any other device.
"""

import dataclasses
import json
import logging
import os
import re

from . import storage

log = logging.getLogger("deckpad.hosts")


@dataclasses.dataclass(frozen=True)
class Host:
    address: str
    # None while bluetoothd only knows the address.
    name: "str | None" = None

    def __post_init__(self):
        if not isinstance(self.address, str) or not re.fullmatch(r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}", self.address):
            raise ValueError("Invalid Bluetooth Host address")
        if self.name is not None and not isinstance(self.name, str):
            raise ValueError("Host name must be a string or null")
        object.__setattr__(self, "address", self.address.upper())

    @classmethod
    def from_device(cls, device):
        return cls(device.get("Address"), display_name(device))

    def to_dict(self):
        return {"address": self.address, "name": self.name}


def display_name(device):
    """The name a person would recognise for a Device1, or None while bluetoothd only knows its address."""
    address = device.get("Address")
    name = device.get("Alias") or device.get("Name")
    if not name or (address and name == address.replace(":", "-")):
        # bluetoothd's placeholder Alias for a device whose name it has not learned.
        return None
    return name


class PairedHosts:
    def __init__(self, path=None):
        self._path = path
        self._hosts = {}
        if path and os.path.exists(path):
            try:
                with open(path) as f:
                    hosts = [Host(h["address"], h["name"]) for h in json.load(f)["hosts"]]
                self._hosts = {host.address: host for host in hosts}
            except (OSError, ValueError, KeyError, TypeError) as e:
                log.warning("Ignoring unreadable Paired Host list %s: %r", path, e)

    def __contains__(self, address):
        return address in self._hosts

    def all(self):
        return list(self._hosts.values())

    def name(self, address):
        host = self._hosts.get(address)
        return host.name if host else None

    def add(self, host):
        self._hosts[host.address] = host
        self._save()

    def rename(self, address, name):
        """Returns whether anything changed."""
        host = self._hosts.get(address)
        if host is None or not name or host.name == name:
            return False
        self._hosts[address] = dataclasses.replace(host, name=name)
        self._save()
        return True

    def remove(self, address):
        if self._hosts.pop(address, None) is not None:
            self._save()

    def erase(self):
        self._hosts = {}
        if self._path:
            storage.erase(self._path)

    def _save(self):
        if not self._path:
            return
        try:
            storage.save(self._path, {"hosts": [h.to_dict() for h in self.all()]})
        except OSError as e:
            log.warning("Could not save the Paired Host list: %r", e)
