# Troubleshooting

## Diagnostics

The DeckPad panel has a collapsed **Troubleshooting** section. Expanding it collects a diagnostics report
(DeckPad, dbus-fast, and Python versions, whether DeckPad runs as root, the Bluetooth service and
adapter state, the DeviceID override, connection intervals, Paired Hosts, controls availability, report
counters, recent errors, and recent log lines), shows a summary, and offers a copy button. The full
report is also saved to `~/homebrew/logs/DeckPad/diagnostics.txt`. Please attach it when you
[report an issue](https://github.com/thedavidweng/DeckPad/issues).

If the panel itself stops responding, reload DeckPad from Decky's settings.

## Common problems

- **The Host does not find the Deck.** Make sure Pairing Mode is open (the countdown is showing) and scan
  again on the Host. Some Hosts list Bluetooth LE devices only after a fresh scan.
- **The Host finds the Deck but pairing fails.** Remove the Deck from the Host's Bluetooth settings if it
  is listed there, then try again. Retrying also helps; some Hosts fail the first attempts for reasons
  unrelated to DeckPad.
- **Connected but no input.** Check the Troubleshooting summary for controls availability and the report
  counters. A Host that paired with a pre-release build from before GATT handles were fixed
  ([ADR-0010](adr/0010-register-gatt-services-at-fixed-handles.md)) may keep a stale copy of the Deck's
  services: remove the Deck on the Host, select **Forget** in DeckPad, and pair again once. Restarting
  the Deck also clears it.
- **A Host does not reconnect by itself.** A Host disconnected from its own side (for example from its
  Bluetooth menu) usually does not reconnect by itself; connect again from the Host's Bluetooth settings.

## Messages the panel can show

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
