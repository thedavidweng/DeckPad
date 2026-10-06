import {
  ButtonItem,
  ConfirmModal,
  Field,
  PanelSection,
  PanelSectionRow,
  ToggleField,
  showModal,
  staticClasses,
} from "@decky/ui";
import { definePlugin, routerHook } from "@decky/api";
import { useEffect, useState } from "react";
import { Troubleshooting } from "./troubleshooting";
import { FaGamepad } from "react-icons/fa";
import {
  ControllerModeState,
  PairedHost,
  PairingState,
  Status,
  allowReconnect,
  connectedHostName,
  disconnectHost,
  forgetHost,
  hostNames,
  setControllerMode,
  setPairingMode,
  useControllerModeState,
} from "./backend";
import {
  CONTROLLER_SCREEN_ROUTE,
  ControllerScreen,
  closeControllerScreen,
  openControllerScreen,
  useControllerScreenOpen,
} from "./controller_screen";

const NOT_RESPONDING = "Reload DeckPad from Decky's settings, then try again.";

const DESCRIPTIONS: Record<Status, string> = {
  off: "Turn on to use this Deck as a Bluetooth controller for another device.",
  starting: "Turning on…",
  on: "This Deck is acting as a Bluetooth controller. Turn off to return to normal.",
  stopping: "Turning off…",
  recovering: "Bluetooth stopped. Controller Mode resumes as soon as it is back.",
};

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
            <Field
              label={pairing.error?.title ?? "Pairing did not finish"}
              description={pairing.error?.message}
              focusable
            />
          </PanelSectionRow>
          {action("Try Again", true)}
        </>
      );
    default:
      return action("Pair a Device", true, "Make this Deck visible in another device's Bluetooth settings.");
  }
}

function ConnectionRows({
  state,
  screenOpen,
  onRequestError,
}: {
  state: ControllerModeState;
  screenOpen: boolean;
  onRequestError: () => void;
}) {
  switch (state.connection) {
    case "connected":
      return (
        <>
          <PanelSectionRow>
            <Field
              label={`Connected to ${connectedHostName(state) ?? "a paired device"}`}
              description="Your controls are going to this device."
              focusable
            />
          </PanelSectionRow>
          {!screenOpen && (
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                description="A full-screen view that keeps Steam on this Deck from reacting to your presses."
                onClick={openControllerScreen}
              >
                Open Controller Screen
              </ButtonItem>
            </PanelSectionRow>
          )}
        </>
      );
    case "waiting":
      return (
        <PanelSectionRow>
          <Field
            label="Waiting for a paired device"
            description="A paired device reconnects on its own, or connect to this Deck from its Bluetooth settings."
            focusable
          />
        </PanelSectionRow>
      );
    case "paused":
      return (
        <>
          <PanelSectionRow>
            <Field label="Disconnected" description="Paired devices will not reconnect until you allow it." focusable />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => allowReconnect().catch(onRequestError)}>
              Allow Reconnecting
            </ButtonItem>
          </PanelSectionRow>
        </>
      );
    default:
      return null;
  }
}

function PairedHostRows({
  state,
  names,
  onRequestError,
}: {
  state: ControllerModeState;
  names: Map<string, string>;
  onRequestError: () => void;
}) {
  if (state.hosts.length === 0) return null;

  const confirmForget = (host: PairedHost) => {
    const name = names.get(host.address) ?? "this device";
    showModal(
      <ConfirmModal
        strTitle={`Forget ${name}?`}
        strDescription={
          `${name} will need to pair again to use this Deck as a controller. ` +
          `Also remove this Deck from ${name}'s Bluetooth settings.`
        }
        strOKButtonText="Forget"
        bDestructiveWarning
        onOK={() => forgetHost(host.address).catch(onRequestError)}
      />,
    );
  };

  return (
    <PanelSection title="Paired Devices">
      {state.hosts.map((host) => (
        <PanelSectionRow key={host.address}>
          <Field
            label={names.get(host.address)}
            description={host.connected ? "Connected" : "Not connected"}
            focusable
          />
          {host.connected && (
            <ButtonItem layout="below" onClick={() => disconnectHost(host.address).catch(onRequestError)}>
              Disconnect
            </ButtonItem>
          )}
          <ButtonItem layout="below" onClick={() => confirmForget(host)}>
            Forget
          </ButtonItem>
        </PanelSectionRow>
      ))}
    </PanelSection>
  );
}

function Content() {
  const state = useControllerModeState();
  const screenOpen = useControllerScreenOpen();
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
  const checked = state.status === "on" || state.status === "starting" || state.status === "recovering";

  const onChange = async (enabled: boolean) => {
    setRequestError(null);
    try {
      await setControllerMode(enabled);
    } catch {
      setRequestError(NOT_RESPONDING);
    }
  };
  const onRequestError = () => setRequestError(NOT_RESPONDING);
  const names = hostNames(state.hosts);

  return (
    <>
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
        {screenOpen && (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={closeControllerScreen}>
              Close Controller Screen
            </ButtonItem>
          </PanelSectionRow>
        )}
        {state.status === "on" && (
          <ConnectionRows state={state} screenOpen={screenOpen} onRequestError={onRequestError} />
        )}
        {state.status === "on" && <PairingRows pairing={state.pairing} onRequestError={onRequestError} />}
        {state.status === "on" && state.controls && !state.controls.available && (
          <PanelSectionRow>
            <Field label="No input from the Deck's controls" description={state.controls.message} focusable />
          </PanelSectionRow>
        )}
        {state.error && (
          <PanelSectionRow>
            <Field label={state.error.title} description={state.error.message} focusable />
          </PanelSectionRow>
        )}
        {requestError && (
          <PanelSectionRow>
            <Field label="DeckPad is not responding" description={requestError} focusable />
          </PanelSectionRow>
        )}
      </PanelSection>
      {(state.status === "on" || state.status === "off") && (
        <PairedHostRows state={state} names={names} onRequestError={onRequestError} />
      )}
      <Troubleshooting />
    </>
  );
}

export default definePlugin(() => {
  routerHook.addRoute(CONTROLLER_SCREEN_ROUTE, ControllerScreen, { exact: true });
  return {
    name: "DeckPad",
    titleView: <div className={staticClasses.Title}>DeckPad</div>,
    content: <Content />,
    icon: <FaGamepad />,
    onDismount() {
      routerHook.removeRoute(CONTROLLER_SCREEN_ROUTE);
    },
  };
});
