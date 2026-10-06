"""The user's DeckPad preferences, remembered across sessions and plugin reloads."""

import json
import logging
import os

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
                json.dump({"quit_combo": self.quit_combo}, f, indent=2)
            os.replace(tmp, self._path)
        except OSError as e:
            log.warning("Could not save settings: %r", e)
