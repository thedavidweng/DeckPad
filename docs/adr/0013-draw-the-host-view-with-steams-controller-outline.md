# Draw what the Host receives with Steam's own Xbox controller outline

The Controller Screen (ADR-0011) shows a drawing of an Xbox controller in the middle of the screen and lights up what the Host is receiving, like a web gamepad tester. DeckPad does not draw the controller itself: Steam's icons module, the one its **Test Device Inputs** page draws with, exports `XboxOneControllerFrontOutline` and outlines for other controllers, and `@decky/ui` already finds that module as `IconsModule`. The component takes a `highlight…` prop per button, D-pad direction and trigger, and stick positions from -1 to 1 with Y pointing down. It matches the Controller Identity (ADR-0002) and Steam's own styling. If a Steam update removes it, the screen falls back to a plain icon.

The drawing follows the Gamepad Reports handed to the Host, not the Deck Controls or Steam's view of them. So the rear buttons and trackpads, which the Host never gets (ADR-0002), never light up, and the Quit Combo shows as nothing held. While a Controller Screen watches (`watch_gamepad`), the backend forwards the latest report as a `gamepad_report` event, described as button names, stick positions and trigger amounts, at most 30 times a second. Reports go out at the link's pace, about 50 a second (ADR-0008), and every event crosses Decky's websocket into Steam's UI process, so the preview is throttled and stops when the screen closes. The drawing only lights a trigger on or off, so a bar under it shows how far each trigger is pulled.

## Considered Options

- **Open Steam's Test Device Inputs page (`/controller/devicesupport/<index>`) instead of a DeckPad route.** Rejected: it is a step-by-step test that moves on once every button has been pressed, it can only be left by holding B (which also goes to the Host), it draws the Deck and lights controls the Host never gets, and it starts Steam's controller device support flow, whose side effects are unknown.
- **Read Steam's controller state in the frontend (`SteamClient.Input.RegisterForControllerStateChanges`).** Rejected: it is Steam's view, not the Host's, and its counterpart `UnregisterForControllerStateChanges` takes no handle, so it could unregister Steam's own listener.
- **Draw a controller in DeckPad's own SVG.** Rejected: more to maintain, and it would not match Steam's look.

## Consequences

- `XboxOneControllerFrontOutline` and its props are Steam internals, read from Steam's client bundle in October 2026. A Steam update can rename or change them; the screen then shows the plain icon or a drawing that no longer lights up, and the controls still reach the Host.
- Checked on the Deck in Gaming Mode (SteamOS 3.8.28) through Steam's CEF debugger: the outline renders with Steam's styling, a fixed test report lights the expected buttons, D-pad directions and stick positions, and real reports reach the screen. At rest the sticks' noise changes the report constantly, so the screen gets close to the full 30 events a second even with nothing pressed. Pressing the Deck's own buttons with the screen open still needs a person (U4 in [Verification status](../verification.md)).
