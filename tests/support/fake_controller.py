"""The Deck's built-in controller as DeckPad finds it: a sysfs hidraw class directory plus a device node.

The layout mirrors the real Deck. Three hidraw interfaces share the Valve VID/PID 28DE:1205; the lizard
keyboard and mouse have an `input/` child, and only the raw controller interface (hidraw2) does not.
The node is a FIFO that the test writes Deck State Reports into.
"""

import os
import shutil
import tempfile

VALVE_CONTROLLER = "0003:000028DE:00001205"


class FakeController:
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="deckpad-hidraw-")
        self.hidraw_class = os.path.join(self.root, "sys", "class", "hidraw")
        self.dev_dir = os.path.join(self.root, "dev")
        os.makedirs(self.hidraw_class)
        os.makedirs(self.dev_dir)
        self._writer = None
        self._add_interface("hidraw0", VALVE_CONTROLLER, has_input=True)
        self._add_interface("hidraw1", "0018:00002808:00001015", has_input=True)
        self._add_interface("hidraw3", VALVE_CONTROLLER, has_input=True)
        self.node = os.path.join(self.dev_dir, "hidraw2")

    def _add_interface(self, name, hid_id, has_input):
        device = os.path.join(self.hidraw_class, name, "device")
        os.makedirs(device)
        with open(os.path.join(device, "uevent"), "w") as f:
            f.write("DRIVER=hid-steam\nHID_ID=%s\nHID_NAME=Valve Software Steam Deck Controller\n" % hid_id)
        if has_input:
            os.makedirs(os.path.join(device, "input", "input5"))
            # A plain file stands in for nodes that DeckPad must never open.
            open(os.path.join(self.dev_dir, name), "wb").close()

    def plug_in(self):
        """The raw controller interface appears (as it does at boot or after the controller resets)."""
        self._add_interface("hidraw2", VALVE_CONTROLLER, has_input=False)
        os.mkfifo(self.node)
        # Read-write, so writing never blocks for want of a reader and DeckPad never sees end-of-file.
        self._writer = os.open(self.node, os.O_RDWR | os.O_NONBLOCK)

    def send(self, report):
        os.write(self._writer, report)

    def opened_nodes(self):
        """Device nodes this process has open, not counting the fake's own writer."""
        opened = set()
        for fd in os.listdir("/proc/self/fd"):
            if self._writer is not None and int(fd) == self._writer:
                continue
            try:
                target = os.readlink(os.path.join("/proc/self/fd", fd))
            except OSError:
                continue
            if target.startswith(self.dev_dir + os.sep):
                opened.add(target)
        return opened

    def is_open(self):
        """Whether DeckPad has the controller node open."""
        return self.node in self.opened_nodes()

    def cleanup(self):
        if self._writer is not None:
            os.close(self._writer)
            self._writer = None
        shutil.rmtree(self.root, ignore_errors=True)
