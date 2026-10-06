import { ButtonItem, Field, PanelSection, PanelSectionRow, ToggleField, staticClasses } from "@decky/ui";
import { addEventListener, callable, definePlugin, removeEventListener } from "@decky/api";
import { useEffect, useState } from "react";
import { FaGamepad } from "react-icons/fa";

type Status = "off" | "starting" | "on" | "stopping";

interface ControllerModeError {
  code: string;
  message: string;
  detail: string | null;
}

type PairingStatus = "closed" | "discoverable" | "pairing" | "paired" | "failed";

interface PairingState {
  status: PairingStatus;
  name: string | null;
  seconds_left: number | null;
  host: { address: string; name: string } | null;
  error: ControllerModeError | null;
}

interface ControllerModeState {
  enabled: boolean;
  status: Status;
  error: ControllerModeError | null;
  pairing: PairingState;
}

const STATE_EVENT = "controller_mode_state";

const getState = callable<[], ControllerModeState>("get_state");
const setControllerMode = callable<[enabled: boolean], ControllerModeState>("set_controller_mode");
const setPairingMode = callable<[enabled: boolean], ControllerModeState>("set_pairing_mode");

const DESCRIPTIONS: Record<Status, string> = {
  off: "Turn on to use this Deck as a Bluetooth controller for another device.",
  starting: "Turning on…",
  on: "This Deck is acting as a Bluetooth controller. Turn off to return to normal.",
  stopping: "Turning off…",
};

function useControllerModeState(): ControllerModeState | null {
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

// The backend reports the time left when the state changes; count down locally in between.
function useCountdown(secondsLeft: number | null): number | null {
  const [left, setLeft] = useState(secondsLeft);

  useEffect(() => {
    setLeft(secondsLeft);
    if (secondsLeft === null) return;
    const started = Date.now();
    const timer = setInterval(() => {
      setLeft(Math.max(0, secondsLeft - Math.floor((Date.now() - started) / 1000)));
    }, 1000);
    return () => clearInterval(timer);
  }, [secondsLeft]);

  return left;
}

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

function PairingRows({ pairing, onRequestError }: { pairing: PairingState; onRequestError: () => void }) {
  const left = useCountdown(pairing.seconds_left);
  const deckName = pairing.name ?? "this Deck";
  const hostName = pairing.host?.name ?? "the other device";

  const request = async (enabled: boolean) => {
    try {
      await setPairingMode(enabled);
    } catch {
      onRequestError();
    }
  };

  const action = (label: string, enabled: boolean, description?: string) => (
    <PanelSectionRow>
      <ButtonItem layout="below" description={description} onClick={() => request(enabled)}>
        {label}
      </ButtonItem>
    </PanelSectionRow>
  );

  switch (pairing.status) {
    case "discoverable":
      return (
        <>
          <PanelSectionRow>
            <Field
              label="Waiting for a device to pair…"
              description={
                `On the other device, open its Bluetooth settings and select "${deckName}".` +
                (left !== null ? ` Pairing ends in ${formatDuration(left)}.` : "")
              }
              focusable
            />
          </PanelSectionRow>
          {action("Cancel Pairing", false)}
        </>
      );
    case "pairing":
      return (
        <>
          <PanelSectionRow>
            <Field
              label={`Pairing with ${hostName}…`}
              description={`If ${hostName} asks to confirm, accept it there.`}
              focusable
            />
          </PanelSectionRow>
          {action("Cancel Pairing", false)}
        </>
      );
    case "paired":
      return (
        <>
          <PanelSectionRow>
            <Field
              label={`Paired with ${hostName}`}
              description={`${hostName} now lists this Deck as a game controller.`}
              focusable
            />
          </PanelSectionRow>
          {action("Pair Another Device", true)}
        </>
      );
    case "failed":
      return (
        <>
          <PanelSectionRow>
            <Field label="Pairing did not finish" description={pairing.error?.message} focusable />
          </PanelSectionRow>
          {action("Try Again", true)}
        </>
      );
    default:
      return action("Pair a Device", true, "Make this Deck visible in another device's Bluetooth settings.");
  }
}

function Content() {
  const state = useControllerModeState();
  const [requestError, setRequestError] = useState<string | null>(null);

  if (!state) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <Field label="DeckPad" description="Connecting to the DeckPad backend…" />
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const busy = state.status === "starting" || state.status === "stopping";
  const checked = state.status === "on" || state.status === "starting";

  const onChange = async (enabled: boolean) => {
    setRequestError(null);
    try {
      await setControllerMode(enabled);
    } catch {
      setRequestError("Reload DeckPad from Decky's settings, then try again.");
    }
  };


  return (
    <PanelSection>
      <PanelSectionRow>
        <ToggleField
          label="Controller Mode"
          description={DESCRIPTIONS[state.status]}
          checked={checked}
          disabled={busy}
          onChange={onChange}
        />
      </PanelSectionRow>
      {state.status === "on" && (
        <PairingRows
          pairing={state.pairing}
          onRequestError={() => setRequestError("Reload DeckPad from Decky's settings, then try again.")}
        />
      )}
      {state.error && (
        <PanelSectionRow>
          <Field label="Could not turn on Controller Mode" description={state.error.message} focusable />
        </PanelSectionRow>
      )}
      {requestError && (
        <PanelSectionRow>
          <Field label="DeckPad is not responding" description={requestError} focusable />
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}

export default definePlugin(() => ({
  name: "DeckPad",
  titleView: <div className={staticClasses.Title}>DeckPad</div>,
  content: <Content />,
  icon: <FaGamepad />,
}));
