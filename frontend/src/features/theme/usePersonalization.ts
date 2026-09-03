import { useCallback, useState } from "react";
import { type AccentPair, accentPair } from "./accent";
import { applyUserTheme } from "./applyUserTheme";
import { clearUserTheme, readUserTheme, writeUserTheme } from "./themeStorage";
import {
  type BundledFont,
  type UserTheme,
  withoutPartialBrandPair,
} from "./types";

/**
 * Live-preview personalization state. Every setter applies the `<style>` layer
 * immediately and persists to localStorage; a future backend sync writes the
 * same `UserTheme` shape to `PUT /users/me/settings`.
 */
export function usePersonalization() {
  const [theme, setThemeState] = useState<UserTheme>(readUserTheme);

  const commit = useCallback((next: UserTheme) => {
    setThemeState(next);
    applyUserTheme(next);
    writeUserTheme(next);
  }, []);

  /** The accent picker moves Journiv's brand colour, not `--primary`.
   *  `--primary` is neutral in both references (DESIGN.md); the blue a user
   *  chooses is the identity accent, so it lands on `--brand`.
   *
   *  An accent is always a light/dark *pair* with its own foregrounds. Writing
   *  one value into both themes and leaving `--brand-foreground` alone is what
   *  made every curated preset fail 4.5:1 in one theme or the other. */
  const setAccentPair = useCallback(
    (pair: AccentPair) => {
      commit({
        ...theme,
        light: { ...theme.light, ...pair.light },
        dark: { ...theme.dark, ...pair.dark },
      });
    },
    [theme, commit],
  );

  /** A typed colour. Returns `false` when the value is not a colour we can
   *  check for contrast, in which case nothing is applied — see `accent.ts`. */
  const setAccent = useCallback(
    (value: string): boolean => {
      const pair = accentPair(value);
      if (!pair) return false;
      setAccentPair(pair);
      return true;
    },
    [setAccentPair],
  );

  const setSystemFont = useCallback(
    (value: BundledFont) => commit({ ...theme, systemFont: value }),
    [theme, commit],
  );

  const setEditorFont = useCallback(
    (value: BundledFont) => commit({ ...theme, editorFont: value }),
    [theme, commit],
  );

  const setEditorFontScale = useCallback(
    (value: number) => commit({ ...theme, editorFontScale: value }),
    [theme, commit],
  );

  const importTheme = useCallback(
    (parsed: { light: UserTheme["light"]; dark: UserTheme["dark"] }) => {
      const light = withoutPartialBrandPair(parsed.light);
      const dark = withoutPartialBrandPair(parsed.dark);
      commit({
        ...theme,
        light: { ...theme.light, ...light },
        dark: { ...theme.dark, ...dark },
      });
    },
    [theme, commit],
  );

  const reset = useCallback(() => {
    const empty: UserTheme = { version: 1, light: {}, dark: {} };
    setThemeState(empty);
    applyUserTheme(empty);
    clearUserTheme();
  }, []);

  return {
    theme,
    setAccent,
    setAccentPair,
    setSystemFont,
    setEditorFont,
    setEditorFontScale,
    importTheme,
    reset,
  };
}
