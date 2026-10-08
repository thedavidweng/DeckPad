import { addEventListener, callable, removeEventListener } from "@decky/api";
import { useEffect, useState } from "react";

export type Status = "off" | "starting" | "on" | "stopping" | "recovering";

export interface ControllerModeError {
  code: string;
  title: string;
  message: string;
  detail: string | null;
}

export interface ControlsState {
  available: boolean;
  message: string | null;
}

export type PairingStatus = "closed" | "discoverable" | "pairing" | "paired" | "failed";

export interface PairingState {
  status: PairingStatus;
  name: string | null;
  seconds_left: number | null;
  host: { address: string; name: string | null } | null;
  error: ControllerModeError | null;
}

export interface PairedHost {
  address: string;
  name: string | null;
  connected: boolean;
}

export type ConnectionStatus = "idle" | "waiting" | "connected" | "paused";

export interface ControllerModeState {
  enabled: boolean;
  status: Status;
  error: ControllerModeError | null;
  pairing: PairingState;
  hosts: PairedHost[];
  connection: ConnectionStatus;
  controls: ControlsState | null;
  quit_combo: boolean;
}

const STATE_EVENT = "controller_mode_state";

const getState = callable<[], ControllerModeState>("get_state");
export const setControllerMode = callable<[enabled: boolean], ControllerModeState>("set_controller_mode");
export const setPairingMode = callable<[enabled: boolean], ControllerModeState>("set_pairing_mode");
export const disconnectHost = callable<[address: string], ControllerModeState>("disconnect_host");
export const forgetHost = callable<[address: string], ControllerModeState>("forget_host");
export const allowReconnect = callable<[], ControllerModeState>("allow_reconnect");
export const setQuitCombo = callable<[enabled: boolean], ControllerModeState>("set_quit_combo");

// Sticks run from -1 to 1 with Y pointing down; triggers from 0 to 1.
export interface GamepadPreview {
  buttons: string[];
  left_stick: [number, number];
  right_stick: [number, number];
  left_trigger: number;
  right_trigger: number;
}

const GAMEPAD_EVENT = "gamepad_report";
const watchGamepad = callable<[enabled: boolean], void>("watch_gamepad");

// Holds the latest payload of `event` while `active`. `subscribed` runs once the listener is in place
// and may return its own cleanup.
function useBackendEvent<T>(
  event: string,
  active: boolean,
  subscribed: (set: (value: T | null) => void) => (() => void) | void,
): T | null {
  const [value, setValue] = useState<T | null>(null);

  useEffect(() => {
    if (!active) {
      setValue(null);
      return;
    }
    const listener = addEventListener<[T]>(event, setValue);
    const cleanup = subscribed(setValue);
    return () => {
      removeEventListener(event, listener);
      cleanup?.();
    };
  }, [event, active]);

  return value;
}

// The backend only forwards reports while someone watches, so keep watching just as long as `active`.
export function useGamepadPreview(active: boolean): GamepadPreview | null {
  return useBackendEvent<GamepadPreview>(GAMEPAD_EVENT, active, () => {
    watchGamepad(true).catch(() => {});
    return () => watchGamepad(false).catch(() => {});
  });
}

export function useControllerModeState(): ControllerModeState | null {
  return useBackendEvent<ControllerModeState>(STATE_EVENT, true, (set) => {
    getState().then(set).catch(() => set(null));
  });
}

// Hosts whose name Bluetooth has not learned yet get a numbered placeholder instead of an address.
export function hostNames(hosts: PairedHost[]): Map<string, string> {
  const names = new Map<string, string>();
  let unnamed = 0;
  for (const host of hosts) {
    if (host.name) {
      names.set(host.address, host.name);
    } else {
      unnamed += 1;
      names.set(host.address, unnamed === 1 ? "Unnamed device" : `Unnamed device ${unnamed}`);
    }
  }
  return names;
}

// The backend keeps only one host connected at a time.
export function connectedHostName(hosts: PairedHost[], names: Map<string, string>): string | undefined {
  const host = hosts.find((h) => h.connected);
  return host && names.get(host.address);
}
