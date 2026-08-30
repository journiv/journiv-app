import { useId, useState } from "react";
import { Button } from "../../../components/ui/button";
import { Textarea } from "../../../components/ui/textarea";
import { exportThemeCss } from "../../theme/exportThemeCss";
import { FONT_OPTIONS } from "../../theme/fonts";
import { parseThemeCss, ThemeParseError } from "../../theme/parseThemeCss";
import type { BundledFont } from "../../theme/types";
import { usePersonalization } from "../../theme/usePersonalization";
import { SettingsRow, SettingsSection } from "../SettingsSection";

/** A small preset palette; the text input accepts any CSS colour. */
const ACCENT_PRESETS = [
  { label: "Journiv blue", value: "oklch(0.545 0.192 269)" },
  { label: "Indigo", value: "oklch(0.51 0.23 277)" },
  { label: "Violet", value: "oklch(0.54 0.24 293)" },
  { label: "Teal", value: "oklch(0.6 0.13 195)" },
  { label: "Green", value: "oklch(0.58 0.15 150)" },
  { label: "Amber", value: "oklch(0.7 0.17 65)" },
  { label: "Rose", value: "oklch(0.6 0.22 15)" },
  { label: "Slate", value: "oklch(0.45 0.03 260)" },
];

const RADIUS_STEPS = [
  { label: "Square", value: "0rem" },
  { label: "Slight", value: "0.375rem" },
  { label: "Default", value: "0.625rem" },
  { label: "Round", value: "1rem" },
];

const SIZE_STEPS = [0.92, 0.96, 1, 1.08, 1.18];

export function PersonalizeSection() {
  const p = usePersonalization();
  const accentId = useId();
  const [accentText, setAccentText] = useState(p.theme.light.primary ?? "");
  const [importText, setImportText] = useState("");
  const [importNote, setImportNote] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const currentScale = p.theme.editorFontScale ?? 1;
  const currentRadius = p.theme.light.radius ?? "0.625rem";

  const applyImport = () => {
    setImportError(null);
    setImportNote(null);
    try {
      const { light, dark, notes } = parseThemeCss(importText);
      p.importTheme({ light, dark });
      setImportNote(
        notes.length
          ? `Applied. ${notes.length} declaration${notes.length === 1 ? "" : "s"} skipped: ${notes.join(" ")}`
          : "Theme applied.",
      );
    } catch (err) {
      setImportError(
        err instanceof ThemeParseError
          ? err.message
          : "That theme couldn’t be read.",
      );
    }
  };

  return (
    <SettingsSection
      title="Personalize"
      intro="Colour, fonts and reading size for this device. Import a shadcn or tweakcn theme, or reset to the Journiv defaults."
    >
      <SettingsRow label="Accent colour" htmlFor={accentId}>
        <div className="jv-personalize__swatches">
          {ACCENT_PRESETS.map((preset) => (
            <button
              key={preset.value}
              type="button"
              className="jv-personalize__swatch"
              style={{ background: preset.value }}
              aria-label={preset.label}
              aria-pressed={p.theme.light.primary === preset.value}
              onClick={() => {
                setAccentText(preset.value);
                p.setAccent(preset.value);
              }}
            />
          ))}
        </div>
        <input
          id={accentId}
          className="jv-field"
          placeholder="oklch(0.55 0.19 269) or #4a5bd6"
          value={accentText}
          onChange={(event) => setAccentText(event.target.value)}
          onBlur={() => {
            const v = accentText.trim();
            if (v) p.setAccent(v);
          }}
        />
      </SettingsRow>

      <SettingsRow label="System font" htmlFor="personalize-system-font">
        <select
          id="personalize-system-font"
          className="jv-field"
          value={p.theme.systemFont ?? "dm-sans"}
          onChange={(event) =>
            p.setSystemFont(event.target.value as BundledFont)
          }
        >
          {FONT_OPTIONS.map((font) => (
            <option key={font.value} value={font.value}>
              {font.label}
            </option>
          ))}
        </select>
      </SettingsRow>

      <SettingsRow
        label="Editor font"
        htmlFor="personalize-editor-font"
        description="Used in the reader and editor. May differ from the system font."
      >
        <select
          id="personalize-editor-font"
          className="jv-field"
          value={p.theme.editorFont ?? "dm-sans"}
          onChange={(event) =>
            p.setEditorFont(event.target.value as BundledFont)
          }
        >
          {FONT_OPTIONS.map((font) => (
            <option key={font.value} value={font.value}>
              {font.label}
            </option>
          ))}
        </select>
      </SettingsRow>

      <SettingsRow
        label="Text size"
        description="Reader and editor prose only."
      >
        <div className="jv-personalize__steps">
          {SIZE_STEPS.map((scale) => (
            <button
              key={scale}
              type="button"
              className="jv-personalize__step"
              aria-pressed={Math.abs(currentScale - scale) < 0.001}
              onClick={() => p.setEditorFontScale(scale)}
            >
              {Math.round(scale * 100)}%
            </button>
          ))}
        </div>
      </SettingsRow>

      <SettingsRow label="Corner radius">
        <div className="jv-personalize__steps">
          {RADIUS_STEPS.map((step) => (
            <button
              key={step.value}
              type="button"
              className="jv-personalize__step"
              aria-pressed={currentRadius === step.value}
              onClick={() => p.setRadius(step.value)}
            >
              {step.label}
            </button>
          ))}
        </div>
      </SettingsRow>

      <SettingsRow
        label="Import theme"
        htmlFor="personalize-import"
        description="Paste a shadcn / tweakcn theme. Only :root and .dark colour variables are read; fonts stay controlled above."
      >
        <Textarea
          id="personalize-import"
          rows={4}
          value={importText}
          placeholder=":root { --primary: oklch(…); } .dark { … }"
          onChange={(event) => setImportText(event.target.value)}
        />
        <div className="jv-personalize__import-actions">
          <Button
            variant="secondary"
            disabled={!importText.trim()}
            onClick={applyImport}
          >
            Apply theme
          </Button>
        </div>
        {importError && (
          <p className="jv-settings__alert" role="alert">
            {importError}
          </p>
        )}
        {importNote && <p className="jv-caption">{importNote}</p>}
      </SettingsRow>

      <SettingsRow
        label="Export theme"
        description="Copy the current colours as a shadcn / tweakcn block."
      >
        <Textarea
          readOnly
          rows={4}
          value={exportThemeCss(p.theme) || "No custom colours yet."}
        />
      </SettingsRow>

      <SettingsRow label="Reset">
        <Button variant="ghost" onClick={p.reset}>
          Reset to Journiv default
        </Button>
      </SettingsRow>
    </SettingsSection>
  );
}
