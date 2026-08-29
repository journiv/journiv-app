import { act, createRef } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Quill from "quill";
import { describe, expect, it, vi } from "vitest";
import { deltasEqual, EMPTY_DELTA } from "./deltaProfile";
import { CANONICAL_DELTA_FIXTURES } from "./fixtures";
import { JOURNIV_DELTA_FORMATS } from "./deltaProfile";
import { QuillSurface, type QuillSurfaceHandle } from "./QuillSurface";

describe("QuillSurface", () => {
  it("hydrates silently, reports words, and keeps one editor across state changes", async () => {
    const changed = vi.fn();
    const stateChanged = vi.fn();
    const view = render(
      <QuillSurface
        editorId="entry-1"
        initialContent={EMPTY_DELTA}
        onUserChange={changed}
        onStateChange={stateChanged}
      />,
    );
    const editor = screen.getByLabelText("Entry body");
    expect(editor.getAttribute("role")).toBe("textbox");
    expect(editor.getAttribute("aria-multiline")).toBe("true");
    expect(changed).not.toHaveBeenCalled();
    expect(stateChanged).toHaveBeenLastCalledWith(
      expect.objectContaining({ wordCount: 0 }),
    );

    await userEvent.type(editor, "Hello world");
    expect(changed).toHaveBeenCalled();
    expect(stateChanged).toHaveBeenLastCalledWith(
      expect.objectContaining({ wordCount: 2 }),
    );

    view.rerender(
      <QuillSurface
        editorId="entry-1"
        initialContent={EMPTY_DELTA}
        onUserChange={changed}
        onStateChange={stateChanged}
        readOnly
      />,
    );
    expect(screen.getByLabelText("Entry content")).toBe(editor);
    expect(editor.getAttribute("contenteditable")).toBe("false");
    expect(editor.getAttribute("role")).toBeNull();
    expect(editor.getAttribute("aria-multiline")).toBeNull();
    expect(editor.getAttribute("aria-readonly")).toBe("true");
    expect(editor.closest(".jv-prose")?.className).toContain(
      "jv-prose--reader",
    );
  });

  it("loads and serializes every canonical fixture without semantic loss", () => {
    for (const [name, fixture] of CANONICAL_DELTA_FIXTURES) {
      const ref = createRef<QuillSurfaceHandle>();
      const view = render(
        <QuillSurface
          ref={ref}
          editorId={`fixture-${name}`}
          initialContent={fixture}
        />,
      );
      expect(
        deltasEqual(ref.current?.getContents() ?? EMPTY_DELTA, fixture),
        name,
      ).toBe(true);
      view.unmount();
    }
  });

  it("hydrates the current content when its entry or placeholder changes", () => {
    const ref = createRef<QuillSurfaceHandle>();
    const view = render(
      <QuillSurface
        ref={ref}
        editorId="entry-1"
        initialContent={{ ops: [{ insert: "First entry\n" }] }}
        placeholder="Write about this moment…"
      />,
    );

    view.rerender(
      <QuillSurface
        ref={ref}
        editorId="entry-2"
        initialContent={{ ops: [{ insert: "Second entry\n" }] }}
        placeholder="Write about this moment…"
      />,
    );
    expect(ref.current?.getContents()).toEqual({
      ops: [{ insert: "Second entry\n" }],
    });

    view.rerender(
      <QuillSurface
        ref={ref}
        editorId="entry-2"
        initialContent={{ ops: [{ insert: "Replacement draft\n" }] }}
        placeholder="Continue writing…"
      />,
    );
    expect(ref.current?.getContents()).toEqual({
      ops: [{ insert: "Replacement draft\n" }],
    });
  });

  it("round-trips inline media without gaining newlines, unlike flutter_quill", () => {
    // flutter_quill grows a newline after every video embed on each load; see
    // DESIGN.md §21. Quill JS must not, or the web client would corrupt
    // documents on its own.
    const signed = "/api/v1/media/media-1/signed?sig=a";
    const source = {
      ops: [
        { insert: "before\n" },
        { insert: { video: signed } },
        { insert: "after\n" },
      ],
    } as never;

    let current = source;
    for (let pass = 0; pass < 3; pass += 1) {
      const ref = createRef<QuillSurfaceHandle>();
      const view = render(
        <QuillSurface
          ref={ref}
          editorId={`media-round-trip-${pass}`}
          initialContent={current}
          formats={[...JOURNIV_DELTA_FORMATS, "image", "video", "audio"]}
        />,
      );
      const next = ref.current?.getContents() as never;
      expect(JSON.stringify(next), `pass ${pass}`).toBe(JSON.stringify(source));
      current = next;
      view.unmount();
    }
  });

  it("formats ranged inline and line selections through the imperative adapter", () => {
    const ref = createRef<QuillSurfaceHandle>();
    const stateChanged = vi.fn();
    render(
      <QuillSurface
        ref={ref}
        editorId="formatting"
        initialContent={{
          ops: [{ insert: "First line\nSecond line\nThird line\n" }],
        }}
        onStateChange={stateChanged}
      />,
    );
    const editor = screen.getByLabelText("Entry body");
    const quill = Quill.find(editor.closest(".jv-prose") as Element) as Quill;

    act(() => quill.setSelection(0, 5, "user"));
    act(() => ref.current?.toggleInline("bold"));
    expect(ref.current?.getContents().ops?.[0]).toEqual({
      insert: "First",
      attributes: { bold: true },
    });

    act(() => quill.setSelection(11, 1, "user"));
    act(() => ref.current?.toggleLine("header", 2));
    expect(ref.current?.getContents().ops).toContainEqual({
      insert: "\n",
      attributes: { header: 2 },
    });
    expect(editor.querySelector("h2")?.textContent).toBe("Second line");

    act(() => quill.setSelection(0, 1, "user"));
    act(() => ref.current?.toggleLine("blockquote", true));
    expect(editor.querySelector("blockquote")?.textContent).toBe("First line");

    act(() => quill.setSelection(23, 1, "user"));
    act(() => ref.current?.toggleLine("list", "bullet"));
    expect(editor.querySelector('li[data-list="bullet"]')?.textContent).toBe(
      "Third line",
    );

    act(() => quill.setSelection(0, 0, "user"));
    act(() => ref.current?.toggleInline("italic"));
    expect(stateChanged).toHaveBeenLastCalledWith(
      expect.objectContaining({
        formats: expect.objectContaining({ italic: true }),
      }),
    );
  });

  it("adds, edits, and removes a link without losing the selected text", () => {
    const ref = createRef<QuillSurfaceHandle>();
    render(
      <QuillSurface
        ref={ref}
        editorId="links"
        initialContent={{ ops: [{ insert: "Journiv docs\n" }] }}
      />,
    );
    const editor = screen.getByLabelText("Entry body");
    const quill = Quill.find(editor.closest(".jv-prose") as Element) as Quill;

    act(() => quill.setSelection(0, 7, "user"));
    expect(ref.current?.getLinkContext()).toEqual({
      href: "",
      selectedText: "Journiv",
      canApply: true,
    });
    act(() => ref.current?.setLink("https://journiv.com"));
    expect(ref.current?.getContents().ops?.[0]).toEqual({
      insert: "Journiv",
      attributes: { link: "https://journiv.com" },
    });
    act(() => ref.current?.setLink("mailto:hello@example.com"));
    expect(ref.current?.getContents().ops?.[0]).toEqual({
      insert: "Journiv",
      attributes: { link: "mailto:hello@example.com" },
    });
    act(() => quill.setSelection(3, 0, "user"));
    expect(ref.current?.getLinkContext()).toEqual({
      href: "mailto:hello@example.com",
      selectedText: "Journiv",
      canApply: true,
    });
    act(() => ref.current?.setLink(false));
    expect(ref.current?.getContents()).toEqual({
      ops: [{ insert: "Journiv docs\n" }],
    });
  });

  it("supports undo/redo and suppresses commands during composition", () => {
    const ref = createRef<QuillSurfaceHandle>();
    render(
      <QuillSurface
        ref={ref}
        editorId="history"
        initialContent={{ ops: [{ insert: "Base\n" }] }}
      />,
    );
    const editor = screen.getByLabelText("Entry body");
    const quill = Quill.find(editor.closest(".jv-prose") as Element) as Quill;
    quill.history.clear();
    act(() => quill.insertText(0, "Added ", "user"));
    act(() => ref.current?.undo());
    expect(quill.getText()).toBe("Base\n");
    act(() => ref.current?.redo());
    expect(quill.getText()).toBe("Added Base\n");

    act(() => quill.setSelection(0, 5, "user"));
    editor.dispatchEvent(
      new CompositionEvent("compositionstart", { bubbles: true }),
    );
    expect(ref.current?.isComposing()).toBe(true);
    act(() => ref.current?.toggleInline("italic"));
    expect(
      ref.current?.getContents().ops?.[0]?.attributes?.italic,
    ).toBeUndefined();
    editor.dispatchEvent(
      new CompositionEvent("compositionend", { bubbles: true }),
    );
    expect(ref.current?.isComposing()).toBe(false);
  });

  it("keeps allowed paste formats and drops unsupported proliferation", () => {
    const ref = createRef<QuillSurfaceHandle>();
    render(
      <QuillSurface ref={ref} editorId="paste" initialContent={EMPTY_DELTA} />,
    );
    const editor = screen.getByLabelText("Entry body");
    const quill = Quill.find(editor.closest(".jv-prose") as Element) as Quill;
    act(() => {
      quill.clipboard.dangerouslyPasteHTML(
        0,
        '<p style="color:red"><strong>Bold</strong> <code>code</code></p>',
        "user",
      );
    });

    const contents = ref.current?.getContents();
    expect(contents?.ops).toContainEqual({
      insert: "Bold",
      attributes: { bold: true },
    });
    const attributeNames =
      contents?.ops?.flatMap((operation) =>
        Object.keys(operation.attributes ?? {}),
      ) ?? [];
    expect(attributeNames).not.toContain("color");
    expect(attributeNames).not.toContain("code");
  });

  it("unregisters Quill listeners when unmounted", () => {
    const off = vi.spyOn(Quill.prototype, "off");
    const view = render(
      <QuillSurface editorId="cleanup" initialContent={EMPTY_DELTA} />,
    );
    view.unmount();
    expect(off).toHaveBeenCalledWith("text-change", expect.any(Function));
    expect(off).toHaveBeenCalledWith("selection-change", expect.any(Function));
    off.mockRestore();
  });
});
