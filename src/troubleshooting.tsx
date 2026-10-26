import { ButtonItem, Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { useEffect, useRef, useState } from "react";
import { Diagnostics, getDiagnostics } from "./backend";

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

export function Troubleshooting() {
  const [open, setOpen] = useState(false);
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const request = useRef(0);

  const refresh = async () => {
    const current = ++request.current;
    setStatus(null);
    try {
      const result = await getDiagnostics();
      if (current === request.current) setDiagnostics(result);
    } catch {
      if (current === request.current) {
        setDiagnostics(null);
        setStatus("DeckPad is not responding. Reload it from Decky's settings.");
      }
    }
  };

  useEffect(() => {
    if (open) void refresh();
    return () => { ++request.current; };
  }, [open]);

  const copy = async () => {
    if (!diagnostics) return;
    const current = request.current;
    const copied = await copyText(diagnostics.text);
    if (current === request.current) {
      setStatus(copied ? "Copied to the clipboard." : "Could not copy. Use the saved file instead.");
    }
  };

  return (
    <PanelSection title="Troubleshooting">
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => setOpen(!open)}>
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
