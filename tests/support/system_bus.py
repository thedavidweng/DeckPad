"""A private dbus-daemon that stands in for the system bus during tests."""

import os
import subprocess
import tempfile

_CONFIG = """<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <listen>unix:dir={dir}</listen>
  <auth>EXTERNAL</auth>
  <policy context="default">
    <allow send_destination="*" eavesdrop="true"/>
    <allow eavesdrop="true"/>
    <allow own="*"/>
  </policy>
</busconfig>
"""


class PrivateSystemBus:
    def __init__(self):
        self._dir = tempfile.TemporaryDirectory(prefix="deckpad-bus-")
        self._proc = None
        self.address = None
        self._previous = None

    def start(self):
        config = os.path.join(self._dir.name, "bus.conf")
        with open(config, "w") as f:
            f.write(_CONFIG.format(dir=self._dir.name))
        self._proc = subprocess.Popen(
            ["dbus-daemon", "--config-file", config, "--nofork", "--print-address=1"],
            stdout=subprocess.PIPE,
            text=True,
        )
        self.address = self._proc.stdout.readline().strip()
        if not self.address:
            raise RuntimeError("dbus-daemon did not start")
        self._previous = os.environ.get("DBUS_SYSTEM_BUS_ADDRESS")
        os.environ["DBUS_SYSTEM_BUS_ADDRESS"] = self.address

    def stop(self):
        if self._previous is None:
            os.environ.pop("DBUS_SYSTEM_BUS_ADDRESS", None)
        else:
            os.environ["DBUS_SYSTEM_BUS_ADDRESS"] = self._previous
        if self._proc:
            self._proc.terminate()
            self._proc.wait(timeout=5)
            self._proc.stdout.close()
        self._dir.cleanup()
