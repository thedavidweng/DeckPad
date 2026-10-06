# Make bluetoothd's own DIS report the Controller Identity by rewriting its DeviceID in memory while Controller Mode is on

bluetoothd always publishes its own Device Information Service, with PnP ID `1D6B:0246` (BlueZ), at lower GATT handles than DeckPad's (ADR-0001, ADR-0002). Hosts use the first DIS they find. Linux's `hog-lib` does, and in ticket #2 a Linux Host built its first HID device as `1D6B:0246`. So, while Controller Mode is on, DeckPad (running as root) rewrites the four `u16` DeviceID fields (`btd_opts.did_source/vendor/product/version`) inside the running bluetoothd's data segment through `/proc/<pid>/mem`, and writes BlueZ's values back when Controller Mode stops. No file is changed, and bluetoothd is not restarted.

This works because BlueZ 5.83 builds the DIS PnP ID value from those globals on every read (`device_info_read_pnp_id_cb` in `src/gatt-database.c`). Nothing else reads them after startup: the Classic SDP DeviceID record, the EIR, and `Adapter1.Modalias` are all built once at startup, so the Deck's Classic identity is unchanged. The only other runtime reader is the `neard` NFC plugin, which SteamOS does not use. On the Deck, an unmodified Arch Linux Host (BlueZ 5.87) paired for the first time and built its HID device as `045E:0B13 v0509`, bound to the kernel's `hid-microsoft` driver.

## Safety rules (in `py_modules/deckpad/device_id.py`)

- bluetoothd's PID comes from D-Bus (`GetConnectionUnixProcessID("org.bluez")`). The original value is derived from the adapter's `Modalias` (`usb:v1D6Bp0246d0553` becomes `02 00 6b 1d 46 02 53 05`), never hard-coded.
- DeckPad scans only the writable mappings of bluetoothd's own executable image, and writes only if the original value occurs exactly once there. Anything else (zero or several matches, an unknown Modalias, or an inaccessible process) leaves bluetoothd untouched and logs why. Hosts may then read BlueZ's ID, which is the pre-ADR behaviour.
- Restore writes back only if the bytes are still DeckPad's, and only if the process is the same one (same PID, exe, and start time). A restarted bluetoothd already has its own values.
- Restore is synchronous file I/O, so it also runs in `_unload`, where awaiting is impossible. If DeckPad is SIGKILLed with the override in place, the next backend start (`_main`) detects the single leftover copy and restores it. The next Controller Mode start would also adopt it.

## Considered Options

- **Transient runtime drop-in plus bluetoothd restart** (`/run/systemd/system/bluetooth.service.d/` pointing `-f` at a generated main.conf with `DeviceID = usb:045e:0b13:0509`). Rejected: every Controller Mode enter and exit would restart bluetoothd, which disconnects headphones and every other Bluetooth device. It would also change the Deck's Classic identity.
- **`DeviceID = false` in `/etc/bluetooth/main.conf`.** Rejected: it permanently modifies SteamOS, needs a restart, and still leaves Hosts that expect a DIS with no identity to read.
- **Accept BlueZ's ID.** This is the fallback when the override cannot be applied. Windows, Apple, and Android mapping by VID/PID would then most likely treat the Deck as a generic gamepad.

## Consequences

- The plugin must run as root: `plugin.json` now has the `root` flag. (ADR-0004's "`_root` flag" wording was wrong: `_root` is the disabled form.) The rest of the backend works the same as root.
- Writing another process's memory is unusual for a Decky plugin and may draw Plugin Store review questions. #8 must state it plainly in the store submission.
- A BlueZ update that changes how `btd_opts` is stored, or that caches the PnP value, makes the override a logged no-op rather than a failure. Re-verify on each SteamOS BlueZ bump: check the PnP ID that a Host reads, or the Host's `Modalias`.
- While Controller Mode is on, any LE central that reads the Deck's DIS sees the Xbox identity. That includes devices unrelated to DeckPad.
- Hosts cache the DIS per bond. A Host that bonded before this override existed keeps its cached ID until it is re-paired.
