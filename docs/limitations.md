# Known limitations

- **One Host at a time.** With several Paired Hosts in range, the first one to connect wins; DeckPad
  cannot choose which one reconnects. If you pair another Host while one is connected, the newly paired
  Host takes over and the previous one is disconnected (it can reconnect once the Deck is free again).
- **Reconnecting depends on the Host.** A Host disconnected from its own side usually does not reconnect
  by itself; connect again from the Host's Bluetooth settings. While Controller Mode is on and no Host is
  connected, the Deck sends a connectable but non-discoverable advertisement so Paired Hosts can come
  back ([ADR-0007](adr/0007-reconnect-with-a-connectable-non-discoverable-advertisement.md)); other
  devices can connect to it but cannot pair outside Pairing Mode.
- **Throughput versus link stability** ([ADR-0008](adr/0008-shorter-connection-interval-and-link-paced-reports.md)).
  A Bluetooth LE link carries about one report per connection interval, which the Host chooses. DeckPad
  asks Hosts for a 15-20 ms interval while Controller Mode is on and Pairing Mode is closed, and paces
  reports to the interval the Host actually uses, keeping only the latest state. Changing the interval
  sometimes drops the link once; it reconnects within a few seconds. The shorter interval is not
  requested during pairing, because a drop there cancels the pairing, so input during the first
  connection right after pairing is slower until the Host reconnects. Hosts may refuse the request.
- **Bluetooth interruptions** ([ADR-0009](adr/0009-resume-controller-mode-when-bluetooth-comes-back.md)).
  If Bluetooth restarts or is switched off while Controller Mode is on, Controller Mode waits up to 20
  seconds and resumes by itself when Bluetooth comes back. Switching Bluetooth off and on again within
  those 20 seconds therefore turns Controller Mode back on. If Bluetooth does not come back, Controller
  Mode turns off with an error. Pairing Mode does not survive an interruption; open it again.
- **Steam still sees the Deck's controls** ([ADR-0011](adr/0011-controller-screen-route.md)). In Gaming
  Mode, whatever has focus on the Deck also reacts to the buttons. The Controller Screen holds Steam's
  focus so the library behind it does not move, and while the Quit Combo is on it also stops the Steam
  and `…` buttons from opening Steam's menus ([ADR-0014](adr/0014-turn-off-steams-menu-buttons-on-the-controller-screen.md)).
  With the Quit Combo turned off, those buttons open Steam's menus as usual: press `…` and select
  **Close Controller Screen**, or press the Steam button. A game running on the Deck still receives the
  controls, so do not run one while using the Deck as a controller.
- **Not sent:** rear buttons, trackpads, gyro, and rumble from the Host.
- **Paired Hosts appear in Steam's Bluetooth settings**, because they are ordinary Bluetooth pairings.
  Removing one there also removes it from DeckPad.
