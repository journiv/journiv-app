import { useState } from "react";
import { NativeSelect } from "../../../components/ui/native-select";
import {
  applyUiExperiment,
  readUiExperiment,
  type UiExperiment,
  writeUiExperiment,
} from "../../theme/uiExperiment";
import { SettingsRow, SettingsSection } from "../SettingsSection";

/**
 * Control for the UI-feel A/B experiment (DESIGN.md §25, `uiExperiment.ts`).
 *
 * DORMANT: not currently mounted in `AppearancePage`. Round 2 adopted
 * `panes: soft` (now the shell.css default) and kept `comfort` / `hover` at
 * their current values. This component is retained, ready to re-mount, so the
 * next round does not have to rebuild the plumbing — swap the axes in
 * `uiExperiment.ts` and add `<UiExperimentSection />` back.
 */
export function UiExperimentSection() {
  const [exp, setExp] = useState<UiExperiment>(readUiExperiment);

  const update = (patch: Partial<UiExperiment>) => {
    const next = { ...exp, ...patch };
    setExp(next);
    applyUiExperiment(next);
    writeUiExperiment(next);
  };

  return (
    <SettingsSection
      title="Interface feel (experiment)"
      intro="A temporary test of a softer, airier treatment against the current design system. This device only; previews instantly. Two of the three axes deliberately push against rules the design system records as already settled — the point is to look again, not to ship."
    >
      <SettingsRow
        label="Primitives"
        htmlFor="ui-comfort"
        description="Roomy rounds the corner radius a little further and gives text inputs, textareas and selects more breathing room."
      >
        <NativeSelect
          id="ui-comfort"
          value={exp.comfort}
          onChange={(event) =>
            update({ comfort: event.target.value as UiExperiment["comfort"] })
          }
        >
          <option value="default">Default (current)</option>
          <option value="roomy">Roomy — rounder, more padding</option>
        </NativeSelect>
      </SettingsRow>

      <SettingsRow
        label="Row hover"
        htmlFor="ui-hover"
        description="Lively keeps the grey tint but adds a soft shadow and a 1px lift, so a row reacts to the pointer instead of only changing colour."
      >
        <NativeSelect
          id="ui-hover"
          value={exp.hover}
          onChange={(event) =>
            update({ hover: event.target.value as UiExperiment["hover"] })
          }
        >
          <option value="flat">Flat tint (current)</option>
          <option value="lively">Lively — tint + shadow + lift</option>
        </NativeSelect>
      </SettingsRow>

      <SettingsRow
        label="Pane separation"
        htmlFor="ui-panes"
        description="Soft is the shipped faded seam. Hairlines forces the old hard --border seam back. Airy removes the shell frame entirely and separates the panes with a strip of canvas — the 'floating panes' look the design system rejected."
      >
        <NativeSelect
          id="ui-panes"
          value={exp.panes}
          onChange={(event) =>
            update({ panes: event.target.value as UiExperiment["panes"] })
          }
        >
          <option value="soft">Soft — faded seams (current)</option>
          <option value="hairlines">Hairlines — hard seams</option>
          <option value="airy">Airy — canvas gap, no frame</option>
        </NativeSelect>
      </SettingsRow>
    </SettingsSection>
  );
}
