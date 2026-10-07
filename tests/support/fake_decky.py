"""Installs a stand-in for the `decky` module that Decky Loader injects into plugin backends."""

import logging
import os
import sys
import tempfile
import types

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeDecky(types.ModuleType):
    def __init__(self):
        super().__init__("decky")
        self._tmp = tempfile.TemporaryDirectory(prefix="deckpad-decky-")
        self.logger = logging.getLogger("deckpad-test")
        self.DECKY_PLUGIN_DIR = REPO_ROOT
        self.DECKY_PLUGIN_SETTINGS_DIR = self._tmp.name + "/settings"
        self.DECKY_PLUGIN_RUNTIME_DIR = self._tmp.name + "/runtime"
        self.DECKY_PLUGIN_LOG_DIR = self._tmp.name + "/logs"
        self.events = []

    async def emit(self, event, *args):
        self.events.append((event, *args))

    def migrate_logs(self, *a):
        return {}

    def migrate_settings(self, *a):
        return {}

    def migrate_runtime(self, *a):
        return {}

    def cleanup(self):
        self._tmp.cleanup()


def install():
    decky = FakeDecky()
    sys.modules["decky"] = decky
    return decky
