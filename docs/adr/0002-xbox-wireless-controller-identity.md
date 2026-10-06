# Controller Identity: Xbox Wireless Controller (BLE firmware)

DeckPad presents itself as an Xbox Wireless Controller (Series X|S, model 1914) in its BLE-firmware form: PnP ID USB-IF `045E:0B13`, product version `0x0509`. It uses that model's HID report descriptor (`XboxOneS_1914_HIDDescriptor` in ESP32-BLE-CompositeHID) and its 17-byte input report 0x01 (four 16-bit sticks, two 10-bit triggers, hat, 15 buttons, Share bit as Consumer "Record" 0x00B2). We chose it because it is the one gamepad identity that every major host stack recognises natively over BLE without drivers. Windows maps it to XInput, Apple's GameController framework and Android list it as a supported controller, and SDL has a dedicated HIDAPI Bluetooth parser for this exact report layout. Its button usage numbering also lands on the standard Linux/Android evdev gamepad codes even under `hid-generic`.

## Considered Options

- **Generic HID gamepad with our own identity.** This was rejected. Windows exposes it only through DirectInput (most games expect XInput), iOS/macOS ignore it, and mappings differ by host.
- **Xbox One S 1708 Classic-BT PID `02FD` (ControllerOS's choice).** SDL associates this PID with older firmware report variants. `0B13` (Series X|S, BLE) is the current shipping controller and keeps the same 17-byte layout. We keep `0B20` (One S, BLE firmware) as a fallback if a host rejects `0B13`.
- **DualShock 4 / DualSense / Switch Pro.** These are Classic-only, have proprietary report formats, and some hosts require authentication.

## Consequences

- If we claim the VID/PID, the descriptor and reports must match real firmware byte for byte, because host drivers parse by VID/PID rather than by descriptor. The 1708 descriptor (Consumer AC Back plus separate report 0x02 for Guide) belongs to PID `02FD`/`0B20` and must not be paired with `0B13`.
- The Deck's bluetoothd publishes its own Device Information Service (PnP 1D6B:0246) at lower handles, and it cannot be removed at runtime (only `DeviceID = false` in `/etc/bluetooth/main.conf`). On hardware, a Linux host built the first HID device as `1D6B:0246`, and only later sessions used the cached `045E:0B13`. Whether Windows, macOS, iOS, and Android pick the right DIS is the top open risk (see the implementation notes). Fallback options, in order of preference: a reversible runtime override of bluetoothd's DeviceID, or accepting a generic identity on the affected hosts.
- The Host-visible name after connection is the Deck adapter's GAP name (its Bluetooth alias), not the advertised LocalName.
- Using Microsoft's VID/PID is common emulator practice (ESP32-BLE-CompositeHID, ControllerOS). DeckPad must not use Microsoft or Xbox marks in its own branding.
