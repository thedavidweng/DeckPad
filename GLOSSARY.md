# DeckPad

DeckPad turns a Steam Deck into a Bluetooth game controller for another device, operated from a Decky plugin in Gaming Mode.

## Roles

**Host**:
The device that the Deck acts as a controller for, such as a PC, phone, tablet, or TV. It pairs with the Deck through its own normal Bluetooth settings.
_Avoid_: target, client, receiver, central

**Peripheral**:
A device that offers input to a Host. In Controller Mode, the Deck is the Peripheral.
_Avoid_: server, slave

**Paired Host**:
A Host that has completed pairing with the Deck and can reconnect without pairing again.
_Avoid_: bonded device, known device, trusted device

**Connected Host**:
A Paired Host with a live link to the Deck that is currently receiving Gamepad Reports.

## Modes

**Controller Mode**:
The user-enabled state in which the Deck acts as a Peripheral and sends its controls to a Connected Host. Turning it off returns the Deck to ordinary SteamOS behaviour.
_Avoid_: gamepad mode, HID mode, peripheral mode

**Pairing Mode**:
A time-limited sub-state of Controller Mode in which new Hosts can discover the Deck and pair with it.
_Avoid_: discoverable mode, scan mode

**Controller Screen**:
DeckPad's full-screen page on the Deck, opened from the panel while a Host is connected. It holds Steam's focus so Steam's UI does not react to the Deck Controls going to the Host.
_Avoid_: overlay, lock screen

## Input and output

**Deck Controls**:
The Deck's physical inputs. Core: face buttons, D-pad, sticks, triggers, bumpers, View/Menu/Steam buttons. Secondary: trackpads, rear buttons, gyro.
_Avoid_: Deck input, buttons (for the whole set)

**Deck State Report**:
One raw snapshot of every Deck Control, as produced by the Deck's built-in controller.

**Gamepad Report**:
One snapshot of the controller state in the form the Controller Identity defines, sent to the Connected Host.
_Avoid_: HID packet, frame

**Controller Identity**:
The controller model the Deck presents itself as to a Host. It determines how the Host recognises the controller and how it interprets Gamepad Reports.
_Avoid_: profile, persona, emulated device
