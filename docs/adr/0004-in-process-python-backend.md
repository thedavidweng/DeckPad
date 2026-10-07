# Run the whole peripheral in the Decky Python backend, with vendored pure-Python dbus-fast

All of DeckPad's backend work runs as asyncio tasks inside the plugin's Decky Python backend (`main.py`, Decky's embedded Python 3.11, running as root through the `root` flag in `plugin.json`, which ADR-0006 needs). That covers the GATT application, advertisement, pairing agent, hidraw reader, and report pacing. There is no helper daemon, no IPC, and no compiled binary. D-Bus goes through a vendored, pinned, pure-Python copy of `dbus-fast` (MIT) in `py_modules/`.

Decky's embedded interpreter cannot import SteamOS's system `dbus-python` or `gi`, which are built for Python 3.13 and live outside the PyInstaller path. A pure-Python library avoids shipping native wheels. A Python-only backend also keeps the Plugin Store on its simpler review track (Stable and Beta testing only, no custom-binary rules). `dbus-fast` exports the many GATT objects HOGP needs with typed decorators, built-in ObjectManager/Properties, and Unix-FD support (for a later `AcquireNotify`). That beats hand-rolling them on `jeepney`, the low-level library the Outpox Bluetooth plugin uses only for client calls. On hardware, a pure-Python `dbus-fast` 5.2.0 spike sent about 120 reports/s at about 4% of one core and was paired and consumed by an unmodified Linux host.

## Consequences

- When the plugin unloads, it must tear everything down itself: unregister the advertisement, application, and agent, close hidraw, and disconnect hosts. If the process dies, bluetoothd drops the registrations automatically, because they are bound to the D-Bus connection.
- Root is only strictly needed for adapter-level tuning such as connection parameters or a DeviceID override. The BlueZ registrations and hidraw reads worked as user `deck`.
- `dbus-fast` 5.x requires Python >= 3.11, so pin the version and re-check it against Decky's bundled Python on every Decky release.
- Never set a `name` attribute on a `ServiceInterface` subclass. It shadows the D-Bus interface name, and BlueZ then rejects the application with "No valid service object found".
