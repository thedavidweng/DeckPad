import os
import sys

# Decky appends py_modules to sys.path; putting it first makes the vendored, pinned dbus-fast win over
# anything else on the path.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "py_modules"))

import decky  # noqa: E402

from deckpad import controller_mode, diagnostics  # noqa: E402
from deckpad.hosts import PairedHosts  # noqa: E402
from deckpad.settings import Settings  # noqa: E402

STATE_EVENT = "controller_mode_state"
GAMEPAD_EVENT = "gamepad_report"
INTERVAL_STATE_FILE = "connection_interval.json"
DIAGNOSTICS_FILE = "diagnostics.txt"


def _interval_state_path():
    return os.path.join(decky.DECKY_PLUGIN_RUNTIME_DIR, INTERVAL_STATE_FILE)


async def _publish(snapshot):
    await decky.emit(STATE_EVENT, snapshot)


async def _publish_gamepad_report(report):
    await decky.emit(GAMEPAD_EVENT, report)


class Plugin:
    def __init__(self):
        diagnostics.RECENT_LOG.attach(decky.logger)
        # Controller Mode always starts off: after a reload or Decky restart the Deck is back to
        # ordinary SteamOS behaviour until the user turns it on again.
        self._controller_mode = controller_mode.ControllerMode(
            on_change=_publish,
            paired_hosts=PairedHosts(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "paired_hosts.json")),
            interval_state_path=_interval_state_path(),
            settings=Settings(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")),
            on_gamepad_report=_publish_gamepad_report,
        )

    async def get_state(self):
        return self._controller_mode.snapshot()

    async def set_controller_mode(self, enabled):
        return await self._controller_mode.set_enabled(bool(enabled))

    async def set_pairing_mode(self, enabled):
        return await self._controller_mode.set_pairing_mode(bool(enabled))

    async def set_quit_combo(self, enabled):
        return await self._controller_mode.set_quit_combo(bool(enabled))

    async def watch_gamepad(self, enabled):
        """The Controller Screen draws the Gamepad Reports going to the Host while it is open."""
        self._controller_mode.watch_gamepad(bool(enabled))

    async def disconnect_host(self, address):
        return await self._controller_mode.disconnect_host(str(address))

    async def forget_host(self, address):
        return await self._controller_mode.forget_host(str(address))

    async def allow_reconnect(self):
        return await self._controller_mode.allow_reconnect()

    async def get_diagnostics(self):
        """For the panel's Troubleshooting section. Also saved to the plugin's log directory."""
        report = await diagnostics.collect(self._controller_mode, getattr(decky, "DECKY_PLUGIN_VERSION", None))
        path = os.path.join(decky.DECKY_PLUGIN_LOG_DIR, DIAGNOSTICS_FILE)
        try:
            os.makedirs(decky.DECKY_PLUGIN_LOG_DIR, exist_ok=True)
            with open(path, "w") as f:
                f.write(report["text"])
        except OSError as e:
            decky.logger.warning("Could not save diagnostics to %s: %r", path, e)
            path = None
        return dict(report, path=path)

    async def _main(self):
        from dbus_fast.__version__ import __version__ as dbus_fast_version

        decky.logger.info("DeckPad backend started (dbus-fast %s)", dbus_fast_version)
        await self._controller_mode.clean_up_after_previous_run()

    async def _unload(self):
        self._controller_mode.shutdown()
        decky.logger.info("DeckPad backend stopped")

    async def _uninstall(self):
        """Decky runs this after `_unload` when the user uninstalls DeckPad. Must not await (see shutdown)."""
        self._controller_mode.uninstall()
        path = os.path.join(decky.DECKY_PLUGIN_LOG_DIR, DIAGNOSTICS_FILE)
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError as e:
            decky.logger.warning("Could not delete %s: %r", path, e)

    async def _migration(self):
        pass
