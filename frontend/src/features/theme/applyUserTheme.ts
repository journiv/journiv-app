import { ensureFont, fontStack } from "./fonts";
import { isSafeThemeValue } from "./parseThemeCss";
import { isEmptyTheme, type ThemeTokens, type UserTheme } from "./types";

const STYLE_ID = "journiv-user-theme";

function declarations(tokens: ThemeTokens): string {
  return Object.entries(tokens)
    .filter(([, value]) => isSafeThemeValue(value))
    .map(([name, value]) => `  --${name}: ${value};`)
    .join("\n");
}

/** Serialises a `UserTheme` to the `<style id="journiv-user-theme">` layer and
 *  installs it in `<head>`. We always build the CSS from the structured map —
 *  a pasted string is never written to the DOM. Called once on boot (after
 *  `applyTheme`) and again after every save / reset. */
export function applyUserTheme(theme: UserTheme): void {
  if (typeof document === "undefined") return;

  const existing = document.getElementById(STYLE_ID);
  if (isEmptyTheme(theme)) {
    existing?.remove();
    return;
  }

  ensureFont(theme.systemFont);
  ensureFont(theme.editorFont);

  const rootRules: string[] = [];
  if (Object.keys(theme.light).length)
    rootRules.push(declarations(theme.light));
  const sys = fontStack(theme.systemFont);
  const reader = fontStack(theme.editorFont);
  if (sys) rootRules.push(`  --font-sans: ${sys};`);
  if (reader) rootRules.push(`  --font-reader: ${reader};`);
  if (theme.editorFontScale != null) {
    rootRules.push(`  --prose-font-scale: ${theme.editorFontScale};`);
  }

  const blocks: string[] = [];
  if (rootRules.length) blocks.push(`:root {\n${rootRules.join("\n")}\n}`);
  if (Object.keys(theme.dark).length) {
    blocks.push(`.dark {\n${declarations(theme.dark)}\n}`);
  }

  const css = blocks.join("\n\n");
  const style =
    existing instanceof HTMLStyleElement
      ? existing
      : document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = css;
  if (!style.isConnected) document.head.appendChild(style);
}
