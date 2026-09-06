import { act, createRef } from "react";
import { render, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Quill from "quill";
import { describe, expect, it, vi } from "vitest";
import type { QuillDelta, QuillOp } from "../../api/generated/types.gen";
import { isQuillDocumentDelta } from "./deltaProfile";
import { QuillSurface, type QuillSurfaceHandle } from "./QuillSurface";

/**
 * `userEvent.type` reads `{` and `[` as the start of special key syntax;
 * doubling them types the literal character. `*`, `_`, `~`, `>`, `]` and `)`
 * are already literal.
 */
function literal(text: string) {
  return text.replace(/\[/g, "[[").replace(/\{/g, "{{");
}

function mountEditor(initial = "\n") {
  const ref = createRef<QuillSurfaceHandle>();
  const onStateChange = vi.fn();
  const view = render(
    <QuillSurface
      ref={ref}
      editorId="markdown"
      initialContent={{ ops: [{ insert: initial }] }}
      onStateChange={onStateChange}
    />,
  );
  const editor = within(view.container).getByLabelText("Entry body");
  const quill = Quill.find(editor.closest(".jv-prose") as Element) as Quill;
  const ops = (): QuillOp[] => {
    const contents = ref.current?.getContents() as QuillDelta | undefined;
    return contents?.ops ?? [];
  };
  return { ref, quill, editor, onStateChange, ops };
}

const attributedOp = (ops: QuillOp[], attr: string) =>
  ops.find((op) => op.attributes?.[attr] != null);

/** First op's text with any trailing newlines trimmed — jsdom's `userEvent`
 *  leaves an extra empty paragraph that the product does not. */
const firstText = (ops: QuillOp[]) => {
  const value = ops[0]?.insert;
  return (typeof value === "string" ? value : "").replace(/\n+$/, "");
};

describe("markdown shortcuts in the writing surface", () => {
  it("rewrites a heading marker and keeps a saveable Delta", async () => {
    const { ref, editor, ops } = mountEditor();
    await userEvent.type(editor, "## Morning");

    expect(ops()).toContainEqual({ insert: "\n", attributes: { header: 2 } });
    expect(ops()[0]).toEqual({ insert: "Morning" });
    expect(isQuillDocumentDelta(ref.current?.getContents())).toBe(true);
    expect(editor.querySelector("h2")?.textContent).toBe("Morning");
  });

  it("maps headings 1-3 and the quote marker", async () => {
    for (const [typed, selector] of [
      ["# h", "h1"],
      ["## h", "h2"],
      ["### h", "h3"],
      ["> q", "blockquote"],
    ] as const) {
      const { editor } = mountEditor();
      await userEvent.type(editor, typed);
      expect(editor.querySelector(selector), typed).not.toBeNull();
    }
  });

  it("leaves four hashes, indented and mid-line markers literal", async () => {
    const four = mountEditor();
    await userEvent.type(four.editor, "#### h");
    expect(four.editor.querySelector("h4,h5,h6")).toBeNull();
    expect(firstText(four.ops())).toBe("#### h");

    const prose = mountEditor();
    await userEvent.type(prose.editor, "a > b then more");
    expect(prose.editor.querySelector("blockquote")).toBeNull();
    expect(firstText(prose.ops())).toBe("a > b then more");
  });

  it("restores the literal markdown with a single undo", async () => {
    const { ref, quill, editor } = mountEditor();
    await userEvent.type(editor, "## ");
    expect(quill.getFormat(0).header).toBe(2);

    act(() => ref.current?.undo());
    expect(quill.getText(0, 3)).toBe("## ");
    expect(quill.getFormat(0).header).toBeUndefined();
  });

  it("keeps toolbar state in sync after a heading rewrite", async () => {
    const { editor, onStateChange } = mountEditor();
    await userEvent.type(editor, "## ");
    expect(onStateChange).toHaveBeenLastCalledWith(
      expect.objectContaining({
        formats: expect.objectContaining({ header: 2 }),
      }),
    );
  });

  it("does not re-format a line that already has a block format", async () => {
    const { editor, quill } = mountEditor();
    await userEvent.type(editor, "> quote");
    expect(editor.querySelector("blockquote")).not.toBeNull();

    // "# " typed at the head of the existing quote line (driven directly so the
    // caret lands there — userEvent would type at the document end).
    act(() => {
      quill.insertText(0, "#", "user");
      quill.insertText(1, " ", "user");
    });
    expect(editor.querySelector("h1")).toBeNull();
    expect(editor.querySelector("blockquote")).not.toBeNull();
    expect(quill.getText(0, 2)).toBe("# ");
  });

  describe("inline runs", () => {
    it("rewrites bold and ends the run so later text is unformatted", async () => {
      const { editor, ops } = mountEditor();
      await userEvent.type(editor, "see **bold** ok");

      expect(attributedOp(ops(), "bold")?.insert).toBe("bold");
      expect(
        ops().some(
          (op) =>
            typeof op.insert === "string" &&
            op.insert.includes("ok") &&
            op.attributes?.bold == null,
        ),
      ).toBe(true);
    });

    it("restores an inline run with a single undo", async () => {
      const { ref, quill, editor, ops } = mountEditor();
      await userEvent.type(editor, "a ~~x~~");
      expect(ops()).toContainEqual({
        insert: "x",
        attributes: { strike: true },
      });
      act(() => ref.current?.undo());
      expect(quill.getText().trim()).toBe("a ~~x~~");
    });

    it("only fires at a whitespace or start-of-line boundary", async () => {
      const intra = mountEditor();
      await userEvent.type(intra.editor, "rename snake_case_name and 2*3*4");
      expect(intra.ops().every((op) => op.attributes == null)).toBe(true);
      expect(firstText(intra.ops())).toBe("rename snake_case_name and 2*3*4");
    });

    it("leaves nested and adjacent delimiters completely literal", async () => {
      const nested = mountEditor();
      await userEvent.type(nested.editor, "***whoa***");
      expect(nested.ops().every((op) => op.attributes == null)).toBe(true);
      expect(firstText(nested.ops())).toBe("***whoa***");
    });

    it("validates link URLs, leaving unsafe or malformed ones as text", async () => {
      const safe = mountEditor();
      await userEvent.type(safe.editor, literal("[Docs](https://journiv.com)"));
      expect(safe.ops()).toContainEqual({
        insert: "Docs",
        attributes: { link: "https://journiv.com" },
      });

      const unsafe = mountEditor();
      await userEvent.type(unsafe.editor, literal("[x](javascript:void)"));
      expect(attributedOp(unsafe.ops(), "link")).toBeUndefined();
      expect(firstText(unsafe.ops())).toBe("[x](javascript:void)");
    });

    it("does not fire while an IME composition is active", async () => {
      const { editor, ops } = mountEditor();
      act(() => {
        editor.dispatchEvent(
          new CompositionEvent("compositionstart", { bubbles: true }),
        );
      });
      await userEvent.type(editor, "see **bold**");
      expect(attributedOp(ops(), "bold")).toBeUndefined();
      act(() => {
        editor.dispatchEvent(
          new CompositionEvent("compositionend", { bubbles: true }),
        );
      });
    });
  });

  describe("list markers are Quill's, narrowed to what Journiv stores", () => {
    it("makes `- `, `* ` and `1. ` lists that round-trip", async () => {
      for (const [typed, list] of [
        ["- one", "bullet"],
        ["* one", "bullet"],
        ["1. one", "ordered"],
      ] as const) {
        const { ref, editor } = mountEditor();
        await userEvent.type(editor, typed);
        expect(
          editor.querySelector(`li[data-list="${list}"]`),
          typed,
        ).not.toBeNull();
        expect(isQuillDocumentDelta(ref.current?.getContents()), typed).toBe(
          true,
        );
      }
    });

    it("leaves `2. `, `10. ` and checkbox markers as literal text", async () => {
      for (const marker of [
        "2. two",
        "10. ten",
        literal("[ ] task"),
        literal("[x] done"),
      ]) {
        const { ref, editor } = mountEditor();
        await userEvent.type(editor, marker);
        expect(editor.querySelector("li"), marker).toBeNull();
        // The document is still saveable — no out-of-Gate-1 list value.
        expect(isQuillDocumentDelta(ref.current?.getContents()), marker).toBe(
          true,
        );
      }
    });

    it("a single undo of a bare `- ` restores the literal marker", async () => {
      const { ref, quill, editor } = mountEditor();
      await userEvent.type(editor, "- ");
      expect(editor.querySelector('li[data-list="bullet"]')).not.toBeNull();
      // Quill's list-autofill brackets the transform with history.cutoff() on
      // both sides, like markdownShortcuts.ts does for headings, so one undo
      // reverts exactly the transform.
      act(() => ref.current?.undo());
      expect(editor.querySelector("li")).toBeNull();
      expect(quill.getText().replace(/\n+$/, "")).toBe("- ");
    });
  });

  it("survives a save and reload round-trip", async () => {
    const { ref, editor } = mountEditor();
    await userEvent.type(editor, "# Title{enter}");
    await userEvent.type(
      editor,
      literal("with **weight** and a [link](https://journiv.com){enter}- one"),
    );
    const saved = ref.current?.getContents();
    expect(isQuillDocumentDelta(saved)).toBe(true);
    expect(saved?.ops).toContainEqual({
      insert: "\n",
      attributes: { header: 1 },
    });
    expect(saved?.ops).toContainEqual({
      insert: "weight",
      attributes: { bold: true },
    });

    const reloaded = createRef<QuillSurfaceHandle>();
    render(
      <QuillSurface
        ref={reloaded}
        editorId="markdown-reload"
        initialContent={saved as QuillDelta}
      />,
    );
    expect(reloaded.current?.getContents()).toEqual(saved);
  });

  it("never rewrites in a read-only surface", () => {
    const ref = createRef<QuillSurfaceHandle>();
    render(
      <QuillSurface
        ref={ref}
        editorId="ro"
        initialContent={{ ops: [{ insert: "## not a heading\n" }] }}
        readOnly
      />,
    );
    const contents = ref.current?.getContents() as QuillDelta | undefined;
    expect(contents?.ops?.[0]).toEqual({ insert: "## not a heading\n" });
  });
});
