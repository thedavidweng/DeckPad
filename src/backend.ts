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

export function useControllerModeState(): ControllerModeState | null {
  const [state, setState] = useState<ControllerModeState | null>(null);

  useEffect(() => {
    const listener = addEventListener<[ControllerModeState]>(STATE_EVENT, setState);
    getState().then(setState).catch(() => setState(null));
    return () => {
      removeEventListener(STATE_EVENT, listener);
    };
  }, []);

  return state;
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

// The backend keeps one Connected Host at a time.
export function connectedHostName(state: ControllerModeState): string | null {
  const host = state.hosts.find((h) => h.connected);
  return host ? (hostNames(state.hosts).get(host.address) ?? null) : null;
}
