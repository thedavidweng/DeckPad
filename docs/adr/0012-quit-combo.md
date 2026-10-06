# Leave Controller Mode with Moonlight's quit combo, read from the Deck Controls

On the Deck, the first build of the Controller Screen (ADR-0011) also swallowed the Steam and `…` buttons, so the user had no way out. That is fixed, but the only exits still depend on Steam's UI responding. DeckPad therefore adds a **Quit Combo**: holding Menu + View + L1 + R1, and no other button or D-pad direction, turns Controller Mode off. That stops the session, disconnects the Host, and the Controller Screen navigates back on its own once Controller Mode is off.

The combo is detected in the backend, on the Gamepad Reports built from the Deck State Reports DeckPad already reads from hidraw (ADR-0003), not in the frontend. So it works even when Steam's focus or UI is stuck. When the combo appears, the Host gets one report with nothing held, sent at once rather than paced, and never the combo itself. Then Controller Mode turns off. Sticks and triggers do not count towards the match.

The combo is on by default. A **Quit Combo** toggle in the panel's Settings section turns it off for games on the Host that need that combination; while it is off, the combo goes to the Host like any other press. The choice is kept in `settings.json` in Decky's settings directory and deleted on uninstall.

## Considered Options

- **Moonlight's combo, Start + Select + L1 + R1 (chosen).** Moonlight is the closest precedent: it also forwards a local controller to another machine and needs a local way out. It matches exactly these four buttons, and after a match sends the Host a state with nothing held (`moonlight-qt` `app/streaming/input/gamepad.cpp`). Moonlight later added `NO_GAMEPAD_QUIT=1` because a game needed the combo (moonlight-qt#870); DeckPad's toggle serves the same purpose.
- **Select + Start (EmuDeck's "stop emulation").** Rejected: two buttons are too easy to press in a game on the Host.
- **L1 + R1 + L3 + R3 (chiaki-ng's stream menu).** Rejected: chiaki-ng users report pressing it by accident in games (chiaki-ng#549), and Moonlight's combo is the more widely known exit.
- **Any combination with the Steam or `…` button.** Rejected: SteamOS owns those chords (for example, holding Steam + B force-quits a game).
- **Only close the Controller Screen and keep Controller Mode on.** Rejected by the user in favour of matching Moonlight, where the combo ends the session.

## Consequences

- The Host sees the combo's buttons go down one by one before the last one completes it, as with Moonlight, and then a report with nothing held before the link drops.
- Whether the combo works on the Deck in Gaming Mode, and whether Steam reacts to it before the Controller Screen closes, needs a person holding the Deck (U4 in [Verification status](../verification.md)).
