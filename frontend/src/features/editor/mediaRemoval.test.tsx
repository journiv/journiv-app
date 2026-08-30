import Quill from "quill";
import { act, render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { EditorToolbar } from "./EditorToolbar";
import { EDITOR_FORMATS } from "./EntryEditorPage";
import { INLINE_MEDIA_KINDS } from "./deltaProfile";
import {
  type EditorState,
  QuillSurface,
  type QuillSurfaceHandle,
} from "./QuillSurface";

const SIGNED = "/api/v1/media/media-1/signed?sig=a";

function mountWithMedia(kind: string) {
  const ref = createRef<QuillSurfaceHandle>();
  const view = render(
    <QuillSurface
      ref={ref}
      editorId={`removal-${kind}`}
      initialContent={
        {
          ops: [
            { insert: "before\n" },
            { insert: { [kind]: SIGNED } },
            { insert: "after\n" },
          ],
        } as never
      }
      formats={EDITOR_FORMATS}
    />,
  );
  const host = view.container.querySelector(".jv-prose") as HTMLElement;
  const quill = Quill.find(host) as Quill;
  /** Places the caret on the embed, as clicking it would. */
  const selectMedia = () => act(() => quill.setSelection(7, 1, "user"));
  return { ref, view, quill, selectMedia };
}

describe("removing inline media from the writing", () => {
  it.each([...INLINE_MEDIA_KINDS])(
    "removes a selected %s and keeps the text",
    (kind) => {
      const { ref, view, selectMedia } = mountWithMedia(kind);
      const editor = view.container.querySelector(".ql-editor");
      expect(
        editor?.querySelector(kind === "image" ? "img" : kind),
      ).not.toBeNull();

      selectMedia();
      expect(ref.current?.getSelectedMedia()?.kind).toBe(kind);
      expect(ref.current?.removeSelectedMedia()).toBe(true);

      expect(editor?.querySelector(kind === "image" ? "img" : kind)).toBeNull();
      const serialized = JSON.stringify(ref.current?.getContents());
      expect(serialized).toContain("before");
      expect(serialized).toContain("after");
      expect(serialized).not.toContain(SIGNED);
      view.unmount();
    },
  );

  it("reports nothing to remove when the caret is not on media", () => {
    const ref = createRef<QuillSurfaceHandle>();
    render(
      <QuillSurface
        ref={ref}
        editorId="no-media"
        initialContent={{ ops: [{ insert: "just text\n" }] } as never}
        formats={EDITOR_FORMATS}
      />,
    );
    expect(ref.current?.getSelectedMedia()).toBeNull();
    expect(ref.current?.removeSelectedMedia()).toBe(false);
  });

  it("can be undone before the entry is saved", () => {
    const { ref, selectMedia } = mountWithMedia("image");
    selectMedia();
    ref.current?.removeSelectedMedia();
    expect(JSON.stringify(ref.current?.getContents())).not.toContain(SIGNED);

    ref.current?.undo();
    // Until Done, nothing has been deleted server-side, so undo is safe.
    expect(JSON.stringify(ref.current?.getContents())).toContain(SIGNED);
  });

  it("cannot be undone after a save, because the file is already gone", () => {
    const { ref, selectMedia } = mountWithMedia("image");
    selectMedia();
    ref.current?.removeSelectedMedia();

    // What the editor does on a successful save. The backend deletes media the
    // save dropped from the document, so restoring the reference would point at
    // a file that no longer exists.
    ref.current?.clearHistory();

    ref.current?.undo();
    expect(JSON.stringify(ref.current?.getContents())).not.toContain(SIGNED);
  });
});

describe("contextual media controls", () => {
  const baseState = (
    selectedMedia: EditorState["selectedMedia"],
  ): EditorState => ({
    formats: {},
    focused: true,
    selectionLength: 1,
    wordCount: 3,
    selectedMedia,
  });

  it("offers no remove control until media is selected", () => {
    const view = render(
      <EditorToolbar
        editor={null}
        state={baseState(null)}
        onAddMedia={vi.fn()}
        onRemoveMedia={vi.fn()}
      />,
    );
    expect(view.queryByLabelText(/^Remove/)).toBeNull();
  });

  it.each([
    ["image", "Remove photo"],
    ["video", "Remove video"],
    ["audio", "Remove audio"],
  ])("names the %s control for what it removes", async (kind, label) => {
    const onRemoveMedia = vi.fn();
    const view = render(
      <EditorToolbar
        editor={null}
        state={baseState(kind as EditorState["selectedMedia"])}
        onAddMedia={vi.fn()}
        onRemoveMedia={onRemoveMedia}
      />,
    );
    // Never a bare "Delete": the label says what is going away.
    const button = view.getByLabelText(label);
    await userEvent.click(button);
    expect(onRemoveMedia).toHaveBeenCalled();
  });
});

describe("undo history scope", () => {
  it("cannot undo past the document that was loaded", () => {
    // Quill records `silent` and `api` changes in history by default, which
    // made Ctrl+Z able to revert the initial load and leave the entry empty —
    // a document the writer could then save over their own words.
    const ref = createRef<QuillSurfaceHandle>();
    render(
      <QuillSurface
        ref={ref}
        editorId="history-scope"
        initialContent={{ ops: [{ insert: "existing writing\n" }] } as never}
        formats={EDITOR_FORMATS}
      />,
    );

    ref.current?.undo();
    ref.current?.undo();
    ref.current?.undo();

    expect(JSON.stringify(ref.current?.getContents())).toContain(
      "existing writing",
    );
  });
});
