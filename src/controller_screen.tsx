import { Focusable, GamepadEvent, Navigation } from "@decky/ui";
import { useEffect, useState } from "react";
import { FaGamepad } from "react-icons/fa";
import { ControllerModeState, connectedHostName, useControllerModeState } from "./backend";

export const CONTROLLER_SCREEN_ROUTE = "/deckpad/controller";

// Steam keeps reacting to the Deck's controls while they also go to the Host (ADR-0003). This screen
// holds Steam's focus on one element that consumes every button and direction Steam's UI navigation
// hands it, so the library or menus behind it do not move. The Steam and Quick Access buttons are
// handled by Steam itself and still work, which is how the user leaves.

let screenOpen = false;
const openListeners = new Set<(open: boolean) => void>();

function setScreenOpen(open: boolean) {
  screenOpen = open;
  openListeners.forEach((listener) => listener(open));
}

export function useControllerScreenOpen(): boolean {
  const [open, setOpen] = useState(screenOpen);
  useEffect(() => {
    openListeners.add(setOpen);
    return () => {
      openListeners.delete(setOpen);
    };
  }, []);
  return open;
}

export function openControllerScreen() {
  Navigation.Navigate(CONTROLLER_SCREEN_ROUTE);
  Navigation.CloseSideMenus();
}

export function closeControllerScreen() {
  Navigation.NavigateBack();
  Navigation.CloseSideMenus();
}

function headline(state: ControllerModeState | null): [string, string] {
  if (!state) return ["DeckPad", "Connecting to the DeckPad backend…"];
  if (state.status === "recovering") return ["Waiting for Bluetooth", "Controller Mode resumes as soon as it is back."];
  if (state.status !== "on") return ["Controller Mode is off", "Press B to go back."];
  if (state.connection === "connected") {
    return [`Connected to ${connectedHostName(state) ?? "a paired device"}`, "Your controls are going to this device."];
  }
  if (state.connection === "paused") return ["Disconnected", "Allow reconnecting in DeckPad's panel."];
  return ["Waiting for a paired device", "It reconnects on its own, or connect to this Deck from its Bluetooth settings."];
}

export function ControllerScreen() {
  const state = useControllerModeState();
  // Only while Controller Mode is on: otherwise B goes back as usual.
  const capturing = state?.status === "on" || state?.status === "recovering";
  const [title, detail] = headline(state);

  useEffect(() => {
    setScreenOpen(true);
    return () => setScreenOpen(false);
  }, []);

  const consume = (evt: GamepadEvent | CustomEvent) => {
    if (!capturing) return;
    evt.preventDefault();
    evt.stopPropagation();
  };

  return (
    <Focusable
      // Steam's gamepad navigation sends button and direction events to the focused element first.
      autoFocus
      preferredFocus
      noFocusRing
      onButtonDown={consume}
      onGamepadDirection={consume}
      onOKButton={consume}
      onCancelButton={consume}
      onCancel={consume}
      onSecondaryButton={consume}
      onOptionsButton={consume}
      onMenuButton={consume}
      onCancelActionDescription={capturing ? null : undefined}
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        padding: "40px 24px",
        boxSizing: "border-box",
        gap: "16px",
      }}
    >
      <FaGamepad size={72} />
      <div style={{ fontSize: "28px", fontWeight: "bold" }}>{title}</div>
      <div style={{ fontSize: "18px", opacity: 0.8 }}>{detail}</div>
      {capturing && (
        <div style={{ fontSize: "16px", opacity: 0.7, maxWidth: "640px" }}>
          Steam on this Deck ignores the controls while this screen is open. To leave, press the … button and
          select Close Controller Screen in DeckPad, or press the Steam button.
        </div>
      )}
    </Focusable>
  );
}
