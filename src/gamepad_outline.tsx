import { IconsModule } from "@decky/ui";
import { FC } from "react";
import { FaGamepad } from "react-icons/fa";
import { GamepadPreview } from "./backend";

// Steam's own Xbox controller drawing, from the icons module its Test Device Inputs page uses. It is
// not part of Decky's API, so the screen falls back to a plain icon if Steam renames it.
const XboxOutline: FC<Record<string, unknown>> | undefined = IconsModule?.XboxOneControllerFrontOutline;

// Below this a trigger counts as released, as Steam's own trigger glyphs do for resting noise.
const TRIGGER_LIT = 0.05;

const WIDTH = 360;
// The drawing's viewBox is 999 x 701.
const HEIGHT = Math.round((WIDTH * 701) / 999);

export function GamepadOutline({ report }: { report: GamepadPreview | null }) {
  if (!XboxOutline) return <FaGamepad size={72} />;
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
