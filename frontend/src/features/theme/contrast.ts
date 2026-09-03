/**
 * The colour maths behind the accent picker (DESIGN.md, docs/features/personalization.md).
 *
 * Journiv's accent is `--brand`, and `--brand` is not decoration: it is a
 * filled button's background, the selection rail, the focus ring, and the
 * colour of links in prose. Three of those four put *text* on or in it, so an
 * accent is only usable if it clears 4.5:1 both against the surface it sits on
 * and against its own `--brand-foreground`. Nothing else in the theme has that
 * property, which is why this lives here and not in `lib/color.ts`.
 *
 * WCAG 2.1 relative luminance is defined on sRGB, so everything converts to
 * linear sRGB first. Out-of-gamut OKLCH is gamut-mapped by reducing chroma at
 * constant lightness and hue before it is measured, rather than clipping RGB
 * channels. That gives the contrast code the same in-gamut colour it emits.
 */

export interface Oklch {
  /** Perceptual lightness, 0-1. */
  l: number;
  /** Chroma. */
  c: number;
  /** Hue in degrees. */
  h: number;
}

/** oklch -> linear-light sRGB. */
function oklchToLinearSrgb({ l, c, h }: Oklch): [number, number, number] {
  const rad = (h * Math.PI) / 180;
  const a = c * Math.cos(rad);
  const b = c * Math.sin(rad);
  const l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s_ = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
    -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
    -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_,
  ];
}

function isSrgbInGamut(color: Oklch): boolean {
  return oklchToLinearSrgb(color).every(
    (channel) => Number.isFinite(channel) && channel >= 0 && channel <= 1,
  );
}

/** Maps OKLCH to sRGB using CSS Color's constant-lightness, constant-hue
 * chroma reduction. The binary search keeps emitted accent tokens in gamut,
 * so their measured and rendered colours are the same. */
export function gamutMapToSrgb(color: Oklch): Oklch {
  if (color.l <= 0 || color.l >= 1) return { ...color, c: 0 };
  if (isSrgbInGamut(color)) return color;

  let low = 0;
  let high = color.c;
  for (let i = 0; i < 24; i++) {
    const c = (low + high) / 2;
    if (isSrgbInGamut({ ...color, c })) low = c;
    else high = c;
  }
  return { ...color, c: low };
}

function linearSrgbToOklch([r, g, b]: [number, number, number]): Oklch {
  const l_ = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m_ = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s_ = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const l = 0.2104542553 * l_ + 0.793617785 * m_ - 0.0040720468 * s_;
  const a = 1.9779984951 * l_ - 2.428592205 * m_ + 0.4505937099 * s_;
  const bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.808675766 * s_;
  const h = (Math.atan2(bb, a) * 180) / Math.PI;
  return { l, c: Math.hypot(a, bb), h: h < 0 ? h + 360 : h };
}

const srgbToLinear = (v: number) =>
  v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;

const NUM = String.raw`[-+]?[\d.]+%?`;
const OKLCH_RE = new RegExp(
  String.raw`^oklch\(\s*(${NUM})\s+(${NUM})\s+(${NUM})(?:deg)?\s*(?:\/[^)]*)?\)$`,
  "i",
);
const RGB_RE = new RegExp(
  String.raw`^rgba?\(\s*(${NUM})[\s,]+(${NUM})[\s,]+(${NUM})\s*(?:[,/][^)]*)?\)$`,
  "i",
);

const pct = (raw: string, whole: number) =>
  raw.endsWith("%") ? (Number.parseFloat(raw) / 100) * whole : Number(raw);

/**
 * Parses the colour syntaxes the accent field documents - `oklch()`, `#rgb`,
 * `#rrggbb` and `rgb()`. Anything else returns `null` and the caller refuses
 * the value rather than applying a colour it cannot check. This is not a
 * general CSS colour parser and should not grow into one; a theme *import*
 * carries its own foreground pair and never comes through here.
 */
export function parseAccentColor(value: string): Oklch | null {
  const raw = value.trim();
  if (!raw) return null;

  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(raw);
  if (hex) {
    const digits = hex[1];
    const full =
      digits.length === 3
        ? digits
            .split("")
            .map((ch) => ch + ch)
            .join("")
        : digits;
    const n = Number.parseInt(full, 16);
    return linearSrgbToOklch([
      srgbToLinear(((n >> 16) & 255) / 255),
      srgbToLinear(((n >> 8) & 255) / 255),
      srgbToLinear((n & 255) / 255),
    ]);
  }

  const rgb = RGB_RE.exec(raw);
  if (rgb) {
    const channels = rgb.slice(1, 4).map((v) => pct(v, 255) / 255);
    if (channels.some((v) => !Number.isFinite(v))) return null;
    const [r, g, b] = channels.map((v) =>
      srgbToLinear(Math.min(1, Math.max(0, v))),
    );
    return linearSrgbToOklch([r, g, b]);
  }

  const ok = OKLCH_RE.exec(raw);
  if (ok) {
    const l = pct(ok[1], 1);
    const c = pct(ok[2], 0.4);
    const h = Number.parseFloat(ok[3]);
    if (![l, c, h].every(Number.isFinite)) return null;
    return { l: Math.min(1, Math.max(0, l)), c: Math.max(0, c), h };
  }

  return null;
}

/** WCAG 2.1 relative luminance of an oklch colour. */
export function relativeLuminance(color: Oklch): number {
  const [r, g, b] = oklchToLinearSrgb(gamutMapToSrgb(color));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG 2.1 contrast ratio, 1-21. The argument order does not matter. */
export function contrastRatio(a: Oklch, b: Oklch): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

export function formatOklch({ l, c, h }: Oklch): string {
  const round = (value: number, places: number) =>
    Number(value.toFixed(places)).toString();
  return `oklch(${round(l, 3)} ${round(c, 3)} ${round(h, 1)})`;
}
