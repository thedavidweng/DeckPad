"""bluetoothd's own Device Information Service reports the Xbox identity while controller mode is on,
and BlueZ's identity again afterwards. Exercised against a stand-in for bluetoothd's /proc entry."""

import os
import struct
import tempfile
import unittest

from deckpad import device_id

BLUEZ_MODALIAS = "usb:v1D6Bp0246d0553"
BLUEZ_PNP = bytes.fromhex("02006b1d46025305")
XBOX_PNP = bytes.fromhex("02005e04130b0905")
XBOX = (0x0002, 0x045E, 0x0B13, 0x0509)

EXE = "/usr/lib/bluetooth/bluetoothd"
DATA = (0x40000, 0x47000)
OPTS = 0x46598


class FakeBluetoothd:
    """/proc/<pid> of a bluetoothd whose writable data segment holds its DeviceID options."""

    def __init__(self, pid=979):
        self._tmp = tempfile.TemporaryDirectory(prefix="deckpad-proc-")
        self.proc = self._tmp.name
        self.pid = pid
        self.dir = os.path.join(self.proc, str(pid))
        os.mkdir(self.dir)
        os.symlink(EXE, os.path.join(self.dir, "exe"))
        self.set_start_time(1234)
        self.maps = [
            "%x-%x r--p 00000000 00:1b 131992 %s" % (0x10000, 0x18000, EXE),
            "%x-%x r-xp 00008000 00:1b 131992 %s" % (0x18000, 0x30000, EXE),
            "%x-%x rw-p 0015e000 00:1b 131992 %s" % (DATA[0], DATA[1], EXE),
            "%x-%x rw-p 00000000 00:00 0 [heap]" % (0x50000, 0x60000),
        ]
        self._write_maps()
        with open(os.path.join(self.dir, "mem"), "wb") as f:
            f.truncate(0x60000)
        self.poke(OPTS - 8, bytes.fromhex("0101000101000000"))
        self.poke(OPTS, BLUEZ_PNP)

    def set_start_time(self, ticks):
        fields = ["S", "1"] + ["0"] * 17 + [str(ticks), "0", "0"]
        with open(os.path.join(self.dir, "stat"), "w") as f:
            f.write("%d (bluetoothd) %s\n" % (self.pid, " ".join(fields)))

    def _write_maps(self):
        with open(os.path.join(self.dir, "maps"), "w") as f:
            f.write("\n".join(self.maps) + "\n")

    def poke(self, address, data):
        with open(os.path.join(self.dir, "mem"), "r+b") as f:
            f.seek(address)
            f.write(data)

    def peek(self, address=OPTS, size=8):
        with open(os.path.join(self.dir, "mem"), "rb") as f:
            f.seek(address)
            return f.read(size)

    def cleanup(self):
        self._tmp.cleanup()


class OverridingBluetoothdsDeviceId(unittest.TestCase):
    def setUp(self):
        self.bluetoothd = FakeBluetoothd()
        self.addCleanup(self.bluetoothd.cleanup)

    def override(self, modalias=BLUEZ_MODALIAS):
        return device_id.override(self.bluetoothd.pid, modalias, XBOX, proc=self.bluetoothd.proc)

    def test_bluetoothd_reports_the_controller_identity_while_overridden(self):
        override = self.override()

        self.assertIsNotNone(override)
        self.assertEqual(self.bluetoothd.peek(), XBOX_PNP)

    def test_restoring_brings_back_bluezs_identity(self):
        override = self.override()

        override.restore()

        self.assertEqual(self.bluetoothd.peek(), BLUEZ_PNP)

    def test_restoring_twice_is_harmless(self):
        override = self.override()
        override.restore()
        self.bluetoothd.poke(OPTS, bytes.fromhex("0200ffff00000100"))

        override.restore()

        self.assertEqual(self.bluetoothd.peek(), bytes.fromhex("0200ffff00000100"))

    def test_only_bluetoothds_own_data_segment_is_touched(self):
        self.bluetoothd.poke(0x50100, BLUEZ_PNP)

        self.override()

        self.assertEqual(self.bluetoothd.peek(0x50100), BLUEZ_PNP)
        self.assertEqual(self.bluetoothd.peek(), XBOX_PNP)

    def test_an_ambiguous_match_is_left_alone(self):
        self.bluetoothd.poke(DATA[0] + 0x10, BLUEZ_PNP)

        self.assertIsNone(self.override())
        self.assertEqual(self.bluetoothd.peek(), BLUEZ_PNP)
        self.assertEqual(self.bluetoothd.peek(DATA[0] + 0x10), BLUEZ_PNP)

    def test_an_unrecognised_bluetoothd_is_left_alone(self):
        self.bluetoothd.poke(OPTS, bytes(8))

        self.assertIsNone(self.override())
        self.assertEqual(self.bluetoothd.peek(), bytes(8))

    def test_an_unknown_modalias_is_left_alone(self):
        self.assertIsNone(self.override(modalias=""))
        self.assertEqual(self.bluetoothd.peek(), BLUEZ_PNP)

    def test_an_override_left_by_a_crashed_session_is_adopted_and_restored(self):
        self.override()

        adopted = self.override()
        adopted.restore()

        self.assertEqual(self.bluetoothd.peek(), BLUEZ_PNP)

    def test_an_override_left_by_a_killed_plugin_is_undone_at_startup(self):
        self.override()

        restored = device_id.restore_leftover(self.bluetoothd.pid, BLUEZ_MODALIAS, XBOX, proc=self.bluetoothd.proc)

        self.assertTrue(restored)
        self.assertEqual(self.bluetoothd.peek(), BLUEZ_PNP)

    def test_startup_leaves_an_untouched_bluetoothd_alone(self):
        restored = device_id.restore_leftover(self.bluetoothd.pid, BLUEZ_MODALIAS, XBOX, proc=self.bluetoothd.proc)

        self.assertFalse(restored)
        self.assertEqual(self.bluetoothd.peek(), BLUEZ_PNP)

    def test_a_bluetoothd_that_restarted_is_not_written_to(self):
        override = self.override()
        self.bluetoothd.set_start_time(99999)

        override.restore()

        self.assertEqual(self.bluetoothd.peek(), XBOX_PNP)

    def test_an_inaccessible_process_is_left_alone(self):
        self.assertIsNone(device_id.override(12345, BLUEZ_MODALIAS, XBOX, proc=self.bluetoothd.proc))

    def test_the_identity_is_written_little_endian(self):
        self.override()

        self.assertEqual(struct.unpack("<HHHH", self.bluetoothd.peek()), XBOX)


if __name__ == "__main__":
    unittest.main()
