# Turn off the Steam and … buttons' menus on the Controller Screen while the Quit Combo is on

The Steam and `…` buttons go to the Host as Xbox and Share (ADR-0002), but on the Deck they also open Steam's menus over the Controller Screen. Steam has a switch for this: `window.SteamUIStore.DisableHomeAndQuickAccessButtons()` and `EnableHomeAndQuickAccessButtons()`. Steam's own Test Device Inputs page and its error screen use it, and while it is off Steam's handlers for those two buttons return early. The Controller Screen turns the menus off while Controller Mode is on or recovering and the Quit Combo (ADR-0012) is on, and turns them back on when it closes, when either condition ends, and when the plugin is dismounted.

That removes the ways out ADR-0011 relied on, so the screen keeps two others: the Quit Combo, which the backend reads from hidraw and which closes the screen once Controller Mode is off, and a **Close** button that only responds to touch, so it does not take Steam's focus and works even if the backend stops answering. With the Quit Combo turned off, the menus stay on, because the Quit Combo would no longer be there to get out.

While the menus are off, the screen also hides Steam's footer hints for the two buttons. Steam builds the footer from the focused element's `actionDescriptionMap` first, and a `null` entry hides a hint, the way Steam's own pages hide theirs. Otherwise the footer would keep offering the Steam button's "Menu", as Steam's own Test Device Inputs page does (steam-for-linux#11504). The A hint is hidden too while Controller Mode is on, because A goes to the Host and selects nothing.

## Considered Options

- **Keep the Steam and `…` buttons opening Steam's menus (ADR-0011 as it was).** Rejected by the user: every press of Xbox or Share on the Host also opened a menu on the Deck.
- **Turn the menus off whatever the Quit Combo setting.** Rejected: with the combo off, only the touchscreen would be left as a way out.

## Consequences

- The switch is one flag, not a counter. If Steam's own error screen turns it off while the Controller Screen is open, closing the screen turns it back on underneath that error screen.
- On the Deck (SteamOS 3.8.28) `SteamUIStore` has both functions, opening the screen with Controller Mode on turns the menus off (`BHomeAndQuickAccessButtonsEnabled()` is false), and they are back on after Decky restarts.
- On the Deck, a person pressing the Steam and `…` buttons with the screen open got no menu. The menus came back after **Close** (a touch tap), after the Quit Combo, after Controller Mode was turned off from the panel, and after the Quit Combo setting was switched off with the screen open.
- On the Deck the footer is empty while the menus are off, shows the Steam button's hint again when the Quit Combo setting is switched off, and is unchanged in the library.
- Whether Steam's chords on the Steam button (holding it, Steam + B) still work while the screen is open has not been checked (U4 in [Verification status](../verification.md)).
