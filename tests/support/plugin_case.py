"""The plugin backend driven the way Decky and the QAM panel drive it, against a private system bus with a
fake org.bluez on it."""

import importlib
import unittest

from tests.support import fake_decky
from tests.support.fake_bluez import FakeBluez
from tests.support.system_bus import PrivateSystemBus


class PluginTestCase(unittest.IsolatedAsyncioTestCase):
    bluez_options = {}

    @classmethod
    def setUpClass(cls):
        cls.system_bus = PrivateSystemBus()
        cls.system_bus.start()

    @classmethod
    def tearDownClass(cls):
        cls.system_bus.stop()

    async def asyncSetUp(self):
        self.decky = fake_decky.install()
        self.addCleanup(self.decky.cleanup)
        self.bluez = None
        if self.bluez_options is not None:
            self.bluez = FakeBluez(**self.bluez_options)
            await self.bluez.start()
        # Decky gives each plugin process a fresh `decky` module, so load main.py against this test's.
        self.main = importlib.reload(importlib.import_module("main"))
        self.plugin = self.main.Plugin()
        await self.plugin._migration()
        await self.plugin._main()

    async def asyncTearDown(self):
        await self.plugin._unload()
        if self.bluez:
            await self.bluez.stop()

    async def state(self):
        return await self.plugin.get_state()
