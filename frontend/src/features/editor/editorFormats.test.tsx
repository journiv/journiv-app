import { render } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it } from "vitest";
import { acceptAttribute, EDITOR_FORMATS } from "./EntryEditorPage";
import { INLINE_MEDIA_KINDS, isEditableDocumentDelta } from "./deltaProfile";
import { QuillSurface, type QuillSurfaceHandle } from "./QuillSurface";

/**
 * Regression guard for a crash found only in the browser:
 * "[Parchment] Unable to create video blot".
 *
 * The editor's document guard and its Quill format allowlist are two separate
 * lists. When the guard admitted `video` but the allowlist did not, opening a
 * real entry threw and the whole editor route died. Unit tests passed happily,
 * because nothing mounted Quill with a video document.
 */
describe("editor format allowlist", () => {
  it("admits every media kind the document guard admits", () => {
    for (const kind of INLINE_MEDIA_KINDS) {
      expect(EDITOR_FORMATS, kind).toContain(kind);
    }
  });

  it.each([...INLINE_MEDIA_KINDS])(
    "mounts a document containing inline %s without throwing",
    (kind) => {
      const signed = `/api/v1/media/media-1/signed?sig=a`;
      const document = {
        ops: [
          { insert: "before\n" },
          // `attributes: null` is what the API actually serialises on embed
          // ops. An earlier guard rejected any op carrying the key at all,
          // which sent real entries to the plain-text fallback.
          { insert: { [kind]: signed }, attributes: null },
          { insert: "after\n" },
        ],
      } as never;

      expect(isEditableDocumentDelta(document), `${kind} guard`).toBe(true);

      const ref = createRef<QuillSurfaceHandle>();
      const view = render(
        <QuillSurface
          ref={ref}
          editorId={`formats-${kind}`}
          initialContent={document}
          formats={EDITOR_FORMATS}
        />,
      );
      const editor = view.container.querySelector(".ql-editor");
      expect(
        editor?.querySelector(kind === "image" ? "img" : kind),
        kind,
      ).not.toBeNull();
      // Quill's built-in video blot renders an iframe; Journiv's must not.
      expect(editor?.querySelector("iframe")).toBeNull();
      view.unmount();
    },
  );
});

describe("media picker filter", () => {
  it("offers every kind the backend accepts, not just images", () => {
    const accept = acceptAttribute({
      images: [".jpg"],
      videos: [".mp4", ".mov"],
      audio: [".m4a"],
    });
    // The original bug: video files could not be selected at all.
    expect(accept).toContain(".mp4");
    expect(accept).toContain(".mov");
    expect(accept).toContain(".m4a");
    expect(accept).not.toContain("image/*");
    expect(accept).not.toContain("video/*");
    expect(accept).not.toContain("audio/*");
  });

  it("stays open to everything while the format list is unavailable", () => {
    // A picker that filters everything out is worse than a permissive one; the
    // backend rejects unsupported types with a human message anyway.
    expect(acceptAttribute(undefined)).toBe("image/*,video/*,audio/*");
    expect(acceptAttribute({ nonsense: true })).toBe("image/*,video/*,audio/*");
  });
});
