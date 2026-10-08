"""Preferences accept actual booleans and never claim a failed write succeeded."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deckpad.settings import Settings


class QuitComboSettings(unittest.TestCase):
    def test_only_boolean_file_values_override_the_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            for value in ("false", 0, None, [], {}):
                with self.subTest(value=value):
                    path.write_text(json.dumps({"quit_combo": value}))
                    self.assertTrue(Settings(str(path)).quit_combo)
            path.write_text('{"quit_combo": false}')
            self.assertFalse(Settings(str(path)).quit_combo)

    def test_a_failed_save_keeps_the_previous_preference_and_exposes_the_error(self):
        settings = Settings("settings.json")
        with patch("deckpad.settings.storage.save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                settings.set_quit_combo(False)
        self.assertTrue(settings.quit_combo)

    def test_boolean_updates_persist_and_invalid_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "settings.json")
            settings = Settings(path)
            settings.set_quit_combo(False)
            self.assertFalse(Settings(path).quit_combo)
            for value in ("false", 0, None):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    settings.set_quit_combo(value)
