import {
  type BundledFont,
  EMPTY_USER_THEME,
  type ThemeTokens,
  type UserTheme,
} from "./types";
import { COLOR_VAR_SET } from "./types";

const STORAGE_KEY = "journiv.userTheme";
const FONT_IDS: ReadonlySet<string> = new Set(["dm-sans", "lora"]);

function safeTokens(value: unknown): ThemeTokens {
  if (!value || typeof value !== "object") return {};
  const out: ThemeTokens = {};
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    if (COLOR_VAR_SET.has(k) && typeof v === "string") {
      out[k as keyof ThemeTokens] = v;
    }
  }
  return out;
}

function safeFont(value: unknown): BundledFont | undefined {
  return typeof value === "string" && FONT_IDS.has(value)
    ? (value as BundledFont)
    : undefined;
}

function safeScale(value: unknown): number | undefined {
  return typeof value === "number" && value >= 0.8 && value <= 1.4
    ? value
    : undefined;
}

/** Reads the stored theme, tolerating an absent / corrupt / partial record. */
export function readUserTheme(): UserTheme {
  let raw: string | null = null;
  try {
    raw = window.localStorage?.getItem(STORAGE_KEY) ?? null;
  } catch {
    return { ...EMPTY_USER_THEME };
  }
  if (!raw) return { ...EMPTY_USER_THEME };
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return {
      version: 1,
      light: safeTokens(parsed.light),
      dark: safeTokens(parsed.dark),
      systemFont: safeFont(parsed.systemFont),
      editorFont: safeFont(parsed.editorFont),
      editorFontScale: safeScale(parsed.editorFontScale),
    };
  } catch {
    return { ...EMPTY_USER_THEME };
  }
}

export function writeUserTheme(theme: UserTheme): void {
  try {
    window.localStorage?.setItem(STORAGE_KEY, JSON.stringify(theme));
  } catch {
    /* private mode / storage disabled — the in-memory theme still applies */
  }
}

export function clearUserTheme(): void {
  try {
    window.localStorage?.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
