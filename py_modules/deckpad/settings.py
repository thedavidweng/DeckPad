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
                    value = json.load(f).get("quit_combo", True)
                if type(value) is not bool:
                    raise ValueError("quit_combo must be a boolean")
                self.quit_combo = value
            except (OSError, ValueError, AttributeError) as e:
                log.warning("Ignoring unreadable settings %s: %r", path, e)

    def set_quit_combo(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("quit_combo must be a boolean")
        if self._path:
            storage.save(self._path, {"quit_combo": enabled})
        self.quit_combo = enabled

    def erase(self):
        """Back to the defaults, and delete the file."""
        self.quit_combo = True
        if self._path:
            storage.erase(self._path)
