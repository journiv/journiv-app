import {
  contrastRatio,
  formatOklch,
  gamutMapToSrgb,
  type Oklch,
  parseAccentColor,
} from "./contrast";
import type { ThemeTokens } from "./types";

/**
 * The accent model (DESIGN.md, docs/features/personalization.md).
 *
 * An accent is a *pair*, never a single colour. Writing one brand value into
 * both themes and leaving `--brand-foreground` at its default is the bug this
 * module exists to prevent: it produced eight curated presets of which every
 * one failed 4.5:1 in at least one theme — white-on-amber at 2.66:1 in light,
 * near-black-on-slate at 2.65:1 in dark. The two themes need different
 * lightnesses and opposite foregrounds, so both are stored explicitly.
 *
 * `--brand` has to clear 4.5:1 against four things at once: the page
 * background and the card behind a prose link, and its own foreground behind
 * a filled button's label. In light mode all four pull the same way (darker);
 * in dark mode all four pull the other way (lighter). That is why a safe
 * accent is a *band* of lightness per hue, and why {@link accentPair} clamps
 * into it rather than refusing a colour outright.
 */

/** The surfaces `--brand` is painted on or beside, per theme (tokens.css). */
const SURFACES = {
  light: [
    { l: 1, c: 0, h: 0 }, // --background
    { l: 0.995, c: 0, h: 0 }, // --card
  ],
  dark: [
    { l: 0.205, c: 0, h: 0 }, // --background
    { l: 0.165, c: 0, h: 0 }, // --card
  ],
} satisfies Record<"light" | "dark", Oklch[]>;

/** `--brand-foreground` is a near-white or near-black tinted by the accent's
 *  own hue, matching the shipped default pair in tokens.css. */
const foreground = (theme: "light" | "dark", h: number): Oklch =>
  theme === "light" ? { l: 0.985, c: 0.003, h } : { l: 0.15, c: 0.01, h };

/** Everything above is checked against this, not against the 4.5:1 floor.
 *  The margin is deliberate: a token is rounded for display, a user may sit at
 *  a different gamma, and an accent that lands exactly on the line has no room
 *  for either. */
const TARGET_RATIO = 5.3;

function meets(theme: "light" | "dark", color: Oklch): boolean {
  const against = [...SURFACES[theme], foreground(theme, color.h)];
  return against.every((other) => contrastRatio(color, other) >= TARGET_RATIO);
}

/**
 * Moves `color`'s lightness into the readable band for `theme`, keeping its
 * hue and chroma. Light mode darkens, dark mode lightens — the direction is
 * fixed because contrast against every surface in that theme is monotonic in
 * lightness. Returns the input unchanged when it is already safe.
 */
function clampToBand(theme: "light" | "dark", color: Oklch): Oklch {
  const mapped = gamutMapToSrgb(color);
  if (meets(theme, mapped)) return mapped;
  const step = theme === "light" ? -0.005 : 0.005;
  for (let i = 1; i <= 200; i++) {
    const candidate = { ...color, l: color.l + step * i };
    if (candidate.l < 0 || candidate.l > 1) break;
    const mappedCandidate = gamutMapToSrgb(candidate);
    if (meets(theme, mappedCandidate)) return mappedCandidate;
  }
  // Only reachable for a chroma so high that no lightness works; a fully
  // desaturated fallback always does.
  return theme === "light"
    ? { l: 0.35, c: 0, h: color.h }
    : { l: 0.78, c: 0, h: color.h };
}

export interface AccentPair {
  light: Pick<ThemeTokens, "brand" | "brand-foreground">;
  dark: Pick<ThemeTokens, "brand" | "brand-foreground">;
}

function pairFrom(color: Oklch): AccentPair {
  const light = clampToBand("light", color);
  const dark = clampToBand("dark", color);
  return {
    light: {
      brand: formatOklch(light),
      "brand-foreground": formatOklch(foreground("light", light.h)),
    },
    dark: {
      brand: formatOklch(dark),
      "brand-foreground": formatOklch(foreground("dark", dark.h)),
    },
  };
}

/**
 * A user-typed accent as a safe light/dark pair, or `null` when the value is
 * not a colour this app can check. Refusing is the point: silently applying an
 * unverifiable colour to `--brand` is how unreadable links and invisible focus
 * rings get shipped.
 */
export function accentPair(value: string): AccentPair | null {
  const parsed = parseAccentColor(value);
  return parsed ? pairFrom(parsed) : null;
}

/**
 * The curated palette. Each entry is a pair produced by {@link pairFrom} from
 * the hue and chroma named in its comment, so the presets and a typed colour
 * go through exactly the same rule and `accent.test.ts` can prove every one of
 * them clears the ratio in both themes.
 *
 * Amber and Teal are visibly deeper than their names suggest. That is not a
 * mistake — a light gold cannot simultaneously carry white text and be a
 * readable link on a white page, and Journiv would rather ship a usable ochre
 * than an amber nobody can read.
 */
export const ACCENT_PRESETS: ReadonlyArray<{ label: string } & AccentPair> = [
  {
    // The one preset written out rather than derived: it *is* the shipped
    // default in tokens.css, so it has to reproduce it exactly. Those values
    // are hand-picked and verified (4.98:1 at the tightest), which is inside
    // AA but below the margin `pairFrom` holds out for. Keep the two in step.
    label: "Journiv blue",
    light: {
      brand: "oklch(0.545 0.192 269)",
      "brand-foreground": "oklch(0.985 0.003 269)",
    },
    dark: {
      brand: "oklch(0.66 0.17 269)",
      "brand-foreground": "oklch(0.15 0.01 269)",
    },
  },
  { label: "Indigo", ...pairFrom({ l: 0.51, c: 0.23, h: 277 }) },
  { label: "Violet", ...pairFrom({ l: 0.54, c: 0.24, h: 293 }) },
  { label: "Teal", ...pairFrom({ l: 0.6, c: 0.13, h: 195 }) },
  { label: "Green", ...pairFrom({ l: 0.58, c: 0.15, h: 150 }) },
  { label: "Amber", ...pairFrom({ l: 0.7, c: 0.17, h: 65 }) },
  { label: "Rose", ...pairFrom({ l: 0.6, c: 0.22, h: 15 }) },
  { label: "Slate", ...pairFrom({ l: 0.45, c: 0.03, h: 260 }) },
];

/** The swatch a preset button paints. The light-mode brand is the one that
 *  reads as "the colour" regardless of the viewer's current theme. */
export function accentSwatch(pair: AccentPair): string {
  return pair.light.brand ?? "";
}

/** Whether a stored theme is currently on this preset. Both halves are
 *  compared: two presets can share a light brand and differ in dark. */
export function isAccentActive(
  theme: { light: ThemeTokens; dark: ThemeTokens },
  pair: AccentPair,
): boolean {
  return (
    theme.light.brand === pair.light.brand &&
    theme.light["brand-foreground"] === pair.light["brand-foreground"] &&
    theme.dark.brand === pair.dark.brand &&
    theme.dark["brand-foreground"] === pair.dark["brand-foreground"]
  );
}
