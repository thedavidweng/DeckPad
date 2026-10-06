# Read Deck Controls from the controller's hidraw node, alongside Steam

DeckPad reads Deck Controls directly from the Valve controller's raw HID interface: the `28DE:1205` hidraw node whose HID device has no `input/` child, currently `/dev/hidraw2`, interface 2. It opens that node read-only and decodes the 64-byte `0x09` Deck State Reports, which arrive at about 250 Hz. It never sends the lizard-mode or settings feature reports, because Steam already owns the controller configuration and hidraw allows several readers to receive every report.

Evdev is not an option. `hid-steam` emits no gamepad events on the Deck while Steam holds the hidraw client (its `gamepad_mode` defaults to off). Steam's virtual "Microsoft X-Box 360 pad" (js0/uinput) only exists for the focused game, and it carries Steam Input remapping. DeckJoy's approach, running as a Steam game and reading Steam's virtual pad, would force DeckPad to run as a non-Steam game, which is not the QAM-native experience the spec asks for.

## Consequences

- Steam keeps receiving the same inputs, so whatever has focus on the Deck reacts to presses while Controller Mode is on. That is the Steam UI or a running game. The QAM and Steam buttons always reach Steam. How to neutralise this (for example, a full-screen DeckPad route that swallows navigation) is open for #3/#5.
- The report layout is undocumented Valve firmware behaviour. It is cross-checked against ControllerOS's mapping and the kernel's `hid-steam.c`, but a SteamOS or firmware update could change it.
- Discovery must use VID/PID plus sysfs topology, never a fixed `hidrawN`.
