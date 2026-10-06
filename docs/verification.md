# Verification status

What has been checked on real hardware, and what is still open. The README's
[Compatibility](../README.md#compatibility) section lists the tested Deck, Decky and Host versions and
what was verified for each area. This page tracks the open unknowns behind those results, so a decision
record can point at one place.

"Verified on hardware" means the Steam Deck LCD (SteamOS 3.8.28 Stable, BlueZ 5.83, Decky Loader v3.2.9)
with an Arch Linux laptop (BlueZ 5.87) as the Host. Anything else is unverified.

## Open unknowns

| # | Unknown | Status |
|---|---|---|
| U1 | Which Device Information Service PnP ID each Host OS uses. bluetoothd publishes its own DIS (`1D6B:0246`) before DeckPad's, and a Linux Host built its first gamepad from it. | Resolved for Linux by overriding bluetoothd's DeviceID while Controller Mode is on ([ADR-0006](adr/0006-override-bluetoothd-deviceid-in-memory.md)): the Host reads `045E:0B13` on its first pairing. Windows, macOS, iOS and Android are untested. |
| U2 | Whether a shorter LE connection interval can be requested, and whether Hosts accept it. | Resolved for the Linux Host ([ADR-0008](adr/0008-shorter-connection-interval-and-link-paced-reports.md)): it settles at 18.75 ms. 3 of 13 interval updates were followed by a link drop. Other Hosts are untested. |
| U3 | Coexistence with Bluetooth headphones, keyboards or controllers paired to the Deck while a Host is connected (audio dropouts, throughput). | Open. Needs real peripherals and a person listening. |
| U4 | Whether Steam's UI on the Deck reacts to presses during Controller Mode, and whether a full-screen route can absorb them. | Partly addressed: the Controller Screen ([ADR-0011](adr/0011-controller-screen-route.md)) is registered with Decky's router on the Deck. Whether it absorbs navigation in Gaming Mode, and how the user leaves it, has not been checked by a person. |
| U5 | Whether dbus-fast loads in Decky's embedded Python. | Resolved: Decky's Python 3.11.7 lacks `xml.etree`, and DeckPad ships CPython's copy as a fallback (`py_modules/_stdlib`). |
| U6 | Rumble from Windows/SDL Hosts, and Deck haptics. | Open, out of scope for now: output reports are accepted and dropped. |
| U7 | Dual-mode Hosts (Android, Windows) deriving a Classic link key and then trying a Classic connection to the Deck. | Open. To be observed during U1 tests. |
| U8 | Suspend and resume with a Host connected. | Open. |
| U9 | Steam Deck OLED (different Bluetooth chip). | Open. No hardware available. |
| U10 | Whether Steam marks every device it pairs as trusted. DeckPad's agent refuses `AuthorizeService` for paired but untrusted devices that are not Paired Hosts while Controller Mode is on ([ADR-0005](adr/0005-borrow-default-pairing-agent.md)). | Open. If Steam leaves some devices untrusted, they cannot use the Deck's services while Controller Mode is on. |
| U11 | Uninstall from Decky's settings removes the Paired Hosts' pairings within Decky's shutdown deadline. | Verified on the Deck through Decky's own uninstall call, with Controller Mode on and the Host connected: the Host was disconnected, its pairing removed, `paired_hosts.json` and `diagnostics.txt` deleted, and the interval restored, in 2.0 s. That other paired devices stay paired is covered by automated tests only, because no other device was paired to the Deck. |
