"""Failed writes leave the previous JSON intact and no partially written temporary file."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from deckpad import storage


class AtomicStorage(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "state.json")
        storage.save(self.path, {"old": True})

    def assert_previous_survives(self):
        with open(self.path) as f:
            self.assertEqual(json.load(f), {"old": True})
        self.assertFalse(os.path.exists(self.path + ".tmp"))

    def test_serialization_failure_does_not_leave_partial_json(self):
        with self.assertRaises(TypeError):
            storage.save(self.path, {"new": object()})
        self.assert_previous_survives()

    def test_disk_sync_failure_does_not_replace_the_previous_file(self):
        with patch("os.fsync", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                storage.save(self.path, {"new": True})
        self.assert_previous_survives()

    def test_rename_failure_does_not_leave_a_temporary_file(self):
        with patch("os.replace", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                storage.save(self.path, {"new": True})
        self.assert_previous_survives()

    def test_a_successful_write_replaces_the_file(self):
        storage.save(self.path, {"new": True})
        with open(self.path) as f:
            self.assertEqual(json.load(f), {"new": True})
        self.assertFalse(os.path.exists(self.path + ".tmp"))

    def test_erase_removes_a_temporary_file_left_by_a_killed_process(self):
        with open(self.path + ".tmp", "w") as f:
            f.write('{"partial":')
        storage.erase(self.path)
        self.assertFalse(os.path.exists(self.path))
        self.assertFalse(os.path.exists(self.path + ".tmp"))
