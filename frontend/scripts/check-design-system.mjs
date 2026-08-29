#!/usr/bin/env node
/**
 * Mechanical enforcement of the DESIGN.md rules that are easiest to break and
 * hardest to spot in review.
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

// A broken walk would make every check pass vacuously.
if (cssFiles.length < 5 || featureCss.length < 3 || sourceFiles.length < 20) {
  console.error(
    `check-design-system: found too few files to scan ` +
      `(${cssFiles.length} css, ${sourceFiles.length} source). ` +
      `Run this from journiv-backend/frontend.`,
  );
  process.exit(2);
}

const checks = [
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
];

let failed = 0;
for (const check of checks) {
  const violations = scan(check.files, check.pattern);
  if (!violations.length) continue;
  failed += violations.length;
  console.error(`\n✗ ${check.name}\n`);
  for (const violation of violations) {
    console.error(`    ${violation.file}:${violation.line}  ${violation.text}`);
  }
  console.error(`\n  ${check.fix.split("\n").join("\n  ")}\n`);
}

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
