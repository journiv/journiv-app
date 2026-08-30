import { FONTS } from "./fonts";
import { COLOR_VARS, type ThemeTokens, type UserTheme } from "./types";

function block(selector: string, tokens: ThemeTokens): string | null {
  const lines = COLOR_VARS.filter((name) => tokens[name] != null).map(
    (name) => `  --${name}: ${tokens[name]};`,
  );
  if (!lines.length) return null;
  return `${selector} {\n${lines.join("\n")}\n}`;
}

/**
 * Serialises the current `UserTheme` to a tweakcn-shaped string for
 * copy / share / backup. Fonts are emitted as a comment, not as `--font-*`
 * variables — re-importing picks them from the bundled set, not from CSS.
 */
export function exportThemeCss(theme: UserTheme): string {
  const parts: string[] = [];
  const fontNotes: string[] = [];
  if (theme.systemFont)
    fontNotes.push(`system font: ${FONTS[theme.systemFont].label}`);
  if (theme.editorFont)
    fontNotes.push(`editor font: ${FONTS[theme.editorFont].label}`);
  if (theme.editorFontScale != null)
    fontNotes.push(`text size: ${theme.editorFontScale}`);
  if (fontNotes.length) parts.push(`/* Journiv — ${fontNotes.join(", ")} */`);

  const light = block(":root", theme.light);
  const dark = block(".dark", theme.dark);
  if (light) parts.push(light);
  if (dark) parts.push(dark);
  return parts.join("\n\n");
}
