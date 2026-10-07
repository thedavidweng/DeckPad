# Verification status

What has been checked on real hardware, and what is still open, so a decision record can point at one
place.

## Test setup

"Verified on hardware" means this setup. Anything else is unverified.

| | Version |
|---|---|
| Steam Deck | LCD model (Realtek RTL8822CE Bluetooth), SteamOS 3.8.28 Stable (build 20260922.1), kernel 6.18, BlueZ 5.83 |
| Decky Loader | v3.2.9 (embedded Python 3.11.7) |
| Host | Arch Linux laptop, BlueZ 5.87, paired with `bluetoothctl` |

## What was verified, and how

| Area | Automated tests (fake BlueZ on a private D-Bus) | On the real Deck with the Linux Host |
|---|---|---|
| Controller Mode on/off, Decky reload and restart | Yes | Yes, including 16 and 10 on/off cycles; nothing left registered afterwards |
| Pairing from the Host's normal Bluetooth flow | Yes | Yes; the Host builds a `045E:0B13` gamepad bound to the `hid-microsoft` driver |
| Pairing timeout, cancel, and stale-pairing error | Yes | Timeout and stale-pairing error, yes |
| Reconnect without re-pairing after Controller Mode off/on | Yes | Yes; the Host reconnected by itself in about 2-11 s and kept receiving input |
| Disconnect, Allow Reconnecting, Forget | Yes | Yes |
| Deck controls to Gamepad Reports (mapping, send-on-change, pacing) | Yes | Report path yes; the Host's capabilities match the README's controls table. A person pressed every core control with the Controller Screen open, and each lit up correctly there; a button-by-button check on the Host's side has not been done |
| Report rate and latency | Pacing logic only | About 42-45 reports/s with no backlog once the 18.75 ms interval is in place; about 18-25 reports/s at the Host's initial 48.75 ms |
| Bluetooth restart, adapter off and on | Yes | Yes; Controller Mode resumed and the Host reconnected |
| Troubleshooting diagnostics | Yes | Collected and saved; the copy button in Gaming Mode has not been checked |
| Backend loading inside Decky's Python | Yes (reproduces the missing `xml.etree`) | Yes |
| Store package (metadata, licenses, files the store CI zips) | Yes | The store-shaped zip was installed and smoke-tested |
| Uninstall from Decky's settings | Yes | Yes, with a Host connected: its pairing was removed and DeckPad's files deleted |

Not yet checked on hardware: how the QAM panel looks (agents drove it through the plugin API only), the
copy button in Troubleshooting, and the open unknowns below.

## Hosts

| Host | Status |
|---|---|
| Linux with BlueZ (Arch Linux, BlueZ 5.87) | Tested: pairs, reconnects, receives input as an Xbox controller |
| Windows 10/11, macOS, iOS/iPadOS, Android, ChromeOS | Untested |
| Game consoles, smart TVs | Untested |
| Steam Deck OLED (as the controller) | Untested |

## Open unknowns

| # | Unknown | Status |
|---|---|---|
| U1 | Which Device Information Service PnP ID each Host OS uses. bluetoothd publishes its own DIS (`1D6B:0246`) before DeckPad's, and a Linux Host built its first gamepad from it. | Resolved for Linux by overriding bluetoothd's DeviceID while Controller Mode is on ([ADR-0006](adr/0006-override-bluetoothd-deviceid-in-memory.md)): the Host reads `045E:0B13` on its first pairing. Windows, macOS, iOS and Android are untested. |
| U2 | Whether a shorter LE connection interval can be requested, and whether Hosts accept it. | Resolved for the Linux Host ([ADR-0008](adr/0008-shorter-connection-interval-and-link-paced-reports.md)): it settles at 18.75 ms. 3 of 13 interval updates were followed by a link drop. Other Hosts are untested. |
| U3 | Coexistence with Bluetooth headphones, keyboards or controllers paired to the Deck while a Host is connected (audio dropouts, throughput). | Open. Needs real peripherals and a person listening. |
| U4 | Whether Steam's UI on the Deck reacts to presses during Controller Mode, and whether a full-screen route can absorb them. | Mostly resolved on the Deck (SteamOS 3.8.28, Gaming Mode). The Controller Screen ([ADR-0011](adr/0011-controller-screen-route.md)) absorbs the presses: a person pressed every core control and nothing behind it moved. The first build also swallowed the Steam and `…` buttons, so the user could not leave. Now, while the Quit Combo ([ADR-0012](adr/0012-quit-combo.md)) is on, the screen turns those two buttons' menus off with Steam's own switch ([ADR-0014](adr/0014-turn-off-steams-menu-buttons-on-the-controller-screen.md)): pressing them opened nothing, and holding the Quit Combo closed the screen and turned Controller Mode off. **Close** (touch), Controller Mode turning off, and switching the Quit Combo off all turn the menus back on. The screen's drawing of what the Host receives ([ADR-0013](adr/0013-draw-the-host-view-with-steams-controller-outline.md)) lit up correctly for every control. Open: whether Steam's chords on the Steam button (holding it, Steam + B) still work while the screen is open. |
| U5 | Whether dbus-fast loads in Decky's embedded Python. | Resolved: Decky's Python 3.11.7 lacks `xml.etree`, and DeckPad ships CPython's copy as a fallback (`py_modules/_stdlib`). |
| U6 | Rumble from Windows/SDL Hosts, and Deck haptics. | Open, out of scope for now: output reports are accepted and dropped. |
| U7 | Dual-mode Hosts (Android, Windows) deriving a Classic link key and then trying a Classic connection to the Deck. | Open. To be observed during U1 tests. |
| U8 | Suspend and resume with a Host connected. | Open. |
| U9 | Steam Deck OLED (different Bluetooth chip). | Open. No hardware available. |
| U10 | Whether Steam marks every device it pairs as trusted. DeckPad's agent refuses `AuthorizeService` for paired but untrusted devices that are not Paired Hosts while Controller Mode is on ([ADR-0005](adr/0005-borrow-default-pairing-agent.md)). | Open. If Steam leaves some devices untrusted, they cannot use the Deck's services while Controller Mode is on. |
| U11 | Uninstall from Decky's settings removes the Paired Hosts' pairings within Decky's shutdown deadline. | Verified on the Deck through Decky's own uninstall call, with Controller Mode on and the Host connected: the Host was disconnected, its pairing removed, `paired_hosts.json` and `diagnostics.txt` deleted, and the interval restored, in 2.0 s. That other paired devices stay paired is covered by automated tests only, because no other device was paired to the Deck. |
