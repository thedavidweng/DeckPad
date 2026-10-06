# Let Paired Hosts reconnect through a connectable, non-discoverable advertisement, and pause it after Disconnect

A Paired Host reconnects over LE only when its Peripheral advertises. Outside Pairing Mode, while Controller Mode is on and no Paired Host is connected, DeckPad therefore registers its advertisement with `Discoverable` false. Hosts leave the Deck out of their scan lists, but a Host that holds a bond with the Deck's public address still connects to it on its own. The advertisement is withdrawn as soon as a Paired Host connects, because a connectable advertisement during a connection can make the controller drop the link, and comes back when the link drops. Pairing Mode re-registers the same object with `Discoverable` true, and the reconnect form returns when Pairing Mode stops accepting Hosts.

BlueZ's D-Bus API has no directed advertising, so DeckPad cannot pick which Paired Host reconnects; whichever one is in range and wants the Deck wins. A Linux Host reconnects by itself after the Deck drops the link, so the panel's Disconnect would be undone within seconds. Disconnect therefore also pauses the reconnect advertisement until the user selects "Allow Reconnecting" or Controller Mode starts again.

## Considered Options

- **Advertise only during Pairing Mode** (the #4 behaviour). Rejected: a returning user would have to open Pairing Mode each time, which is the first-time setup the ticket asks to avoid.
- **Directed advertising to the last Host.** Not offered by `LEAdvertisingManager1`. Driving HCI directly would mean bypassing bluetoothd.
- **Block a disconnected Host with `Device1.Blocked`.** Rejected: it changes persistent bluetoothd state, which would have to be undone after a crash, and it affects Steam's view of that device.

## Consequences

- While waiting, any LE central can connect to the Deck. A device that is not a Paired Host cannot pair, because DeckPad's agent refuses outside Pairing Mode (ADR-0005), and HID reads need encryption.
- A Host that the user disconnected on the Host side (for example with `bluetoothctl disconnect`) typically does not reconnect by itself. The user connects again from the Host's Bluetooth settings, which works because the advertisement is up.
- With several Paired Hosts in range, the first one to connect becomes the Connected Host. Supporting several simultaneous Hosts is out of scope.
- A second Host can only connect while one is connected through Pairing Mode's advertisement. DeckPad keeps one Connected Host: the Host that connects or finishes pairing last takes over, and the previous one is disconnected (without pausing reconnects).
