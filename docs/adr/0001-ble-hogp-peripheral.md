# Present the Deck to hosts as a Bluetooth LE HID-over-GATT peripheral

DeckPad exposes the Deck to a Host as a BLE HID-over-GATT (HOGP) gamepad, built from BlueZ's D-Bus GATT server (`GattManager1.RegisterApplication`) and LE advertising (`LEAdvertisingManager1.RegisterAdvertisement`) APIs. We do not use Classic Bluetooth HID (L2CAP PSM 17/19).

Classic HID is ruled out because bluetoothd's `input` plugin already listens on PSM 17/19 to support the Deck's own Bluetooth keyboards, mice, and controllers. Binding those PSMs requires stopping that plugin (DeckJoy installs a persistent `bluetooth.service` drop-in running `bluetoothd -P input` and restarts bluetooth), which breaks the Deck's ordinary Bluetooth role and permanently modifies SteamOS. HOGP needs none of that. On a Steam Deck LCD (SteamOS, BlueZ 5.83, RTL8822CE), it registered and advertised without root, worked alongside the stock `input` plugin, Steam's agent, and the adapter's normal dual-mode/BR/EDR state, and an unmodified Arch Linux host paired with it through its normal BlueZ flow and received gamepad input in evdev.

## Considered Options

- **Classic HID with our own L2CAP sockets.** It gives the widest legacy-host reach, but it requires root, disabling the `input` plugin, and a bluetoothd restart that disconnects every peripheral. Rejected.
- **Classic HID through `ProfileManager1.RegisterProfile` (UUID 0x1124).** bluetoothd still has to bind PSM 17/19, which collides with the `input` plugin in the same way. Rejected.
- **USB gadget (DeckJoy's primary mode).** It is not Bluetooth, and it needs a BIOS change to DRD mode. It is out of scope.

## Consequences

- Hosts must support BLE HID (HOGP). Windows 10+, macOS, iOS/iPadOS, Android, ChromeOS, and Linux do. Very old, Classic-only hosts are not supported.
- The Deck's bluetoothd always publishes its own Device Information Service before ours, so the Host may read BlueZ's PnP ID (1D6B:0246) instead of the Controller Identity. See ADR-0002.
- Link throughput is bounded by the LE connection interval that the Host chooses. BlueZ queues notifications without limit, so the report pipeline must pace itself to the link and coalesce to the latest state.
