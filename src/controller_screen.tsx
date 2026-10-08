import { Focusable, GamepadButton, GamepadEvent, Navigation } from "@decky/ui";
import { useEffect, useRef, useState } from "react";
import { ControllerModeState, connectedHostName, useControllerModeState, useGamepadPreview } from "./backend";
import { GamepadOutline } from "./gamepad_outline";

export const CONTROLLER_SCREEN_ROUTE = "/deckpad/controller";

// Steam keeps reacting to the Deck's controls while they also go to the host. This screen holds
// Steam's focus on one element that consumes every button and direction Steam's UI navigation hands
// it, so the library or menus behind it do not move. While the quit combo is on, it also turns off the
// Steam and … buttons' menus with Steam's own switch, and the quit combo is the way out; otherwise
// those two buttons still open Steam's menus.

const STEAM_MENU_BUTTONS = new Set<number | undefined>([GamepadButton.STEAM_GUIDE, GamepadButton.STEAM_QUICK_MENU]);

const STEAM_MENU_HINTS_HIDDEN = { [GamepadButton.STEAM_GUIDE]: null, [GamepadButton.STEAM_QUICK_MENU]: null };

interface SteamMenuButtonsSwitch {
  DisableHomeAndQuickAccessButtons(): void;
  EnableHomeAndQuickAccessButtons(): void;
}

// The switch Steam's Test Device Inputs page uses. Not part of Decky's API; without it the buttons stay on.
function steamMenuButtonsSwitch(): SteamMenuButtonsSwitch | null {
  const store = (window as { SteamUIStore?: Partial<SteamMenuButtonsSwitch> }).SteamUIStore;
  return typeof store?.DisableHomeAndQuickAccessButtons === "function" &&
    typeof store?.EnableHomeAndQuickAccessButtons === "function"
    ? (store as SteamMenuButtonsSwitch)
    : null;
}

let steamMenusOff = false;

function setSteamMenusOff(off: boolean): boolean {
  const steamSwitch = steamMenuButtonsSwitch();
  if (!steamSwitch) return false;
  if (off !== steamMenusOff) {
    if (off) steamSwitch.DisableHomeAndQuickAccessButtons();
    else steamSwitch.EnableHomeAndQuickAccessButtons();
    steamMenusOff = off;
  }
  return steamMenusOff;
}

// Steam keeps the switch after DeckPad goes away, so turning the menus back on must never be skipped.
export function restoreSteamMenus() {
  setSteamMenusOff(false);
}

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
  // Only while controller mode is on; otherwise B goes back as usual.
  const capturing = state?.status === "on" || state?.status === "recovering";
  const [title, detail] = headline(state);
  const report = useGamepadPreview(capturing);
  const wantSteamMenusOff = capturing && state?.quit_combo === true;
  const [menusOff, setMenusOff] = useState(false);

  useEffect(() => {
    setMenusOff(setSteamMenusOff(wantSteamMenusOff));
    return () => {
      restoreSteamMenus();
      setMenusOff(false);
    };
  }, [wantSteamMenusOff]);

  useEffect(() => {
    setScreenOpen(true);
    return () => setScreenOpen(false);
  }, []);

  // Leave once controller mode turns off, for example through the quit combo.
  const wasCapturing = useRef(capturing);
  useEffect(() => {
    if (wasCapturing.current && !capturing && state !== null) Navigation.NavigateBack();
    wasCapturing.current = capturing;
  }, [capturing]);

  const consume = (evt: GamepadEvent | CustomEvent) => {
    if (!capturing) return;
    // Steam delivers these to the focused element too; cancelling them leaves the user with no way out.
    if (STEAM_MENU_BUTTONS.has(evt.detail?.button)) return;
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
      onOKActionDescription={capturing ? null : undefined}
      // Steam's footer takes its hints from the focused element first, and null hides one. With the
      // menus off, Steam's own "Menu" hint for the Steam button would point at nothing.
      actionDescriptionMap={menusOff ? STEAM_MENU_HINTS_HIDDEN : undefined}
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        // Clear Steam's header and footer, which overlay the route.
        padding: "40px 24px 48px",
        boxSizing: "border-box",
        gap: "8px",
      }}
    >
      <div style={{ fontSize: "20px", fontWeight: "bold" }}>{title}</div>
      <div style={{ fontSize: "14px", opacity: 0.8 }}>{detail}</div>
      <GamepadOutline report={report} />
      {capturing && (
        <div style={{ fontSize: "12px", opacity: 0.7, maxWidth: "720px" }}>
          {menusOff
            ? "Steam on this Deck ignores the controls while this screen is open, and the Steam and … buttons go to the connected device. To leave, hold Menu + View + L1 + R1 to turn off Controller Mode, or tap Close."
            : "Steam on this Deck ignores the controls while this screen is open. To leave, press the … button and select Close Controller Screen in DeckPad, or press the Steam button."}
          {!menusOff && state?.quit_combo && " Hold Menu + View + L1 + R1 to turn off Controller Mode and leave."}
        </div>
      )}
      {capturing && (
        // Touch only, so it does not take Steam's focus from the screen. Works without Steam's menus
        // or the backend.
        <div
          onClick={closeControllerScreen}
          style={{ fontSize: "14px", padding: "6px 24px", borderRadius: "4px", background: "rgba(255,255,255,0.1)" }}
        >
          Close
        </div>
      )}
    </Focusable>
  );
}
