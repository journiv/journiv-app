import { describe, expect, it } from "vitest";
import { JOURNIV_DELTA_FORMATS } from "./deltaProfile";
import {
  detectBlockShortcut,
  detectInlineShortcut,
  MARKDOWN_SHORTCUT_FORMATS,
  typedInsertion,
} from "./markdownShortcuts";

describe("detectBlockShortcut", () => {
  it("maps hash markers to headings 1-3 only", () => {
    expect(detectBlockShortcut("# ")).toEqual({
      kind: "block",
      format: "header",
      value: 1,
      markerLength: 2,
    });
    expect(detectBlockShortcut("## ")).toMatchObject({ value: 2 });
    expect(detectBlockShortcut("### ")).toMatchObject({ value: 3 });
    // Gate-1 has no h4-h6: left literal.
    expect(detectBlockShortcut("#### ")).toBeNull();
  });

  it("maps the quote marker", () => {
    expect(detectBlockShortcut("> ")).toEqual({
      kind: "block",
      format: "blockquote",
      value: true,
      markerLength: 2,
    });
  });

  it("does not own list markers — Quill's list autofill handles those", () => {
    expect(detectBlockShortcut("- ")).toBeNull();
    expect(detectBlockShortcut("* ")).toBeNull();
    expect(detectBlockShortcut("1. ")).toBeNull();
  });

  it("does not fire inside ordinary prose or on escaped markers", () => {
    expect(detectBlockShortcut("a > b ")).toBeNull();
    expect(detectBlockShortcut("text > ")).toBeNull();
    expect(detectBlockShortcut("\\# ")).toBeNull();
    expect(detectBlockShortcut("  # ")).toBeNull();
    // Marker without exactly one trailing space is not complete.
    expect(detectBlockShortcut("#")).toBeNull();
    expect(detectBlockShortcut("#  ")).toBeNull();
  });
});

describe("detectInlineShortcut", () => {
  it("rewrites bold, italic and strikethrough runs at a word boundary", () => {
    expect(detectInlineShortcut("say **hi**")).toEqual({
      kind: "inline",
      format: "bold",
      start: 4,
      end: 10,
      text: "hi",
    });
    expect(detectInlineShortcut("__hi__")).toMatchObject({
      format: "bold",
      start: 0,
      text: "hi",
    });
    expect(detectInlineShortcut("a *word*")).toMatchObject({
      format: "italic",
      start: 2,
      text: "word",
    });
    expect(detectInlineShortcut("_word_")).toMatchObject({ format: "italic" });
    expect(detectInlineShortcut("~~gone~~")).toMatchObject({
      format: "strike",
      text: "gone",
    });
    // A leading space is a boundary too.
    expect(detectInlineShortcut(" _x_")).toMatchObject({
      format: "italic",
      start: 1,
      text: "x",
    });
  });

  it("prefers bold over italic for a double marker", () => {
    expect(detectInlineShortcut("**x**")).toMatchObject({
      format: "bold",
      text: "x",
    });
  });

  it("requires a whitespace or start-of-line boundary before the opener", () => {
    // Intra-word emphasis: arithmetic and snake_case must survive.
    expect(detectInlineShortcut("foo_bar_")).toBeNull();
    expect(detectInlineShortcut("foo_bar_baz_")).toBeNull();
    expect(detectInlineShortcut("2*3*")).toBeNull();
    expect(detectInlineShortcut("a*b*")).toBeNull();
    expect(detectInlineShortcut("word**bold**")).toBeNull();
    expect(detectInlineShortcut("word~~s~~")).toBeNull();
    // Underscores inside a URL fragment.
    expect(
      detectInlineShortcut("https://en.wikipedia.org/wiki/Foo_bar_"),
    ).toBeNull();
    // Punctuation is not a boundary — keep it predictable.
    expect(detectInlineShortcut("(**x**")).toBeNull();
  });

  it("leaves nested, adjacent, padded and escaped delimiters literal", () => {
    expect(detectInlineShortcut("***text***")).toBeNull();
    expect(detectInlineShortcut("**_x_**")).toBeNull();
    expect(detectInlineShortcut("____")).toBeNull();
    expect(detectInlineShortcut("****")).toBeNull();
    expect(detectInlineShortcut("* *")).toBeNull();
    expect(detectInlineShortcut("** **")).toBeNull();
    expect(detectInlineShortcut("**x **")).toBeNull();
    expect(detectInlineShortcut("a ** b **")).toBeNull();
    expect(detectInlineShortcut("~~~")).toBeNull();
    expect(detectInlineShortcut("\\*x\\*")).toBeNull();
    expect(detectInlineShortcut("\\*x*")).toBeNull();
    expect(detectInlineShortcut("nothing here")).toBeNull();
  });

  it("validates link URLs and leaves unsafe or malformed ones as text", () => {
    expect(detectInlineShortcut("[Journiv](https://journiv.com)")).toEqual({
      kind: "inline",
      format: "link",
      start: 0,
      end: 30,
      text: "Journiv",
      link: "https://journiv.com",
    });
    expect(detectInlineShortcut("[mail](mailto:a@b.com)")).toMatchObject({
      link: "mailto:a@b.com",
    });
    expect(detectInlineShortcut("[u](https://x.com/a_b_c)")).toMatchObject({
      link: "https://x.com/a_b_c",
    });
    expect(detectInlineShortcut("[x](javascript:void)")).toBeNull();
    expect(detectInlineShortcut("[x](ftp://x.com)")).toBeNull();
    expect(detectInlineShortcut("[x](/relative/path)")).toBeNull();
    expect(detectInlineShortcut("[x]()")).toBeNull();
    expect(detectInlineShortcut("[](https://x.com)")).toBeNull();
    expect(detectInlineShortcut("[x](  )")).toBeNull();
    expect(detectInlineShortcut("[x](https://x.com")).toBeNull();
    expect(detectInlineShortcut("\\[x](https://x.com)")).toBeNull();
  });
});

describe("typedInsertion", () => {
  it("recognises a single typed character and its index", () => {
    expect(typedInsertion({ ops: [{ insert: " " }] })).toEqual({
      char: " ",
      index: 0,
    });
    expect(typedInsertion({ ops: [{ retain: 12 }, { insert: "*" }] })).toEqual({
      char: "*",
      index: 12,
    });
  });

  it("ignores pastes, IME multi-char commits, deletions, embeds and formatting", () => {
    expect(typedInsertion({ ops: [{ insert: "hello" }] })).toBeNull();
    expect(typedInsertion({ ops: [{ insert: "日本" }] })).toBeNull();
    expect(typedInsertion({ ops: [{ delete: 1 }] })).toBeNull();
    expect(
      typedInsertion({ ops: [{ retain: 1 }, { insert: "x" }, { delete: 2 }] }),
    ).toBeNull();
    expect(typedInsertion({ ops: [{ insert: { image: "/x" } }] })).toBeNull();
    expect(
      typedInsertion({ ops: [{ retain: 3, attributes: { bold: true } }] }),
    ).toBeNull();
    expect(typedInsertion({ ops: [] })).toBeNull();
  });
});

describe("format allowlist", () => {
  it("only ever produces Gate-1 attributes", () => {
    for (const format of MARKDOWN_SHORTCUT_FORMATS) {
      expect(JOURNIV_DELTA_FORMATS).toContain(format);
    }
  });
});
