import { describe, expect, it } from "vitest";
import { ACCENT_PRESETS, accentPair, isAccentActive } from "./accent";
import { contrastRatio, type Oklch, parseAccentColor } from "./contrast";

/** The surfaces `--brand` is painted on or beside in each theme, and the
 *  foreground painted on top of it — read from tokens.css. If tokens.css moves
 *  a background, this list has to move with it. */
const CHECKS = {
  light: [
    { name: "--background", color: { l: 1, c: 0, h: 0 } },
    { name: "--card", color: { l: 0.995, c: 0, h: 0 } },
  ],
  dark: [
    { name: "--background", color: { l: 0.205, c: 0, h: 0 } },
    { name: "--card", color: { l: 0.165, c: 0, h: 0 } },
  ],
} satisfies Record<"light" | "dark", Array<{ name: string; color: Oklch }>>;

/** WCAG AA for normal text. */
const AA = 4.5;

function oklch(value: string | undefined): Oklch {
  const parsed = value ? parseAccentColor(value) : null;
  if (!parsed) throw new Error(`not a colour: ${value}`);
  return parsed;
}

describe("curated accent presets", () => {
  it("offers a stable set of named presets", () => {
    expect(ACCENT_PRESETS.map((preset) => preset.label)).toEqual([
      "Journiv blue",
      "Indigo",
      "Violet",
      "Teal",
      "Green",
      "Amber",
      "Rose",
      "Slate",
    ]);
  });

  for (const preset of ACCENT_PRESETS) {
    describe(preset.label, () => {
      for (const theme of ["light", "dark"] as const) {
        it(`carries its own label in ${theme}`, () => {
          // The filled brand Button: --brand-foreground text on a --brand fill.
          const brand = oklch(preset[theme].brand);
          const fg = oklch(preset[theme]["brand-foreground"]);
          expect(contrastRatio(brand, fg)).toBeGreaterThanOrEqual(AA);
        });

        for (const surface of CHECKS[theme]) {
          it(`is a readable link on ${surface.name} in ${theme}`, () => {
            // Links in prose are the accent as *text*, so the accent has to
            // clear AA against the page and the card as well as against its
            // own foreground.
            const brand = oklch(preset[theme].brand);
            expect(contrastRatio(brand, surface.color)).toBeGreaterThanOrEqual(
              AA,
            );
          });
        }
      }

      it("is a different lightness in light and dark", () => {
        // The whole failure mode was one value written to both themes.
        expect(oklch(preset.dark.brand).l).toBeGreaterThan(
          oklch(preset.light.brand).l,
        );
      });

      it("keeps one hue across both themes", () => {
        expect(oklch(preset.dark.brand).h).toBeCloseTo(
          oklch(preset.light.brand).h,
          0,
        );
      });
    });
  }
});

describe("a typed accent colour", () => {
  it.each([
    ["#4a5bd6", "hex"],
    ["#f80", "short hex"],
    ["rgb(74, 91, 214)", "rgb()"],
    ["oklch(0.55 0.19 269)", "oklch()"],
    ["  #4A5BD6  ", "surrounding space"],
  ])("accepts %s (%s) and produces a readable pair", (value) => {
    const pair = accentPair(value);
    expect(pair).not.toBeNull();
    if (!pair) return;
    for (const theme of ["light", "dark"] as const) {
      const brand = oklch(pair[theme].brand);
      expect(
        contrastRatio(brand, oklch(pair[theme]["brand-foreground"])),
      ).toBeGreaterThanOrEqual(AA);
      for (const surface of CHECKS[theme]) {
        expect(contrastRatio(brand, surface.color)).toBeGreaterThanOrEqual(AA);
      }
    }
  });

  it("pulls a too-light colour down for light mode and up for dark", () => {
    // Pure yellow is the worst case: unusable as light-mode text or as a fill
    // behind white, perfect in dark mode.
    const pair = accentPair("#ffee00");
    expect(pair).not.toBeNull();
    if (!pair) return;
    expect(oklch(pair.light.brand).l).toBeLessThan(0.7);
    expect(oklch(pair.dark.brand).l).toBeGreaterThan(oklch(pair.light.brand).l);
  });

  it("gamut-maps an extreme OKLCH colour before checking its contrast", () => {
    const pair = accentPair("oklch(0.01 0.23 180)");
    expect(pair).not.toBeNull();
    if (!pair) return;

    for (const theme of ["light", "dark"] as const) {
      const brand = oklch(pair[theme].brand);
      expect(
        contrastRatio(brand, oklch(pair[theme]["brand-foreground"])),
      ).toBeGreaterThanOrEqual(AA);
      for (const surface of CHECKS[theme]) {
        expect(contrastRatio(brand, surface.color)).toBeGreaterThanOrEqual(AA);
      }
    }
  });

  it("refuses a colour it cannot measure rather than applying it", () => {
    expect(accentPair("rebeccapurple")).toBeNull();
    expect(accentPair("var(--primary)")).toBeNull();
    expect(accentPair("not a colour")).toBeNull();
    expect(accentPair("")).toBeNull();
  });
});

describe("isAccentActive", () => {
  it("matches only when both halves of the pair match", () => {
    const [blue, indigo] = ACCENT_PRESETS;
    expect(isAccentActive({ light: blue.light, dark: blue.dark }, blue)).toBe(
      true,
    );
    expect(isAccentActive({ light: blue.light, dark: indigo.dark }, blue)).toBe(
      false,
    );
    expect(
      isAccentActive(
        {
          light: { ...blue.light, "brand-foreground": "oklch(0.4 0 0)" },
          dark: blue.dark,
        },
        blue,
      ),
    ).toBe(false);
    expect(isAccentActive({ light: {}, dark: {} }, blue)).toBe(false);
  });
});
