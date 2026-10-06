# Absorb the Deck's navigation with a full-screen Controller Screen route

DeckPad reads Deck Controls alongside Steam (ADR-0003), so Steam's UI on the Deck reacts to the same presses that go to the Host. DeckPad registers a Decky route, `/deckpad/controller`, through `routerHook.addRoute` when the plugin loads, and removes it when the plugin is dismounted. While a Host is connected, the panel offers **Open Controller Screen**, which navigates to the route and closes the Quick Access menu. The screen is one `Focusable` that takes Steam's focus and consumes every button and direction event Steam's gamepad navigation delivers to it, including B, so the library behind it does not move. It does so only while Controller Mode is on or recovering; otherwise B goes back as usual.

Steam delivers the Steam and `…` buttons (`STEAM_GUIDE` and `STEAM_QUICK_MENU`) to the focused element like any other button, and cancelling them stops Steam from opening its menus. The first build on the Deck did that and trapped the user. The screen therefore lets those two buttons through. That is how the user leaves: press `…` and select **Close Controller Screen** in DeckPad's panel (it navigates back), or press the Steam button. The Quit Combo (ADR-0012) is a way out that does not depend on Steam's UI.

## Considered Options

- **Only document "do not use the Deck's UI while in Controller Mode".** Rejected as the only answer: A and the D-pad would still launch and move things in the library.
- **Open the screen automatically when a Host connects.** Rejected for now: it would take the screen away from whatever the user is doing on the Deck without asking. It can be revisited once the manual check shows the screen works.
- **Run DeckPad as a Steam game so it owns the controller (DeckJoy's approach).** Rejected in ADR-0003.

## Consequences

- On the Deck the route is registered with Decky's router (checked in Desktop Mode through `routerHook.routerState`). Whether the screen absorbs every press in Gaming Mode, and whether the Steam and `…` buttons still get the user out, needs a person holding the Deck (U4 in [Verification status](../verification.md)).
- A running game on the Deck still receives the controls, because the screen only holds Steam's UI focus. The README keeps advising not to run a game while using the Deck as a controller.
- The screen follows `controller_mode_state` like the panel, so it shows "Connected to *Host*", "Waiting for a paired device" or the recovering message.
