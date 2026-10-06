# DeckPad

DeckPad is a [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that lets you use
your Steam Deck as a Bluetooth game controller for another device, such as a PC, a phone, or a tablet.
The other device pairs with the Deck through its own normal Bluetooth settings, the same way it would
pair with a wireless controller, and needs no extra software.

**How DeckPad differs from the Bluetooth plugin.** The [Bluetooth](https://github.com/Outpox/Bluetooth)
plugin on the Plugin Store connects the Deck to Bluetooth devices such as headphones and controllers:
the Deck uses them. DeckPad works the other way round: the Deck *is* the controller, and another device
uses it. The two plugins do not overlap and can be installed together.

DeckPad is early software. It has been tested on one Steam Deck with one Linux laptop as the other
device; see [Compatibility](#compatibility) before you rely on it.

## Words used here

- **Host**: the device the Deck acts as a controller for (a PC, phone, tablet, or TV).
- **Controller Mode**: while it is on, the Deck sends its controls to a connected Host. Turning it off
  returns the Deck to normal.
- **Pairing Mode**: a three-minute window inside Controller Mode in which a new Host can find the Deck and
  pair with it.

## Requirements

- A Steam Deck running SteamOS, with [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader)
  installed. DeckPad was tested on a Steam Deck LCD; the Steam Deck OLED has not been tested.
- A Host that supports Bluetooth Low Energy game controllers (HID over GATT). Current Windows, macOS,
  iOS/iPadOS, Android, ChromeOS, and Linux versions support this in general, but only Linux has been
  tested with DeckPad. Classic-only Bluetooth hosts cannot connect.

## Installation

Install DeckPad from the Decky Plugin Store: open the Quick Access menu (the `…` button), select the
Decky tab, open the store, and install **DeckPad**.

Everything DeckPad needs ships inside the plugin. It installs no system packages, Flatpaks, or other
software, does not change SteamOS's read-only system files, and needs no Desktop Mode setup.

## Pairing a Host

1. In Gaming Mode, open the Quick Access menu, select the Decky tab, and open **DeckPad**.
2. Turn on **Controller Mode**.
3. Select **Pair a Device**. The panel shows "Waiting for a device to pair…" with the Deck's Bluetooth
   name and a three-minute countdown.
4. On the Host, open its Bluetooth settings, scan for devices, and select the Deck. It is listed under the
   Deck's Bluetooth name (by default `steamdeck`) with a game controller icon. If the Host asks you to
   confirm, accept.
5. The panel shows "Paired with *Host*". The Host now lists the Deck as a game controller.

Pairing ends after three minutes, or when you select **Cancel Pairing**. Outside Pairing Mode the Deck
does not show up in other devices' scan lists.

## Everyday use

- **Reconnecting.** With Controller Mode on, a Paired Host can reconnect without pairing again. Some
  Hosts reconnect by themselves; with others, select the Deck in the Host's Bluetooth settings. The panel
  shows "Waiting for a paired device" until one connects, then "Connected to *Host*".
- **Paired Devices.** The panel lists the Hosts paired with DeckPad. Only Hosts that paired through
  DeckPad are listed; your headphones and other Bluetooth devices are never shown or touched.
- **Disconnect** drops the link and stops that Host from reconnecting by itself until you select
  **Allow Reconnecting** or turn Controller Mode off and on.
- **Forget** removes the pairing on the Deck. Also remove the Deck in the Host's Bluetooth settings, or
  the next pairing attempt from that Host fails.
- **Turning Controller Mode off** disconnects the Host and returns Bluetooth on the Deck to normal. It
  always starts off after a reboot, a Decky restart, or a plugin reload.
- **Quit Combo.** Hold Menu + View + L1 + R1 together (and nothing else) to turn Controller Mode off
  from the Deck's controls, the same combination Moonlight uses to quit a stream. The Host gets a
  "nothing held" report instead of the combo, then disconnects, and the Controller Screen closes. If a
  game on the Host needs that combination, turn off **Quit Combo** in the panel's Settings section;
  the combo then goes to the Host like any other press.

### Controls

DeckPad presents itself to the Host as an Xbox Wireless Controller (model 1914, Bluetooth LE).

| Deck | Host sees |
|---|---|
| A, B, X, Y | A, B, X, Y |
| L1, R1 | Left and right bumpers |
| L2, R2 | Left and right triggers (analog) |
| Left and right sticks, L3, R3 | Left and right sticks and stick clicks |
| D-pad | D-pad |
| View, Menu | View, Menu |
| Steam button | Xbox (Guide) button |
| `…` (Quick Access) button | Share button |
| L4, L5, R4, R5, trackpads, gyro | Not sent |

Steam on the Deck still sees every button press while Controller Mode is on. See
[Known limitations](#known-limitations).

## Compatibility

This table records what has actually been checked. Anything not listed as tested is untested, not
known to work.

### Tested hardware and software

| | Version |
|---|---|
| Steam Deck | LCD model (Realtek RTL8822CE Bluetooth), SteamOS 3.8.28 Stable (build 20260922.1), kernel 6.18, BlueZ 5.83 |
| Decky Loader | v3.2.9 (embedded Python 3.11.7) |
| Host | Arch Linux laptop, BlueZ 5.87, paired with `bluetoothctl` |

### What was verified, and how

| Area | Automated tests (fake BlueZ on a private D-Bus) | On the real Deck with the Linux Host |
|---|---|---|
| Controller Mode on/off, Decky reload and restart | Yes | Yes, including 16 and 10 on/off cycles; nothing left registered afterwards |
| Pairing from the Host's normal Bluetooth flow | Yes | Yes; the Host builds a `045E:0B13` gamepad bound to the `hid-microsoft` driver |
| Pairing timeout, cancel, and stale-pairing error | Yes | Timeout and stale-pairing error, yes |
| Reconnect without re-pairing after Controller Mode off/on | Yes | Yes; the Host reconnected by itself in about 2-11 s and kept receiving input |
| Disconnect, Allow Reconnecting, Forget | Yes | Yes |
| Deck controls to Gamepad Reports (mapping, send-on-change, pacing) | Yes | Report path yes; the Host's capabilities match the table above. A full button-by-button check by a person holding the Deck has not been done |
| Report rate and latency | Pacing logic only | About 42-45 reports/s with no backlog once the 18.75 ms interval is in place; about 18-25 reports/s at the Host's initial 48.75 ms |
| Bluetooth restart, adapter off and on | Yes | Yes; Controller Mode resumed and the Host reconnected |
| Troubleshooting diagnostics | Yes | Collected and saved; the copy button in Gaming Mode has not been checked |
| Backend loading inside Decky's Python | Yes (reproduces the missing `xml.etree`) | Yes |
| Store package (metadata, licenses, files the store CI zips) | Yes | The store-shaped zip was installed and smoke-tested |
| Uninstall from Decky's settings | Yes | Yes, with a Host connected: its pairing was removed and DeckPad's files deleted |

Not yet checked on hardware: how the QAM panel looks (agents drove it through the plugin API only),
whether Steam's UI on the Deck reacts to presses during Controller Mode and whether the Controller
Screen stops it (its route is registered on the Deck, but it has not been opened in Gaming Mode),
Bluetooth headphones or other Bluetooth devices on the Deck while a Host is connected, and
suspend/resume. These are on the manual test list; see
[Verification status](docs/verification.md).

### Hosts

| Host | Status |
|---|---|
| Linux with BlueZ (Arch Linux, BlueZ 5.87) | Tested: pairs, reconnects, receives input as an Xbox controller |
| Windows 10/11 | Untested |
| macOS | Untested |
| iOS / iPadOS | Untested |
| Android | Untested |
| ChromeOS | Untested |
| Game consoles, smart TVs | Untested |
| Steam Deck OLED (as the controller) | Untested |

## Known limitations

- **One Host at a time.** With several Paired Hosts in range, the first one to connect wins; DeckPad
  cannot choose which one reconnects. If you pair another Host while one is connected, the newly paired
  Host takes over and the previous one is disconnected (it can reconnect once the Deck is free again).
- **Reconnecting depends on the Host.** A Host disconnected from its own side (for example from its
  Bluetooth menu) usually does not reconnect by itself; connect again from the Host's Bluetooth
  settings. While Controller Mode is on and no Host is connected, the Deck sends a connectable but
  non-discoverable advertisement so Paired Hosts can come back; other devices can connect to it but
  cannot pair outside Pairing Mode.
- **Throughput versus link stability.** A Bluetooth LE link carries about one report per connection
  interval, which the Host chooses. To keep input responsive, DeckPad asks Hosts for a 15-20 ms
  interval while Controller Mode is on and Pairing Mode is closed, and paces reports to the interval
  the Host actually uses, keeping only the latest state. On the tested Host this carried about 45
  reports/s. The trade-off: in 3 of 13 interval changes on that Host, the link dropped about 0.4 s later.
  A dropped link reconnected within about 3 s. The shorter interval is not requested during pairing,
  because a drop there cancels the pairing, so input during the first connection right after pairing is
  slower (about 18 reports/s) until the Host reconnects. Other Hosts may choose a different interval or
  refuse the request.
- **Bluetooth interruptions.** If Bluetooth restarts or is switched off while Controller Mode is on,
  Controller Mode waits up to 20 seconds and resumes by itself when Bluetooth comes back (the panel says
  "Bluetooth stopped. Controller Mode resumes as soon as it is back."). Switching Bluetooth off and on
  again within those 20 seconds therefore turns Controller Mode back on. If Bluetooth does not come
  back, Controller Mode turns off with an error. Pairing Mode does not survive an interruption; open it
  again.
- **Steam still sees the Deck's controls.** In Gaming Mode, whatever has focus on the Deck (the library,
  the Quick Access menu, or a running game) also reacts to the buttons, and the Steam and `…` buttons
  still open Steam's menus. While a Host is connected, select **Open Controller Screen** in the panel:
  it fills the screen and holds Steam's focus so the library behind it does not move. To leave it,
  press `…` and select **Close Controller Screen**, press the Steam button, or hold the Quit Combo
  (which also turns Controller Mode off). Do not run a game on the Deck while using it as a
  controller. Whether the screen absorbs every press, and whether these ways out work, has not been
  checked by a person since the first build on the Deck swallowed the Steam and `…` buttons.
- **Not sent:** rear buttons, trackpads, gyro, and rumble from the Host.
- **Paired Hosts appear in Steam's Bluetooth settings**, because they are ordinary Bluetooth pairings.
  Removing one there also removes it from DeckPad.
- **Upgrading from a build before fixed GATT handles.** A Host that paired with a pre-release DeckPad
  build from before GATT handles were fixed may keep a stale copy of the Deck's services and get no
  input after upgrading. Remove the Deck on the Host, select **Forget** in DeckPad, and pair again once.
  Restarting the Deck also clears it.
- **Pending checks:** suspend/resume with a Host connected, Bluetooth audio on the Deck while a Host is
  connected, the Controller Screen in Gaming Mode, and non-Linux Hosts have not been tested. See
  [Verification status](docs/verification.md) for the full list of open unknowns.

## What DeckPad changes on your Deck

DeckPad's backend **runs as root** (the Decky `root` flag). Root is needed for two things below; the rest
of DeckPad would work without it.

- **Controller Identity in bluetoothd's memory.** The Deck's Bluetooth service (`bluetoothd`) always
  publishes its own device information, which says "BlueZ" rather than "Xbox controller", and Hosts
  read it first. While Controller Mode is on, DeckPad overwrites the four DeviceID numbers inside the
  running `bluetoothd` process's memory (through `/proc/<pid>/mem`) so that Hosts read `045E:0B13`, and
  writes the original values back when Controller Mode turns off. No file is changed and Bluetooth is
  not restarted. DeckPad writes only if it finds the original value exactly once in `bluetoothd`'s own
  data, and otherwise leaves `bluetoothd` alone (Hosts then see a generic controller). If DeckPad is
  killed while the override is in place, it restores the value the next time it starts. While the
  override is active, any Bluetooth LE device that reads the Deck's device information sees the Xbox
  identity. The Deck's Classic Bluetooth identity, which headphones and keyboards see, does not change.
- **Bluetooth LE connection interval.** While Controller Mode is on (and Pairing Mode is closed), DeckPad
  sets the adapter's default LE connection interval to 15-20 ms through the kernel's Bluetooth
  management interface, and restores the previous value when Controller Mode turns off or after a crash.
  This also applies to other Bluetooth LE connections the Deck makes during that time.
- **Pairing agent.** While Controller Mode is on, DeckPad answers pairing requests that come from
  Hosts. It accepts them only while Pairing Mode is open, and lets only Hosts paired through DeckPad
  use the Deck's Bluetooth services without asking. Pairing you start from Steam's Bluetooth
  settings still goes through Steam as usual. When Controller Mode turns off, DeckPad unregisters its
  agent and Bluetooth hands pairing requests back to Steam.

Files DeckPad keeps, all under Decky's per-plugin directories:

| File | Contents |
|---|---|
| `~/homebrew/settings/DeckPad/paired_hosts.json` | Bluetooth addresses and names of the Hosts paired through DeckPad |
| `~/homebrew/settings/DeckPad/settings.json` | Whether the Quit Combo is on, once you have changed it |
| `~/homebrew/data/DeckPad/connection_interval.json` | The adapter's previous connection interval, only while DeckPad has changed it |
| `~/homebrew/logs/DeckPad/` | Decky's log files for DeckPad, and `diagnostics.txt` |

Uninstalling DeckPad from Decky's settings removes the Deck's pairings with the Hosts paired through
DeckPad, and only those: headphones, keyboards, and other devices you paired in Steam stay paired. It
also puts back bluetoothd's DeviceID and the adapter's connection interval if a crashed DeckPad left
them changed, and deletes `paired_hosts.json`, `settings.json`, `connection_interval.json`, and `diagnostics.txt`
(Decky's own log files for DeckPad stay). If Bluetooth is off or does not answer within a few seconds
during the uninstall, the pairings stay; remove them in Steam's Bluetooth settings. Each Host still
lists the Deck afterwards: remove it in the Host's Bluetooth settings.

## Troubleshooting

The DeckPad panel has a collapsed **Troubleshooting** section. Expanding it collects a diagnostics report
(DeckPad, dbus-fast, and Python versions, whether DeckPad runs as root, the Bluetooth service and
adapter state, the DeviceID override, connection intervals, Paired Hosts, controls availability, report
counters, recent errors, and recent log lines), shows a summary,
and offers a copy button. The full report is also saved to `~/homebrew/logs/DeckPad/diagnostics.txt`.
Please attach it when you [report an issue](https://github.com/thedavidweng/DeckPad/issues).

### Messages the panel can show

| Title | Message | What it means |
|---|---|---|
| Could not turn on Controller Mode | The Bluetooth service is not running. Restart the Deck, then try again. | `bluetoothd` is not available. |
| Could not turn on Controller Mode | No Bluetooth adapter was found on this Deck. | |
| Could not turn on Controller Mode | Bluetooth is turned off. Turn it on in Steam's Bluetooth settings, then try again. | |
| Could not turn on Controller Mode | Controller Mode could not start. Try again; if it keeps failing, restart the Deck. | BlueZ rejected a registration; details are in the diagnostics. |
| Pairing did not finish | The Deck could not become discoverable. Turn Controller Mode off and on, then try again. | |
| Pairing did not finish | No device paired in time. Select Pair a Device again, then pick this Deck in the other device's Bluetooth settings. | Pairing Mode's three minutes ran out. |
| Pairing did not finish | Pairing with *Host* did not finish. If this Deck is already listed in *Host*'s Bluetooth settings, remove it there, then select Pair a Device and try again. | Usually the Host still holds an old pairing with the Deck. |
| Controller Mode turned off | Bluetooth was turned off. Turn it on in Steam's Bluetooth settings, then turn Controller Mode on again. | Bluetooth stayed off for more than 20 seconds. |
| Controller Mode turned off | Bluetooth stopped working and did not come back. Turn Controller Mode on again; if it keeps happening, restart the Deck. | |
| Could not forget *Host* | Bluetooth did not remove the pairing. Try again; if it keeps failing, remove *Host* in Steam's Bluetooth settings. | |
| Could not disconnect *Host* | Try again, or turn Controller Mode off to disconnect every device. | |
| Paired devices cannot reconnect | The Deck could not start advertising to them. Turn Controller Mode off and on, then try again. | |
| No input from the Deck's controls | DeckPad cannot read the Deck's controls right now, so the connected device gets no input. DeckPad keeps trying; if this lasts, restart the Deck. | |

If the panel itself stops responding, reload DeckPad from Decky's settings.

### Common problems

- **The Host does not find the Deck.** Make sure Pairing Mode is open (the countdown is showing) and scan
  again on the Host. Some Hosts list Bluetooth LE devices only after a fresh scan.
- **The Host finds the Deck but pairing fails.** Remove the Deck from the Host's Bluetooth settings if it
  is listed there, then try again. Retrying also helps; the tested laptop sometimes failed to connect on
  the first attempts for reasons unrelated to DeckPad.
- **Connected but no input.** Check the Troubleshooting summary for controls availability and the report
  counters. If you used a DeckPad build from before the first store release, see the upgrade note under
  [Known limitations](#known-limitations).

## Development

- Backend tests run against a fake BlueZ on a private D-Bus and need `dbus-daemon` and Python 3.11 or
  newer: `pnpm test`. To match Decky's interpreter, run them under Python 3.11:
  `mise x python@3.11 -- pnpm test`.
- Frontend build: `pnpm i && pnpm build`. The store CI builds with Node 20, pnpm 9, and
  `pnpm i --frozen-lockfile`, then packages with the [Decky CLI](https://github.com/SteamDeckHomebrew/cli)
  (`decky plugin build`).
- Vendored Python modules and their versions: `py_modules/README.md`.
- Design decisions: `docs/adr/`. Vocabulary: `GLOSSARY.md`. Open unknowns: `docs/verification.md`.

## Acknowledgements

- [DeckJoy](https://github.com/Lucaber/deckjoy) by Lucaber showed that a Steam Deck can act as a
  controller for another device, and why Classic Bluetooth HID would need bluetoothd's input plugin
  disabled. DeckPad does not use DeckJoy's code.
- [DeckControllerOS](https://github.com/Zak-Bahm/DeckControllerOS) by Zak Bahm documented the Deck's
  controller reports and the pitfalls of running a Bluetooth LE HID peripheral on BlueZ. DeckPad does not
  include its code.
- [ESP32-BLE-CompositeHID](https://github.com/Mystfit/ESP32-BLE-CompositeHID) (MIT, Copyright (c) 2021
  lemmingDev) provides the Xbox Wireless Controller HID report descriptor that DeckPad uses.
- [dbus-fast](https://github.com/Bluetooth-Devices/dbus-fast) (MIT) is DeckPad's D-Bus library, bundled
  unmodified.
- CPython's `xml.etree` (PSF License) is bundled unmodified for Decky's Python, which lacks it.
- The Linux kernel's `hid-steam` driver and SDL's Xbox controller support were used as references for
  report layouts.
- [decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template) (BSD 3-Clause) by
  Steam Deck Homebrew is the starting point of this plugin, and
  [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) runs it.

DeckPad is not affiliated with Valve or Microsoft. Xbox is a trademark of Microsoft.

## License

DeckPad is licensed under the BSD 3-Clause License; see `LICENSE`, which also contains the
decky-plugin-template license. Bundled third-party software and its licenses are listed in
`THIRD_PARTY_NOTICES.md`.
