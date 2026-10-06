import { Field, PanelSection, PanelSectionRow, ToggleField, staticClasses } from "@decky/ui";
import { addEventListener, callable, definePlugin, removeEventListener } from "@decky/api";
import { useEffect, useState } from "react";
import { FaGamepad } from "react-icons/fa";

type Status = "off" | "starting" | "on" | "stopping";

interface ControllerModeError {
  code: string;
  message: string;
  detail: string | null;
}

interface ControllerModeState {
  enabled: boolean;
  status: Status;
  error: ControllerModeError | null;
}

const STATE_EVENT = "controller_mode_state";

const getState = callable<[], ControllerModeState>("get_state");
const setControllerMode = callable<[enabled: boolean], ControllerModeState>("set_controller_mode");

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
