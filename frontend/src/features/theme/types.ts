/**
 * User personalization model (DESIGN.md §25).
 *
 * A `UserTheme` is a set of stock shadcn CSS custom-property values plus the two
 * font choices and the reader text-size scale. We store the *structured* values,
 * never a raw CSS string, and render the `<style id="journiv-user-theme">` layer
 * ourselves (`applyUserTheme`). The same shape is what a future
 * `PUT /users/me/settings { theme }` will carry, so backend sync needs no
 * redesign.
 */

/** The stock shadcn colour / shadow variables a user (or an imported tweakcn
 *  theme) may set — including Journiv's own `--brand` pair, which is what the
 *  accent picker writes (DESIGN.md §3: `--primary` is neutral, blue is the
 *  brand accent). Font variables are deliberately NOT here — fonts come only
 *  from the bundled-font pickers. `radius` is NOT here either: there is no
 *  corner-radius personalization control, and the whole named scale derives
 *  from that one value, so letting a pasted theme move it would reshape every
 *  registry component at once. */
export const COLOR_VARS = [
  "background",
  "foreground",
  "card",
  "card-foreground",
  "popover",
  "popover-foreground",
  "primary",
  "primary-foreground",
  "brand",
  "brand-foreground",
  "secondary",
  "secondary-foreground",
  "muted",
  "muted-foreground",
  "accent",
  "accent-foreground",
  "destructive",
  "destructive-foreground",
  "border",
  "input",
  "ring",
  "sidebar",
  "sidebar-foreground",
  "sidebar-primary",
  "sidebar-primary-foreground",
  "sidebar-accent",
  "sidebar-accent-foreground",
  "sidebar-border",
  "sidebar-ring",
  "chart-1",
  "chart-2",
  "chart-3",
  "chart-4",
  "chart-5",
  "shadow-2xs",
  "shadow-xs",
  "shadow-sm",
  "shadow",
  "shadow-md",
  "shadow-lg",
  "shadow-xl",
  "shadow-2xl",
] as const;

export type ColorVar = (typeof COLOR_VARS)[number];

export const COLOR_VAR_SET: ReadonlySet<string> = new Set(COLOR_VARS);

/** Bundled font families. `dm-sans` is always loaded; the rest are lazy. Add a
 *  family here + in `fonts.ts` + a fixture — nothing else changes. */
export type BundledFont = "dm-sans" | "lora";

export type ThemeTokens = Partial<Record<ColorVar, string>>;

export interface UserTheme {
  version: 1;
  /** Colour / radius / shadow overrides for light mode (`:root`). */
  light: ThemeTokens;
  /** Overrides for dark mode (`.dark`). */
  dark: ThemeTokens;
  /** UI / chrome font → `--font-sans`. */
  systemFont?: BundledFont;
  /** Reader + editor prose font → `--font-reader`. */
  editorFont?: BundledFont;
  /** Reader/editor prose size multiplier → `--prose-font-scale` (0.9–1.25). */
  editorFontScale?: number;
}

export const EMPTY_USER_THEME: UserTheme = { version: 1, light: {}, dark: {} };

export function isEmptyTheme(theme: UserTheme): boolean {
  return (
    Object.keys(theme.light).length === 0 &&
    Object.keys(theme.dark).length === 0 &&
    theme.systemFont === undefined &&
    theme.editorFont === undefined &&
    theme.editorFontScale === undefined
  );
}
