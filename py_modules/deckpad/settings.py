"""The user's DeckPad preferences, remembered across sessions and plugin reloads."""

import json
import logging
import os

from . import storage

log = logging.getLogger("deckpad.settings")


class Settings:
    def __init__(self, path=None):
        self._path = path
        self.quit_combo = True
        if path and os.path.exists(path):
            try:
                with open(path) as f:
                    self.quit_combo = bool(json.load(f).get("quit_combo", True))
            except (OSError, ValueError, AttributeError) as e:
                log.warning("Ignoring unreadable settings %s: %r", path, e)

    def set_quit_combo(self, enabled):
        self.quit_combo = bool(enabled)
        self._save()

    def erase(self):
        """Back to the defaults, and delete the file."""
        self.quit_combo = True
        if self._path:
            storage.erase(self._path)

    def _save(self):
        if not self._path:
            return
        try:
            storage.save(self._path, {"quit_combo": self.quit_combo})
        except OSError as e:
            log.warning("Could not save settings: %r", e)
