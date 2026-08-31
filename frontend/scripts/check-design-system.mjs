#!/usr/bin/env node
/**
 * Mechanical enforcement of the DESIGN.md rules that are easiest to break and
 * hardest to spot in review.
 *
 * This is a STATIC, source-level guard. It parses .css/.ts/.tsx files and
 * DESIGN.md's own prose — it never launches a browser. Rendered/runtime
 * properties (contrast as actually painted, computed styles, visual
 * regressions) are Playwright's job, not this script's — see DESIGN.md §19.
 *
 * Run via `npm run lint:design`, `npm test` or `npm run verify`.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

/** Files that legitimately hold raw values — the token and typography layers. */
const VALUE_LAYER = [
  "src/styles/tokens.css",
  "src/styles/base.css",
  "src/styles/prose.css",
  "src/styles/fonts.css",
  "src/styles/util.css",
];

/** The one sanctioned data-palette exception (DESIGN.md §3) — literal hex
 *  arrays that are content a user picks, not a piece of Journiv's theme. */
const DATA_PALETTE_FILES = ["src/lib/journalColors.ts"];

/** Registry components kept close to upstream (DESIGN.md §18) are exempt from
 *  the arbitrary-Tailwind-value check — re-skinning them to avoid a bracketed
 *  value would violate the "don't rewrite a registry component" rule. */
const REGISTRY_DIR = "src/components/ui/";

/** CSS custom properties that are legitimately never `--name: value;`
 *  declared in any stylesheet: set inline from API data by JS (DESIGN.md §3),
 *  or owned by a vendor (base-ui) whose CSS we don't author. */
const RUNTIME_OR_VENDOR_VARS = new Set([
  "--journal-accent",
  "--mood-accent",
  "--entity-accent",
]);

/** `--name` prefixes that exist only to bridge tokens into Tailwind's
 *  `@theme inline` utility generator (src/styles/index.css) — consumed by
 *  Tailwind's compiler via class names (`bg-primary`, `rounded-md`, …), never
 *  by a textual `var(--color-primary)` in our own code. A dead-token check
 *  that doesn't know this would flag all of them. */
const THEME_BRIDGE_PREFIX = /^--(color|radius|font)-/;

/** The two layout breakpoints (DESIGN.md §9) plus every current
 *  component-level breakpoint, named there. A new *page*-shaped breakpoint
 *  must be one of the two layout widths; a new *component* breakpoint must be
 *  added here and named in DESIGN.md §9 — this check is a "confirm and
 *  document" gate, not a ban. */
const ALLOWED_BREAKPOINTS = new Set([
  "860px",
  "1100px",
  "1101px", // paired with 1100px's max-width to avoid a 1-pixel overlap
  "620px", // settings.css row layout, users.css heading
  "520px", // tags.css stat grid
  "640px", // tags.css controls wrap
  "768px", // util.css .jv-field font-size
  "34rem", // editor.css conflict banner wrap
]);

/** Token facts documented as a literal value in DESIGN.md prose, cross-checked
 *  against their `tokens.css` definition so the two cannot silently diverge
 *  (this is exactly the class of bug — a documented radius scale nobody
 *  updated after the tokens changed — that motivated this check). Each entry:
 *  the CSS custom property name, and how it appears in DESIGN.md prose
 *  (```--name` <value>`` or ``--name`` <value>``, both used depending on
 *  section). */
const TOKEN_FACTS = [
  "radius-xs",
  "radius-sm",
  "radius-md",
  "radius-lg",
  "bar-height",
  "reader-measure",
  "tap-target",
  "duration-fast",
];

function walk(dir, extensions) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      return name === "generated" ? [] : walk(path, extensions);
    }
    return extensions.some((extension) => name.endsWith(extension))
      ? [path]
      : [];
  });
}

/** Strips comments, so a hex code in an explanatory note is not a violation. */
const withoutComments = (source) =>
  source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

function scan(files, pattern) {
  const found = [];
  for (const file of files) {
    withoutComments(readFileSync(file, "utf8"))
      .split("\n")
      .forEach((text, index) => {
        if (pattern.test(text)) {
          found.push({ file, line: index + 1, text: text.trim() });
        }
      });
  }
  return found;
}

const cssFiles = walk("src", [".css"]);
const featureCss = cssFiles.filter((file) => !VALUE_LAYER.includes(file));
const sourceFiles = walk("src", [".tsx", ".ts"]).filter(
  (file) => !/\.test\.tsx?$/.test(file),
);
const productFiles = sourceFiles.filter(
  (file) => !file.startsWith(REGISTRY_DIR),
);

// A broken walk would make every check pass vacuously.
if (cssFiles.length < 5 || featureCss.length < 3 || sourceFiles.length < 20) {
  console.error(
    `check-design-system: found too few files to scan ` +
      `(${cssFiles.length} css, ${sourceFiles.length} source). ` +
      `Run this from journiv-backend/frontend.`,
  );
  process.exit(2);
}

const lineChecks = [
  {
    name: "raw colour outside the token layer",
    files: featureCss,
    pattern: /(#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\boklch\(|\boklab\()/,
    fix:
      `Use an existing semantic token, or add one to src/styles/tokens.css and\n` +
      `document it in DESIGN.md §3. Raw values belong only in:\n` +
      `  ${VALUE_LAYER.join("\n  ")}`,
  },
  {
    name: "px font-size",
    files: cssFiles,
    pattern: /font-size:\s*[0-9.]+px/,
    fix:
      `A px font-size ignores the reader's browser text scaling. Use rem or em,\n` +
      `or a role class from src/styles/base.css (DESIGN.md §4).`,
  },
  {
    name: "!important outside the reduced-motion reset",
    files: cssFiles.filter((file) => file !== "src/styles/base.css"),
    pattern: /!important/,
    fix: `!important is sanctioned only for the reduced-motion reset (DESIGN.md §8).`,
  },
  {
    name: "hard-coded colour in an inline style",
    files: sourceFiles,
    pattern: /style=\{\{[^}]*(#[0-9a-fA-F]{3,8}\b|\brgba?\(|\boklch\()/,
    fix:
      `Inline styles may pass a token or an API-provided value (a journal or mood\n` +
      `colour), never a hard-coded one.`,
  },
  {
    name: "direct crypto.randomUUID call",
    files: sourceFiles.filter((file) => file !== "src/lib/uuid.ts"),
    pattern: /crypto\.randomUUID/,
    fix:
      `crypto.randomUUID is undefined outside a secure context, and self-hosted\n` +
      `Journiv is commonly reached over plain HTTP on a LAN — attaching a photo\n` +
      `threw there and did nothing. Use uuid() from src/lib/uuid.ts.`,
  },
  {
    name: "raw colour in a Tailwind arbitrary-value utility",
    files: productFiles.filter((file) => !DATA_PALETTE_FILES.includes(file)),
    pattern:
      /\b(?:bg|text|border|ring|fill|stroke|from|via|to|shadow|outline|decoration|accent|caret|divide)-\[#[0-9a-fA-F]{3,8}\]/,
    fix:
      `A bracketed Tailwind colour utility (e.g. bg-[#405DE6]) bypasses every\n` +
      `token. Use the semantic Tailwind class (bg-primary, text-muted-foreground,\n` +
      `…) that already resolves through index.css's --color-* map (DESIGN.md §3).`,
  },
  {
    name: "arbitrary spacing or font-size Tailwind value",
    files: productFiles,
    pattern:
      /\b(?:m|p)[trblxy]?-\[[0-9.]+(?:px|rem|em)\]|\bgap(?:-x|-y)?-\[[0-9.]+(?:px|rem|em)\]|\btext-\[[0-9.]+(?:px|rem|em)\]/,
    fix:
      `DESIGN.md §3: "Do not write mt-[13px]." Use the spacing scale\n` +
      `(--space-1…--space-16 / gap-1, gap-2, …) or a typographic role class from\n` +
      `src/styles/base.css instead of a bracketed pixel/rem value.`,
  },
];

let failed = 0;
for (const check of lineChecks) {
  const violations = scan(check.files, check.pattern);
  if (!violations.length) continue;
  failed += violations.length;
  console.error(`\n✗ ${check.name}\n`);
  for (const violation of violations) {
    console.error(`    ${violation.file}:${violation.line}  ${violation.text}`);
  }
  console.error(`\n  ${check.fix.split("\n").join("\n  ")}\n`);
}

// ---------------------------------------------------------------------------
// Structural checks: these need more than "does this line match a pattern",
// so they are hand-written rather than run through `lineChecks`/`scan`.
// ---------------------------------------------------------------------------

function report(name, violations, fix) {
  if (!violations.length) return 0;
  console.error(`\n✗ ${name}\n`);
  for (const line of violations) console.error(`    ${line}`);
  console.error(`\n  ${fix.split("\n").join("\n  ")}\n`);
  return violations.length;
}

/** Every `var(--x)` used in a stylesheet must resolve to a real `--x: …;`
 *  declaration somewhere, or be one of the sanctioned runtime/vendor names.
 *  This is the check that would have caught `var(--line)` resolving to
 *  nothing in a real border-bottom rule — a bug the design guard did not
 *  previously catch because nothing verified property NAMES, only literal
 *  colour/size VALUES. */
function checkUndefinedCustomProperties() {
  const defined = new Set();
  for (const file of cssFiles) {
    for (const m of withoutComments(readFileSync(file, "utf8")).matchAll(
      /^\s*(--[a-zA-Z0-9-]+)\s*:/gm,
    )) {
      defined.add(m[1]);
    }
  }
  const violations = [];
  for (const file of cssFiles) {
    withoutComments(readFileSync(file, "utf8"))
      .split("\n")
      .forEach((text, index) => {
        for (const m of text.matchAll(/var\(\s*(--[a-zA-Z0-9-]+)/g)) {
          const name = m[1];
          if (!defined.has(name) && !RUNTIME_OR_VENDOR_VARS.has(name)) {
            violations.push(
              `${file}:${index + 1}  var(${name}) — never declared`,
            );
          }
        }
      });
  }
  return report(
    "undefined CSS custom property",
    violations,
    `This property is not declared \`--name: value;\` in any stylesheet, and\n` +
      `is not one of the sanctioned runtime/vendor names\n` +
      `(${[...RUNTIME_OR_VENDOR_VARS].join(", ")}). A typo here silently\n` +
      `resolves to nothing — the browser drops the whole declaration — so it\n` +
      `never throws and rarely gets noticed in review. Fix the name, or add it\n` +
      `to tokens.css and document it in DESIGN.md §3.`,
  );
}

/** A token declared in tokens.css that nothing consumes is either dead code
 *  or a promise DESIGN.md makes that the product doesn't keep. Either way it
 *  should be resolved, not left to rot — this is exactly how `--state-pressed`
 *  and `--duration-base` were found. */
function checkDeadTokens() {
  const defined = new Map(); // name -> file:line
  for (const file of cssFiles) {
    withoutComments(readFileSync(file, "utf8"))
      .split("\n")
      .forEach((text, index) => {
        const m = text.match(/^\s*(--[a-zA-Z0-9-]+)\s*:/);
        if (m) defined.set(m[1], `${file}:${index + 1}`);
      });
  }
  const used = new Set();
  for (const file of cssFiles) {
    for (const m of readFileSync(file, "utf8").matchAll(
      /var\(\s*(--[a-zA-Z0-9-]+)/g,
    )) {
      used.add(m[1]);
    }
  }
  const violations = [];
  for (const [name, where] of defined) {
    if (!used.has(name) && !THEME_BRIDGE_PREFIX.test(name)) {
      violations.push(`${where}  ${name} — no var(${name}) anywhere`);
    }
  }
  return report(
    "dead token",
    violations,
    `Defined in tokens.css but nothing reads it. Either give it a real\n` +
      `consumer, or remove it and its mention in DESIGN.md — a token with no\n` +
      `consumer is a claim the design system isn't keeping.`,
  );
}

/** Every `[text](src/...)` link in DESIGN.md must resolve to a real file or
 *  directory. A stale link (a rename the doc missed) sends the next agent
 *  looking for a file that isn't there. */
function checkDesignMdLinks() {
  const designMd = readFileSync("DESIGN.md", "utf8");
  const violations = [];
  const seen = new Set();
  for (const m of designMd.matchAll(/\]\((src\/[^)]+)\)/g)) {
    const target = m[1];
    if (seen.has(target)) continue;
    seen.add(target);
    try {
      statSync(target);
    } catch {
      violations.push(`DESIGN.md links to ${target} — does not exist`);
    }
  }
  return report(
    "broken DESIGN.md link",
    violations,
    `Fix the path, or the file this linked to before continuing — a broken\n` +
      `link sends the next reader (human or agent) looking for something that\n` +
      `moved or was renamed.`,
  );
}

/** A page-shaped breakpoint at a width nobody has named is exactly how "one
 *  breakpoint system" quietly became seven. This does not forbid a new
 *  component breakpoint — it forces it to be named in ALLOWED_BREAKPOINTS
 *  (and, by the same change, in DESIGN.md §9) rather than added silently. */
function checkBreakpoints() {
  const violations = [];
  for (const file of cssFiles) {
    withoutComments(readFileSync(file, "utf8"))
      .split("\n")
      .forEach((text, index) => {
        if (!/@media/.test(text)) return;
        for (const m of text.matchAll(/([0-9.]+(?:px|rem))/g)) {
          if (!ALLOWED_BREAKPOINTS.has(m[1])) {
            violations.push(
              `${file}:${index + 1}  ${text.trim()} — ${m[1]} is not an allowed breakpoint`,
            );
          }
        }
      });
  }
  return report(
    "unlisted breakpoint",
    violations,
    `DESIGN.md §9 names exactly two layout breakpoints (860px, 1100px/1101px)\n` +
      `plus a fixed list of component-level ones. A new *page*-shaped\n` +
      `breakpoint (a pane restructuring) must be one of the two layout widths.\n` +
      `A new *component* breakpoint (one control reflowing at its own width) is\n` +
      `fine — add it to ALLOWED_BREAKPOINTS in this script and name it in\n` +
      `DESIGN.md §9's component-breakpoint list.`,
  );
}

/** Cross-checks a handful of literal values DESIGN.md documents in prose
 *  (the radius scale, layout constants) against their tokens.css definition,
 *  so a token change and its documentation cannot silently drift apart — the
 *  exact failure mode that let the radius scale in DESIGN.md describe values
 *  the app hadn't rendered in months. This validates literal VALUES; rendered
 *  contrast and other computed/cascaded properties are Playwright's job. */
function checkTokenFacts() {
  const tokensCss = readFileSync("src/styles/tokens.css", "utf8");
  const designMd = readFileSync("DESIGN.md", "utf8");
  const violations = [];

  for (const name of TOKEN_FACTS) {
    const defMatch = tokensCss.match(
      new RegExp(`--${name}:\\s*([0-9.]+[a-zA-Z]+)`),
    );
    const docMatch = designMd.match(
      new RegExp(`\`--${name}\`\\s+([0-9.]+[a-zA-Z]+)`),
    );
    if (!defMatch) {
      violations.push(
        `--${name} is a documented token fact but is not declared in tokens.css`,
      );
      continue;
    }
    if (!docMatch) {
      violations.push(
        `--${name} is ${defMatch[1]} in tokens.css but DESIGN.md never states its value`,
      );
      continue;
    }
    if (defMatch[1] !== docMatch[1]) {
      violations.push(
        `--${name} is ${defMatch[1]} in tokens.css but DESIGN.md says ${docMatch[1]}`,
      );
    }
  }

  // The spacing scale is documented as one ordered sequence, not per-token —
  // "4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 as --space-1 … --space-16" — so it is
  // checked positionally against tokens.css's own declaration order.
  const spaceValues = [
    ...tokensCss.matchAll(/--space-\d+:\s*([0-9.]+px)/g),
  ].map((m) => m[1]);
  const docSpacing = designMd.match(/^Spacing:\s*([0-9\s/]+)\s*as `--space-1/m);
  if (docSpacing) {
    const documented = docSpacing[1].split("/").map((n) => `${n.trim()}px`);
    if (JSON.stringify(documented) !== JSON.stringify(spaceValues)) {
      violations.push(
        `Spacing scale in tokens.css (${spaceValues.join(", ")}) does not match ` +
          `DESIGN.md's documented sequence (${documented.join(", ")})`,
      );
    }
  }

  return report(
    "token fact drifted from DESIGN.md",
    violations,
    `A value in tokens.css no longer matches what DESIGN.md's prose states.\n` +
      `Update whichever one is wrong — usually the doc, since tokens.css is the\n` +
      `thing that actually renders — in the same change.`,
  );
}

failed += checkUndefinedCustomProperties();
failed += checkDeadTokens();
failed += checkDesignMdLinks();
failed += checkBreakpoints();
failed += checkTokenFacts();

if (failed) {
  console.error(
    `check-design-system: ${failed} violation${failed === 1 ? "" : "s"}. ` +
      `See DESIGN.md.\n`,
  );
  process.exit(1);
}

console.log(
  `check-design-system: clean ` +
    `(${cssFiles.length} stylesheets, ${sourceFiles.length} source files).`,
);
