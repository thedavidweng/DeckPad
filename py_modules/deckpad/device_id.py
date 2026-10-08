"""Make bluetoothd's own Device Information Service report the Xbox controller's IDs, reversibly.

bluetoothd always publishes a DIS with its DeviceID (BlueZ's 1D6B:0246) at lower GATT handles than
DeckPad's, and hosts such as Linux use the first DIS they find. bluetoothd builds that PnP ID value
from its `btd_opts.did_*` globals on every read, and nothing else reads them after startup (the SDP
record, EIR, and Modalias are built once). So, as root, DeckPad rewrites those four u16s in the
running bluetoothd's data segment while controller mode is on and writes BlueZ's values back when it
stops. No file is changed and bluetoothd is not restarted.

Every step refuses rather than guesses: the original values must match the adapter's Modalias, occur
exactly once in bluetoothd's own writable image mapping, and still be ours when restored.
"""

import logging
import os
import re
import struct

log = logging.getLogger("deckpad.device_id")

_MODALIAS = re.compile(r"^(usb|bluetooth):v([0-9A-Fa-f]{4})p([0-9A-Fa-f]{4})d([0-9A-Fa-f]{4})$")
_SOURCES = {"bluetooth": 0x0001, "usb": 0x0002}


def parse_modalias(modalias):
    """(source, vendor, product, version) from an Adapter1 Modalias such as `usb:v1D6Bp0246d0553`."""
    match = _MODALIAS.match(modalias or "")
    if not match:
        return None
    return (_SOURCES[match.group(1)],) + tuple(int(g, 16) for g in match.groups()[1:])


def _pack(device_id):
    return struct.pack("<HHHH", *device_id)


class Override:
    def __init__(self, process, address, original, replacement):
        self._process = process
        self._address = address
        self._original = original
        self._replacement = replacement

    def restore(self):
        """Write BlueZ's DeviceID back, unless bluetoothd restarted or something else changed it since."""
        try:
            if _Process.current(self._process.proc, self._process.pid) != self._process:
                log.info("bluetoothd restarted; its DeviceID is already its own")
                return
            with open(self._process.mem_path, "r+b", buffering=0) as mem:
                mem.seek(self._address)
                if mem.read(len(self._replacement)) != self._replacement:
                    return
                mem.seek(self._address)
                mem.write(self._original)
            log.info("Restored bluetoothd's DeviceID")
        except OSError as e:
            log.warning("Could not restore bluetoothd's DeviceID: %r", e)


class _Process:
    def __init__(self, proc, pid, exe, start_time):
        self.proc = proc
        self.pid = pid
        self.exe = exe
        self.start_time = start_time

    @property
    def mem_path(self):
        return os.path.join(self.proc, str(self.pid), "mem")

    def __eq__(self, other):
        return isinstance(other, _Process) and (self.pid, self.exe, self.start_time) == (
            other.pid,
            other.exe,
            other.start_time,
        )

    @classmethod
    def current(cls, proc, pid):
        base = os.path.join(proc, str(pid))
        try:
            exe = os.readlink(os.path.join(base, "exe"))
            with open(os.path.join(base, "stat")) as f:
                # Field 22 (starttime) tells a restarted process with a reused pid apart.
                start_time = f.read().rsplit(")", 1)[1].split()[19]
        except (OSError, IndexError):
            return None
        return cls(proc, pid, exe, start_time)

    def image_data_segments(self):
        with open(os.path.join(self.proc, str(self.pid), "maps")) as f:
            for line in f:
                fields = line.split(None, 5)
                if len(fields) == 6 and "w" in fields[1] and fields[5].strip() == self.exe:
                    start, end = (int(x, 16) for x in fields[0].split("-"))
                    yield start, end


def _scan(pid, modalias, replacement, proc):
    """Locate bluetoothd's DeviceID: (process, original, new, addresses of each), or None if not possible."""
    original_id = parse_modalias(modalias)
    if original_id is None:
        log.info("Leaving bluetoothd's DeviceID alone: unrecognised Modalias %r", modalias)
        return None
    original = _pack(original_id)
    new = _pack(replacement)
    process = _Process.current(proc, pid)
    if process is None:
        log.info("Leaving bluetoothd's DeviceID alone: process %s is not accessible", pid)
        return None
    found = {original: [], new: []}
    try:
        with open(process.mem_path, "rb", buffering=0) as mem:
            for start, end in process.image_data_segments():
                mem.seek(start)
                data = mem.read(end - start)
                for pattern in found:
                    found[pattern].extend(start + m.start() for m in re.finditer(re.escape(pattern), data))
    except OSError as e:
        log.info("Leaving bluetoothd's DeviceID alone: %r", e)
        return None
    return process, original, new, found[original], found[new]


def override(pid, modalias, replacement, proc="/proc"):
    """Rewrite the running bluetoothd's DeviceID to `replacement`; return an Override to undo it, or None.

    If a previous session died with the override in place, it is adopted so it can be restored.
    """
    scan = _scan(pid, modalias, replacement, proc)
    if scan is None:
        return None
    process, original, new, originals, replacements = scan
    if len(originals) == 1 and not replacements:
        address = originals[0]
        try:
            with open(process.mem_path, "r+b", buffering=0) as mem:
                mem.seek(address)
                mem.write(new)
        except OSError as e:
            log.info("Could not override bluetoothd's DeviceID: %r", e)
            return None
        log.info("bluetoothd's DIS now reports %04X:%04X", replacement[1], replacement[2])
    elif len(replacements) == 1 and not originals:
        address = replacements[0]
        log.info("Adopted a DeviceID override left by a previous session")
    else:
        log.info(
            "Leaving bluetoothd's DeviceID alone: found %d copies of it (expected exactly one)", len(originals)
        )
        return None
    return Override(process, address, original, new)


def restore_leftover(pid, modalias, replacement, proc="/proc"):
    """Undo an override that a killed plugin process left in bluetoothd. Returns True if one was undone."""
    scan = _scan(pid, modalias, replacement, proc)
    if scan is None:
        return False
    process, original, new, originals, replacements = scan
    if len(replacements) != 1 or originals:
        return False
    Override(process, replacements[0], original, new).restore()
    return True


def current(pid, modalias, replacement, proc="/proc"):
    """Which DeviceID bluetoothd reports right now: "controller_identity", "bluez", or None if unknown."""
    scan = _scan(pid, modalias, replacement, proc)
    if scan is None:
        return None
    _process, _original, _new, originals, replacements = scan
    if len(replacements) == 1 and not originals:
        return "controller_identity"
    if len(originals) == 1 and not replacements:
        return "bluez"
    return None
