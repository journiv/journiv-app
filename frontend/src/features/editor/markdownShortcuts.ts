import { Delta } from "quill";
import type Quill from "quill";
import type { JOURNIV_DELTA_FORMATS } from "./deltaProfile";
import { validateLinkUrl } from "./linkPolicy";

/**
 * Markdown *input* shortcuts for the writing surface.
 *
 * This is an input method, not a storage format: typed shorthand is rewritten
 * into exactly the same Delta the toolbar would have produced, and nothing here
 * can emit an attribute outside the Gate-1 allowlist
 * (`JOURNIV_DELTA_FORMATS`). Persisted content stays a Quill Delta — see
 * docs/features/editor.md.
 *
 * Scope: this module owns the block markers Quill does **not** — `#`/`##`/`###`
 * and `>` — plus inline `**`/`__`, `*`/`_`, `~~` and `[text](url)`. Bullet and
 * ordered lists come from Quill's own `list autofill` keyboard binding (narrowed
 * to `1.`/`-`/`*` in QuillSurface); this module deliberately does not duplicate
 * them, which is also why nothing here is deferred — `#` and `>` apply cleanly
 * inside the text-change, only a `<p>`→`<ol>` swap does not.
 *
 * These are typing shortcuts, not a CommonMark parser. The rules are
 * deliberately narrow and never *partially* transform:
 *
 *   - Escaping is positional, not a backslash mechanism. A block marker fires
 *     only when the text from line start to caret is *exactly* the marker plus
 *     one space, so any preceding character — `\`, a space, other prose — leaves
 *     it literal. An inline run fires only when its opening delimiter is at the
 *     start of the line or right after whitespace, so `foo_bar_`, `2*3*`,
 *     `word**x**` and `\*x\*` are all left as typed. Backslashes are never
 *     consumed or interpreted; they simply sit before a delimiter and, being
 *     non-whitespace, stop the match.
 *   - Nested or multi-level markdown (`***x***`, `**_x_**`), adjacent delimiters
 *     (`****`, `* *`), unsupported constructs (`` `code` ``, `![img]()`, `+ `,
 *     `#### `, setext headings) and malformed or unsafe links (`[x]()`,
 *     `[x](javascript:…)`) are left completely literal.
 *
 * Two halves:
 *   - `detectBlockShortcut` / `detectInlineShortcut` are pure string logic and
 *     carry the whole behaviour contract (boundaries, escaping, validation).
 *   - `installMarkdownShortcuts` is the thin Quill binding that applies a match
 *     as a single, undoable `"user"` change.
 */

export type BlockShortcut = {
  kind: "block";
  /** Gate-1 line format to apply across the line. */
  format: "header" | "blockquote";
  value: 1 | 2 | 3 | true;
  /** Characters to remove from the start of the line (marker + its space). */
  markerLength: number;
};

export type InlineShortcut = {
  kind: "inline";
  format: "bold" | "italic" | "strike" | "link";
  /** Line offsets of the run to replace, `[start, end)`. `end` is the caret. */
  start: number;
  end: number;
  /** Text that survives, with the marker characters stripped. */
  text: string;
  /** Present only for links; already passed `validateLinkUrl`. */
  link?: string;
};

/** Characters whose insertion can complete a shortcut. */
export const TRIGGER_CHARACTERS = [" ", "*", "_", "~", ")"] as const;

const BLOCK_RULES: Array<{
  pattern: RegExp;
  build: (match: RegExpMatchArray) => BlockShortcut;
}> = [
  {
    // #, ##, ### only. Four or more hashes is not a Journiv heading and stays
    // literal.
    pattern: /^(#{1,3}) $/,
    build: (match) => ({
      kind: "block",
      format: "header",
      value: match[1].length as 1 | 2 | 3,
      markerLength: match[1].length + 1,
    }),
  },
  {
    pattern: /^> $/,
    build: () => ({
      kind: "block",
      format: "blockquote",
      value: true,
      markerLength: 2,
    }),
  },
];

/**
 * A block shortcut for `lineBeforeCaret`, or `null`.
 *
 * `lineBeforeCaret` is the text from the start of the current line up to the
 * caret. A rule fires only when that whole slice is the marker followed by one
 * space, so ordinary prose ("a > b ") is never rewritten and a leading
 * backslash ("\\# ") keeps the text literal. Bullet and ordered lists are
 * Quill's own keyboard binding, not this module.
 */
export function detectBlockShortcut(
  lineBeforeCaret: string,
): BlockShortcut | null {
  for (const rule of BLOCK_RULES) {
    const match = lineBeforeCaret.match(rule.pattern);
    if (match) return rule.build(match);
  }
  return null;
}

// Inline runs: the opening delimiter must sit at the start of the slice or
// right after whitespace (`(?<!\S)` — which also rejects a `\`-escaped
// delimiter and a second delimiter of `**`/`__`), then a non-space/non-marker
// first character, a lazy middle, a non-space/non-marker last character, and
// the closing delimiter at the very end of the slice.
const BOLD_PATTERN = /(?<!\S)(\*\*|__)([^\s*_](?:[^*_\n]*[^\s*_])?)\1$/;
const ITALIC_PATTERN = /(?<!\S)([*_])([^\s*_](?:[^*_\n]*[^\s*_])?)\1$/;
const STRIKE_PATTERN = /(?<!\S)(~~)([^\s~](?:[^~\n]*[^\s~])?)~~$/;
// A link keeps only its `\`-escape guard: the `[text](url)` shape is specific
// enough that a word boundary would just block legitimate uses like "note.[a](…)".
const LINK_PATTERN = /(?<!\\)\[([^\]\n]+)\]\(([^)\s\n]+)\)$/;

/**
 * An inline shortcut ending at the caret, or `null`.
 *
 * Order matters: bold is tested before italic so `**x**` is not read as
 * `*` + `x*`. A link whose URL is not http/https/mailto fails `validateLinkUrl`
 * and is left as literal text rather than rewritten.
 */
export function detectInlineShortcut(
  lineBeforeCaret: string,
): InlineShortcut | null {
  const caret = lineBeforeCaret.length;

  const bold = lineBeforeCaret.match(BOLD_PATTERN);
  if (bold) {
    return {
      kind: "inline",
      format: "bold",
      start: caret - bold[0].length,
      end: caret,
      text: bold[2],
    };
  }

  const strike = lineBeforeCaret.match(STRIKE_PATTERN);
  if (strike) {
    return {
      kind: "inline",
      format: "strike",
      start: caret - strike[0].length,
      end: caret,
      text: strike[2],
    };
  }

  const italic = lineBeforeCaret.match(ITALIC_PATTERN);
  if (italic) {
    return {
      kind: "inline",
      format: "italic",
      start: caret - italic[0].length,
      end: caret,
      text: italic[2],
    };
  }

  const link = lineBeforeCaret.match(LINK_PATTERN);
  if (link) {
    const href = validateLinkUrl(link[2]);
    if (!href) return null;
    return {
      kind: "inline",
      format: "link",
      start: caret - link[0].length,
      end: caret,
      text: link[1],
      link: href,
    };
  }

  return null;
}

type ChangeDelta = { ops?: ReadonlyArray<Record<string, unknown>> };

/**
 * The plain single-character type this change represents, or `null`.
 *
 * A shortcut only ever completes on a lone typed character. Anything else — a
 * paste, a deletion, typing over a selection (which Quill emits as
 * insert + delete), an embed, a formatting-only change, an IME commit of more
 * than one character — returns `null` and is ignored, so shortcuts never fire
 * unexpectedly.
 */
export function typedInsertion(
  delta: ChangeDelta,
): { char: string; index: number } | null {
  const ops = delta.ops ?? [];
  if (ops.length === 0 || ops.length > 2) return null;
  let insert: unknown;
  let index = 0;
  for (const op of ops) {
    if ("delete" in op || "attributes" in op) return null;
    if ("retain" in op) {
      if (typeof op.retain !== "number" || ops.length !== 2) return null;
      index = op.retain;
    }
    if ("insert" in op) {
      if (insert !== undefined) return null;
      insert = op.insert;
    }
  }
  if (typeof insert !== "string" || insert.length !== 1) return null;
  return { char: insert, index };
}

type InstallOptions = {
  /** Whether shortcuts may rewrite the current user change. */
  isEnabled?: () => boolean;
  /** Suppress rewrites while an IME composition is active. */
  isComposing?: () => boolean;
  /**
   * Called after a rewrite, with the document index the caret was left at, so
   * the host can re-emit editor state.
   */
  onApplied?: (caretIndex: number) => void;
};

/**
 * Binds markdown input shortcuts to a Quill instance. Returns a teardown that
 * removes the listener.
 *
 * A rewrite is one `"user"` change bracketed by `history.cutoff()`, so a single
 * undo restores the literal markdown that triggered it and a second undo
 * removes the text that was typed before it. Everything is synchronous: this
 * module never touches lists, so there is no `<p>`→`<ol>` swap to defer.
 */
export function installMarkdownShortcuts(
  quill: Quill,
  options: InstallOptions = {},
): () => void {
  let applying = false;

  /** Runs `mutate` as one undoable `"user"` change, isolated in history so a
   *  single undo reverts exactly it. */
  const asOneUndoStep = (mutate: () => void) => {
    applying = true;
    try {
      quill.history.cutoff();
      mutate();
      quill.history.cutoff();
    } finally {
      applying = false;
    }
  };

  const applyBlock = (
    lineStart: number,
    lineLength: number,
    shortcut: BlockShortcut,
  ) => {
    // Everything after the marker, up to but not including the line's "\n".
    const trailing = Math.max(lineLength - 1 - shortcut.markerLength, 0);
    asOneUndoStep(() => {
      quill.updateContents(
        new Delta()
          .retain(lineStart)
          .delete(shortcut.markerLength)
          .retain(trailing)
          .retain(1, { [shortcut.format]: shortcut.value }),
        "user",
      );
      quill.setSelection(lineStart, 0, "silent");
    });
    options.onApplied?.(lineStart);
  };

  const applyInline = (lineStart: number, shortcut: InlineShortcut) => {
    const from = lineStart + shortcut.start;
    const runLength = shortcut.end - shortcut.start;
    const attributeValue = shortcut.format === "link" ? shortcut.link : true;
    const caretAfter = from + shortcut.text.length;

    asOneUndoStep(() => {
      quill.updateContents(
        new Delta()
          .retain(from)
          .delete(runLength)
          .insert(shortcut.text, { [shortcut.format]: attributeValue }),
        "user",
      );
      quill.setSelection(caretAfter, 0, "silent");
      // Stop the run so the next keystroke is unformatted, matching what a
      // toolbar toggle would leave behind.
      quill.format(shortcut.format, false, "user");
    });
    options.onApplied?.(caretAfter);
  };

  const handleTextChange = (
    delta: ChangeDelta,
    _old: unknown,
    source: string,
  ) => {
    if (applying || source !== "user") return;
    if (options.isEnabled?.() === false) return;
    if (options.isComposing?.()) return;

    const typed = typedInsertion(delta);
    if (
      typed === null ||
      !(TRIGGER_CHARACTERS as readonly string[]).includes(typed.char)
    )
      return;

    // The caret is derived from the change itself, not `getSelection()`: this
    // runs inside the synchronous text-change, before the browser selection has
    // settled.
    const caret = typed.index + 1;
    const [line, offsetInLine] = quill.getLine(caret);
    if (!line) return;
    const lineStart = caret - offsetInLine;
    const lineBeforeCaret = quill.getText(lineStart, offsetInLine);

    if (typed.char === " ") {
      const block = detectBlockShortcut(lineBeforeCaret);
      if (!block) return;
      // Never re-format a line that already carries a block format.
      const existing = quill.getFormat(lineStart, Math.max(offsetInLine, 1));
      if (
        existing.header != null ||
        existing.list != null ||
        existing.blockquote != null
      )
        return;
      applyBlock(lineStart, line.length(), block);
      return;
    }

    const inline = detectInlineShortcut(lineBeforeCaret);
    if (inline) applyInline(lineStart, inline);
  };

  quill.on("text-change", handleTextChange);
  return () => quill.off("text-change", handleTextChange);
}

/**
 * Every attribute this module can produce is in the Gate-1 allowlist. A test
 * pins this so a future rule cannot quietly widen what the editor saves.
 */
export const MARKDOWN_SHORTCUT_FORMATS = [
  "header",
  "blockquote",
  "bold",
  "italic",
  "strike",
  "link",
] as const satisfies ReadonlyArray<(typeof JOURNIV_DELTA_FORMATS)[number]>;
