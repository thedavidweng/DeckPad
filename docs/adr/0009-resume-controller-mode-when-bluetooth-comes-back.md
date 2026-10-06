# Resume Controller Mode by itself when Bluetooth comes back underneath it

When bluetoothd exits or restarts (`systemctl restart bluetooth`), or the adapter is switched off (Steam's Bluetooth toggle) or disappears, every registration DeckPad holds becomes meaningless: bluetoothd forgets the application, advertisement and agent, and a powered-off adapter carries no links. DeckPad notices this through a separate bus connection (`BluetoothWatch`: `NameOwnerChanged` for `org.bluez`, `Adapter1.Powered` turning false, or the adapter's `InterfacesRemoved`). It then drops the whole session, shows Controller Mode as `recovering`, and starts a fresh session as soon as a start succeeds, retrying every second for up to 20 s. If Bluetooth does not come back in time, Controller Mode turns off with an error that says what to do (`bluetooth_turned_off` or `bluetooth_stopped`). The user can turn Controller Mode off while it waits.

bluetoothd also unregisters every device object, keeping the bonds, when it exits or loses the adapter. A removed Paired Host is therefore forgotten only if, half a second later, a running bluetoothd with its adapter no longer holds a pairing with it. Without that check a Bluetooth restart would silently drop every Paired Host from DeckPad's list.

## Considered Options

- **Turn Controller Mode off with an error at once.** Simpler, but a Bluetooth restart (which SteamOS and users do) would make a working Controller Mode stop for good, although nothing is wrong with it afterwards.
- **Re-register only what bluetoothd lost, keeping the Peripheral object.** Rejected: the Peripheral's device cache, advertisement state, and DeviceID override all refer to the old bluetoothd. A fresh session is the path that is already tested.
- **Wait for Bluetooth indefinitely.** Rejected: a user who switched Bluetooth off in Steam would see Controller Mode stay on with nothing happening.

## Consequences

- Hardware: after `systemctl restart bluetooth` Controller Mode was back on in about 1 s, and the Paired Host reconnected within 2-15 s with reports reaching it. Switching the adapter off for 3 s resumed it; leaving it off turned Controller Mode off with `bluetooth_turned_off`.
- Switching Bluetooth off and on again within 20 s in Steam's settings resumes Controller Mode, which the user may not expect. The panel shows "Bluetooth stopped. Controller Mode resumes as soon as it is back." in the meantime.
- Pairing Mode does not survive a recovery; it is closed, and the user opens it again.
