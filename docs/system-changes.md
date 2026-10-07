# What DeckPad changes on your Deck

DeckPad's backend **runs as root** (the Decky `root` flag). Root is needed for the first two changes
below; the rest of DeckPad would work without it.

- **Controller Identity in bluetoothd's memory** ([ADR-0006](adr/0006-override-bluetoothd-deviceid-in-memory.md)).
  The Deck's Bluetooth service (`bluetoothd`) always publishes its own device information, which says
  "BlueZ" rather than "Xbox controller", and Hosts read it first. While Controller Mode is on, DeckPad
  overwrites the four DeviceID numbers inside the running `bluetoothd` process's memory (through
  `/proc/<pid>/mem`) so that Hosts read `045E:0B13`, and writes the original values back when Controller
  Mode turns off. No file is changed and Bluetooth is not restarted. DeckPad writes only if it finds the
  original value exactly once in `bluetoothd`'s own data, and otherwise leaves `bluetoothd` alone (Hosts
  then see a generic controller). If DeckPad is killed while the override is in place, it restores the
  value the next time it starts. While the override is active, any Bluetooth LE device that reads the
  Deck's device information sees the Xbox identity. The Deck's Classic Bluetooth identity, which
  headphones and keyboards see, does not change.
- **Bluetooth LE connection interval** ([ADR-0008](adr/0008-shorter-connection-interval-and-link-paced-reports.md)).
  While Controller Mode is on (and Pairing Mode is closed), DeckPad sets the adapter's default LE
  connection interval to 15-20 ms through the kernel's Bluetooth management interface, and restores the
  previous value when Controller Mode turns off or after a crash. This also applies to other Bluetooth
  LE connections the Deck makes during that time.
- **Pairing agent** ([ADR-0005](adr/0005-borrow-default-pairing-agent.md)). While Controller Mode is on,
  DeckPad answers pairing requests that come from Hosts. It accepts them only while Pairing Mode is
  open, and lets only Hosts paired through DeckPad use the Deck's Bluetooth services without asking.
  Pairing you start from Steam's Bluetooth settings still goes through Steam as usual. When Controller
  Mode turns off, DeckPad unregisters its agent and Bluetooth hands pairing requests back to Steam.

## Files

All under Decky's per-plugin directories:

| File | Contents |
|---|---|
| `~/homebrew/settings/DeckPad/paired_hosts.json` | Bluetooth addresses and names of the Hosts paired through DeckPad |
| `~/homebrew/settings/DeckPad/settings.json` | Whether the Quit Combo is on, once you have changed it |
| `~/homebrew/data/DeckPad/connection_interval.json` | The adapter's previous connection interval, only while DeckPad has changed it |
| `~/homebrew/logs/DeckPad/` | Decky's log files for DeckPad, and `diagnostics.txt` |

## Uninstalling

Uninstalling DeckPad from Decky's settings removes the Deck's pairings with the Hosts paired through
DeckPad, and only those: headphones, keyboards, and other devices you paired in Steam stay paired. It
also puts back bluetoothd's DeviceID and the adapter's connection interval if a crashed DeckPad left
them changed, and deletes `paired_hosts.json`, `settings.json`, `connection_interval.json`, and
`diagnostics.txt` (Decky's own log files for DeckPad stay). If Bluetooth is off or does not answer
within a few seconds during the uninstall, the pairings stay; remove them in Steam's Bluetooth
settings. Each Host still lists the Deck afterwards: remove it in the Host's Bluetooth settings.
