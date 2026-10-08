import { IconsModule } from "@decky/ui";
import { FC } from "react";
import { GamepadPreview } from "./backend";

// The "gamepad" icon from Font Awesome Free 5 (CC BY 4.0, https://fontawesome.com/license/free).
export function GamepadIcon({ size = "1em" }: { size?: number | string }) {
  return (
    <svg viewBox="0 0 640 512" width={size} height={size} fill="currentColor">
      <path d="M480.07 96H160a160 160 0 1 0 114.24 272h91.52A160 160 0 1 0 480.07 96zM248 268a12 12 0 0 1-12 12h-52v52a12 12 0 0 1-12 12h-24a12 12 0 0 1-12-12v-52H84a12 12 0 0 1-12-12v-24a12 12 0 0 1 12-12h52v-52a12 12 0 0 1 12-12h24a12 12 0 0 1 12 12v52h52a12 12 0 0 1 12 12zm216 76a40 40 0 1 1 40-40 40 40 0 0 1-40 40zm64-96a40 40 0 1 1 40-40 40 40 0 0 1-40 40z" />
    </svg>
  );
}

// Steam's own Xbox controller drawing, from the icons module its Test Device Inputs page uses. It is
// not part of Decky's API, so the screen falls back to a plain icon if Steam renames it.
const XboxOutline: FC<Record<string, unknown>> | undefined = IconsModule?.XboxOneControllerFrontOutline;

// Below this a trigger counts as released, as Steam's own trigger glyphs do for resting noise.
const TRIGGER_LIT = 0.05;

const WIDTH = 360;
// The drawing's viewBox is 999 x 701.
const HEIGHT = Math.round((WIDTH * 701) / 999);

export function GamepadOutline({ report }: { report: GamepadPreview | null }) {
  if (!XboxOutline) return <GamepadIcon size={72} />;
  const held = new Set(report?.buttons ?? []);
  const lt = report?.left_trigger ?? 0;
  const rt = report?.right_trigger ?? 0;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "8px" }}>
      <XboxOutline
        width={WIDTH}
        height={HEIGHT}
        style={{ color: "#dcdedf" }}
        highlightSouth={held.has("a")}
        highlightEast={held.has("b")}
        highlightWest={held.has("x")}
        highlightNorth={held.has("y")}
        highlightLeftBumper={held.has("lb")}
        highlightRightBumper={held.has("rb")}
        highlightLeftTrigger={lt > TRIGGER_LIT}
        highlightRightTrigger={rt > TRIGGER_LIT}
        highlightSelect={held.has("view")}
        highlightStart={held.has("menu")}
        highlightGuide={held.has("guide")}
        hasCaptureButton
        highlightCapture={held.has("share")}
        highlightLeftStick={held.has("l3")}
        highlightRightStick={held.has("r3")}
        highlightDPadUp={held.has("dpad_up")}
        highlightDPadDown={held.has("dpad_down")}
        highlightDPadLeft={held.has("dpad_left")}
        highlightDPadRight={held.has("dpad_right")}
        leftJoystickX={report?.left_stick[0] ?? 0}
        leftJoystickY={report?.left_stick[1] ?? 0}
        rightJoystickX={report?.right_stick[0] ?? 0}
        rightJoystickY={report?.right_stick[1] ?? 0}
      />
      <div style={{ display: "flex", gap: "24px", fontSize: "14px", opacity: 0.8 }}>
        <TriggerBar label="LT" value={lt} />
        <TriggerBar label="RT" value={rt} />
      </div>
    </div>
  );
}

// The drawing only lights a trigger on or off; the bar shows how far it is pulled.
function TriggerBar({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
      <span>{label}</span>
      <div style={{ width: "120px", height: "8px", borderRadius: "4px", background: "rgba(255,255,255,0.15)" }}>
        <div
          style={{
            width: `${Math.round(value * 100)}%`,
            height: "100%",
            borderRadius: "4px",
            background: "#1a9fff",
          }}
        />
      </div>
    </div>
  );
}
