import { COLOR_VAR_SET, type ThemeTokens } from "./types";

export type ParseResult = {
  light: ThemeTokens;
  dark: ThemeTokens;
  /** Human-readable notes for declarations that were dropped. */
  notes: string[];
};

export class ThemeParseError extends Error {}

/** Selectors we read light-mode tokens from. */
const LIGHT_SELECTORS = new Set([":root", "html", ":host", "*"]);
/** Selectors we read dark-mode tokens from. */
const DARK_SELECTORS = new Set([
  ".dark",
  ":root.dark",
  "html.dark",
  ".dark:root",
  '[data-theme="dark"]',
  ':root[data-theme="dark"]',
  '[data-theme="dark"] :root',
]);

/** Function names allowed inside a token value. Anything else — `url(`,
 *  `image-set(`, `element(`, `expression(`, `attr(` … — is rejected. */
const SAFE_FUNCTIONS = new Set([
  "oklch",
  "oklab",
  "rgb",
  "rgba",
  "hsl",
  "hsla",
  "hwb",
  "lab",
  "lch",
  "color",
  "color-mix",
  "calc",
  "min",
  "max",
  "clamp",
  "var",
]);

function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

/** A brace-matched top-level block. */
type Block = { prelude: string; body: string };

/** Splits CSS into top-level `{ … }` blocks, tracking string and paren state so
 *  a brace inside a value or a string is never mistaken for a rule boundary. */
function topLevelBlocks(css: string): Block[] {
  const blocks: Block[] = [];
  let prelude = "";
  let depth = 0;
  let body = "";
  let quote: string | null = null;

  for (let i = 0; i < css.length; i++) {
    const ch = css[i];
    if (quote) {
      if (depth > 0) body += ch;
      else prelude += ch;
      if (ch === quote && css[i - 1] !== "\\") quote = null;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      if (depth > 0) body += ch;
      else prelude += ch;
      continue;
    }
    if (ch === "{") {
      depth++;
      if (depth === 1) continue;
      body += ch;
      continue;
    }
    if (ch === "}") {
      depth--;
      if (depth === 0) {
        blocks.push({ prelude: prelude.trim(), body });
        prelude = "";
        body = "";
        continue;
      }
      body += ch;
      continue;
    }
    if (ch === ";" && depth === 0) {
      // A top-level statement (@import, @charset, @custom-variant …) — it is
      // not a rule prelude, so drop it instead of prepending it to the next.
      prelude = "";
      continue;
    }
    if (depth === 0) prelude += ch;
    else body += ch;
  }
  return blocks;
}

/** Splits a declaration body on top-level `;` (ignoring `;` inside parens). */
function splitDeclarations(body: string): string[] {
  const out: string[] = [];
  let cur = "";
  let paren = 0;
  for (const ch of body) {
    if (ch === "(") paren++;
    else if (ch === ")") paren = Math.max(0, paren - 1);
    if (ch === ";" && paren === 0) {
      out.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  if (cur.trim()) out.push(cur);
  return out;
}

function balancedParens(value: string): boolean {
  let depth = 0;
  for (const ch of value) {
    if (ch === "(") depth++;
    else if (ch === ")") {
      depth--;
      if (depth < 0) return false;
    }
  }
  return depth === 0;
}

/** Rejects a value that could reference an external resource or break out of
 *  the declaration. Structure is lenient; names and values are strict. */
function isSafeValue(value: string): boolean {
  const v = value.trim();
  if (!v) return false;
  if (/[{}<>@\\;]/.test(v)) return false;
  if (/url\s*\(/i.test(v)) return false;
  if (
    /(image|image-set|-webkit-image-set|cross-fade|element|expression|attr)\s*\(/i.test(
      v,
    )
  )
    return false;
  if (/(javascript|data|vbscript)\s*:/i.test(v)) return false;
  if (!balancedParens(v)) return false;
  // Every function call must be on the safe list.
  const fnNames = [...v.matchAll(/([a-zA-Z-]+)\s*\(/g)].map((m) =>
    m[1].toLowerCase(),
  );
  if (fnNames.some((name) => !SAFE_FUNCTIONS.has(name))) return false;
  // A `var(--x)` reference may only target another allowlisted token.
  for (const ref of v.matchAll(/var\(\s*--([a-zA-Z0-9-]+)/g)) {
    if (!COLOR_VAR_SET.has(ref[1])) return false;
  }
  return true;
}

function readTokens(body: string, into: ThemeTokens, notes: string[]): void {
  for (const decl of splitDeclarations(body)) {
    const idx = decl.indexOf(":");
    if (idx < 0) continue;
    const rawName = decl.slice(0, idx).trim();
    const rawValue = decl.slice(idx + 1).trim();
    if (!rawName.startsWith("--")) continue;
    const name = rawName.slice(2);
    if (/^font(-|$)/.test(name)) {
      notes.push(`Ignored --${name}: set fonts with the font pickers.`);
      continue;
    }
    if (!COLOR_VAR_SET.has(name)) continue; // unknown var — silently skip
    if (!isSafeValue(rawValue)) {
      notes.push(`Dropped --${name}: unsupported value.`);
      continue;
    }
    into[name as keyof ThemeTokens] = rawValue;
  }
}

/** Walks blocks, reading `:root` / `.dark` declarations wherever they appear
 *  (including inside `@layer base { … }`), and ignoring everything else. */
function walk(
  blocks: Block[],
  light: ThemeTokens,
  dark: ThemeTokens,
  notes: string[],
): void {
  for (const { prelude, body } of blocks) {
    if (prelude.startsWith("@")) {
      const at = prelude.slice(1).split(/\s/, 1)[0].toLowerCase();
      // These at-rules contain `{}` that are not style rules — do not recurse.
      if (at === "keyframes" || at === "font-face" || at === "property")
        continue;
      walk(topLevelBlocks(body), light, dark, notes);
      continue;
    }
    // A selector list: `:root, html { … }`.
    const selectors = prelude.split(",").map((s) => s.trim());
    if (selectors.some((s) => LIGHT_SELECTORS.has(s))) {
      readTokens(body, light, notes);
    }
    if (selectors.some((s) => DARK_SELECTORS.has(s))) {
      readTokens(body, dark, notes);
    }
  }
}

/**
 * Parses a tweakcn / shadcn "Tailwind v4" theme export. Lenient about
 * structure (unknown selectors, `@theme`, `@layer`, `@custom-variant` are
 * ignored, not rejected); strict about variable names and values. Succeeds
 * whenever at least one recognised colour variable was extracted.
 */
export function parseThemeCss(input: string): ParseResult {
  const css = stripComments(input ?? "");
  const light: ThemeTokens = {};
  const dark: ThemeTokens = {};
  const notes: string[] = [];

  walk(topLevelBlocks(css), light, dark, notes);

  if (Object.keys(light).length === 0 && Object.keys(dark).length === 0) {
    throw new ThemeParseError(
      "No recognised theme variables found. Paste a shadcn / tweakcn theme with a :root { … } block.",
    );
  }
  return { light, dark, notes };
}
