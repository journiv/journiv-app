import { useCallback, useState } from "react";
import { applyUserTheme } from "./applyUserTheme";
import { clearUserTheme, readUserTheme, writeUserTheme } from "./themeStorage";
import type { BundledFont, UserTheme } from "./types";

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

  const setAccent = useCallback(
    (value: string) => {
      commit({
        ...theme,
        light: { ...theme.light, primary: value },
        dark: { ...theme.dark, primary: value },
      });
    },
    [theme, commit],
  );

  const setRadius = useCallback(
    (value: string) => {
      commit({ ...theme, light: { ...theme.light, radius: value } });
    },
    [theme, commit],
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
      commit({
        ...theme,
        light: { ...theme.light, ...parsed.light },
        dark: { ...theme.dark, ...parsed.dark },
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
    setRadius,
    setSystemFont,
    setEditorFont,
    setEditorFontScale,
    importTheme,
    reset,
  };
}
