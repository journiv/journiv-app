import { type CSSProperties, useEffect, useId, useState } from "react";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { NativeSelect } from "../../../components/ui/native-select";
import { Textarea } from "../../../components/ui/textarea";
import {
  ToggleGroup,
  ToggleGroupItem,
} from "../../../components/ui/toggle-group";
import {
  ACCENT_PRESETS,
  accentSwatch,
  isAccentActive,
} from "../../theme/accent";
import { exportThemeCss } from "../../theme/exportThemeCss";
import { FONT_OPTIONS } from "../../theme/fonts";
import { parseThemeCss, ThemeParseError } from "../../theme/parseThemeCss";
import type { BundledFont } from "../../theme/types";
import { usePersonalization } from "../../theme/usePersonalization";
import { SettingsRow, SettingsSection } from "../SettingsSection";

const SIZE_STEPS = [0.92, 0.96, 1, 1.08, 1.18];

export function PersonalizeSection() {
  const p = usePersonalization();
  const accentId = useId();
  const [accentText, setAccentText] = useState(p.theme.light.brand ?? "");
  const [accentError, setAccentError] = useState<string | null>(null);
  const [importText, setImportText] = useState("");
  const [importNote, setImportNote] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  useEffect(() => {
    setAccentText(p.theme.light.brand ?? "");
    setAccentError(null);
  }, [p.theme.light.brand]);

  const currentScale = p.theme.editorFontScale ?? 1;

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
      <SettingsRow
        label="Accent colour"
        htmlFor={accentId}
        description="Used for the brand button, the selection rail, the focus ring and links in prose. Light and dark get different lightnesses of the same hue so text on the accent stays readable in both."
      >
        <div className="jv-personalize__swatches">
          {ACCENT_PRESETS.map((preset) => (
            <button
              key={preset.label}
              type="button"
              className="jv-personalize__swatch"
              style={
                { "--entity-accent": accentSwatch(preset) } as CSSProperties
              }
              aria-label={preset.label}
              aria-pressed={isAccentActive(p.theme, preset)}
              onClick={() => {
                setAccentError(null);
                setAccentText(preset.light.brand ?? "");
                p.setAccentPair(preset);
              }}
            />
          ))}
        </div>
        <Input
          id={accentId}
          placeholder="oklch(0.55 0.19 269) or #4a5bd6"
          value={accentText}
          aria-invalid={accentError != null}
          onChange={(event) => setAccentText(event.target.value)}
          onBlur={() => {
            const value = accentText.trim();
            if (!value) {
              setAccentError("Enter an accent colour.");
              return;
            }
            // A colour we cannot measure is refused rather than applied: this
            // one token is a link colour and a focus ring, so an unreadable
            // value is a real accessibility failure, not a taste question.
            setAccentError(
              p.setAccent(value)
                ? null
                : "Use an oklch() colour, an rgb() colour or a hex value like #4a5bd6.",
            );
          }}
        />
        {accentError && (
          <p className="jv-settings__alert" role="alert">
            {accentError}
          </p>
        )}
      </SettingsRow>

      <SettingsRow label="System font" htmlFor="personalize-system-font">
        <NativeSelect
          id="personalize-system-font"
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
        </NativeSelect>
      </SettingsRow>

      <SettingsRow
        label="Editor font"
        htmlFor="personalize-editor-font"
        description="Used in the reader and editor. May differ from the system font."
      >
        <NativeSelect
          id="personalize-editor-font"
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
        </NativeSelect>
      </SettingsRow>

      <SettingsRow
        label="Text size"
        description="Reader and editor prose only."
      >
        <ToggleGroup
          spacing={0}
          variant="outline"
          size="sm"
          aria-label="Text size"
          value={SIZE_STEPS.filter(
            (scale) => Math.abs(currentScale - scale) < 0.001,
          ).map(String)}
          onValueChange={([next]) => {
            if (next) p.setEditorFontScale(Number(next));
          }}
        >
          {SIZE_STEPS.map((scale) => (
            <ToggleGroupItem key={scale} value={String(scale)}>
              {Math.round(scale * 100)}%
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
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
