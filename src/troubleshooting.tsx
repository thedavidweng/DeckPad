import { ButtonItem, Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { callable } from "@decky/api";
import { useState } from "react";

interface Diagnostics {
  summary: [string, string][];
  text: string;
  path: string | null;
}

const getDiagnostics = callable<[], Diagnostics>("get_diagnostics");

// Steam's CEF exposes no clipboard API to plugins, and navigator.clipboard needs a focused secure
// context that the QAM often is not, so copy through a temporary text area first.
async function copyText(text: string): Promise<boolean> {
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  } finally {
    document.body.removeChild(area);
  }
  if (copied) return true;
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

// Collapsed by default, below everything else, so it never competes with the normal controls.
export function Troubleshooting() {
  const [open, setOpen] = useState(false);
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const refresh = async () => {
    setStatus(null);
    try {
      setDiagnostics(await getDiagnostics());
    } catch {
      setDiagnostics(null);
      setStatus("DeckPad is not responding. Reload it from Decky's settings.");
    }
  };

  const toggle = () => {
    if (!open) refresh();
    setOpen(!open);
  };

  const copy = async () => {
    if (!diagnostics) return;
    const copied = await copyText(diagnostics.text);
    setStatus(copied ? "Copied to the clipboard." : "Could not copy. Use the saved file instead.");
  };

  return (
    <PanelSection title="Troubleshooting">
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={toggle}>
          {open ? "Hide Diagnostics" : "Show Diagnostics"}
        </ButtonItem>
      </PanelSectionRow>
      {open &&
        diagnostics?.summary.map(([label, value]) => (
          <PanelSectionRow key={label}>
            <Field label={label} focusable>
              {value}
            </Field>
          </PanelSectionRow>
        ))}
      {open && diagnostics && (
        <>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={copy}
              description={diagnostics.path ? `Also saved to ${diagnostics.path}` : undefined}
            >
              Copy Diagnostics
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={refresh}>
              Refresh
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}
      {open && status && (
        <PanelSectionRow>
          <Field description={status} focusable />
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}
