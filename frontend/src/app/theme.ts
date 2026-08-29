import { useEffect, useState } from "react";

export type ThemeMode = "system" | "light" | "dark";

const storageKey = "journiv.theme";

export function readTheme(): ThemeMode {
  const storage = window.localStorage as Partial<Storage>;
  const value =
    typeof storage.getItem === "function" ? storage.getItem(storageKey) : null;
  return value === "light" || value === "dark" ? value : "system";
}

export function applyTheme(mode: ThemeMode) {
  const resolved =
    mode === "system"
      ? typeof matchMedia === "function" &&
        matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : mode;
  // shadcn base-vega keys dark mode off the `.dark` class (see the
  // `@custom-variant dark` in index.css), not a data attribute.
  document.documentElement.classList.toggle("dark", resolved === "dark");
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themeMode = mode;
}

export function setTheme(mode: ThemeMode) {
  const storage = window.localStorage as Partial<Storage>;
  if (mode === "system" && typeof storage.removeItem === "function")
    storage.removeItem(storageKey);
  else if (mode !== "system" && typeof storage.setItem === "function")
    storage.setItem(storageKey, mode);
  applyTheme(mode);
}

export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(readTheme);

  useEffect(() => {
    applyTheme(mode);
    if (typeof matchMedia !== "function") return;
    const media = matchMedia("(prefers-color-scheme: dark)");
    const updateSystemTheme = () => mode === "system" && applyTheme(mode);
    media.addEventListener("change", updateSystemTheme);
    return () => media.removeEventListener("change", updateSystemTheme);
  }, [mode]);

  return {
    mode,
    set: (next: ThemeMode) => {
      setTheme(next);
      setMode(next);
    },
  };
}
