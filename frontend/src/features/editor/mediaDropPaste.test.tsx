import Quill from "quill";
import { render } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { EDITOR_FORMATS } from "./EntryEditorPage";
import { QuillSurface, type QuillSurfaceHandle } from "./QuillSurface";

const OWN_MEDIA = "/api/v1/media/media-1/signed?sig=a";

function mount(onFiles?: (files: File[], index: number) => void) {
  const ref = createRef<QuillSurfaceHandle>();
  const view = render(
    <QuillSurface
      ref={ref}
      editorId={`drop-${Math.random()}`}
      initialContent={{ ops: [{ insert: "before\nafter\n" }] } as never}
      formats={EDITOR_FORMATS}
      onFiles={onFiles}
    />,
  );
  const host = view.container.querySelector(".jv-prose") as HTMLElement;
  const quill = Quill.find(host) as Quill;
  return { ref, view, quill, root: quill.root };
}

const photo = (name = "photo.jpg") =>
  new File(["bytes"], name, { type: "image/jpeg" });

function fileEvent(
  type: "drop" | "paste",
  files: File[],
  coords = { x: 10, y: 10 },
) {
  const event = new Event(type, {
    bubbles: true,
    cancelable: true,
  }) as Event & {
    dataTransfer?: unknown;
    clipboardData?: unknown;
    clientX?: number;
    clientY?: number;
  };
  // Quill's own handlers read getData, so the fake must look like the real
  // thing or their exceptions mask the behaviour under test.
  const payload = {
    files,
    types: files.length ? ["Files"] : [],
    getData: () => "",
    setData: () => undefined,
    items: [],
  };
  if (type === "drop") {
    event.dataTransfer = payload;
    event.clientX = coords.x;
    event.clientY = coords.y;
  } else {
    event.clipboardData = payload;
  }
  return event;
}

describe("dropping files onto the writing", () => {
  it("hands the files over and prevents the browser navigating away", () => {
    const onFiles = vi.fn();
    const { root } = mount(onFiles);
    const event = fileEvent("drop", [photo()]);
    root.dispatchEvent(event);

    expect(onFiles).toHaveBeenCalledTimes(1);
    expect(onFiles.mock.calls[0][0]).toHaveLength(1);
    expect(typeof onFiles.mock.calls[0][1]).toBe("number");
    // Without preventDefault the browser leaves the page to open the file.
    expect(event.defaultPrevented).toBe(true);
  });

  it("ignores a drop that carries no files", () => {
    const onFiles = vi.fn();
    const { root } = mount(onFiles);
    root.dispatchEvent(fileEvent("drop", []));
    expect(onFiles).not.toHaveBeenCalled();
  });

  it("does nothing when the host does not accept files", () => {
    // A surface with no file handler must not try to attach anything. Quill
    // still handles the event itself, so defaultPrevented is not the signal.
    const { ref, root } = mount(undefined);
    const before = JSON.stringify(ref.current?.getContents());
    root.dispatchEvent(fileEvent("drop", [photo()]));
    expect(JSON.stringify(ref.current?.getContents())).toBe(before);
  });
});

describe("pasting files into the writing", () => {
  it("attaches pasted files at the caret", () => {
    const onFiles = vi.fn();
    const { root } = mount(onFiles);
    const event = fileEvent("paste", [photo("pasted.png")]);
    root.dispatchEvent(event);

    expect(onFiles).toHaveBeenCalledTimes(1);
    expect(onFiles.mock.calls[0][0][0].name).toBe("pasted.png");
    expect(event.defaultPrevented).toBe(true);
  });

  it("leaves an ordinary text paste to Quill", () => {
    const onFiles = vi.fn();
    const { root } = mount(onFiles);
    root.dispatchEvent(fileEvent("paste", []));
    // Only file pastes are intercepted; text and formatting keep working.
    expect(onFiles).not.toHaveBeenCalled();
  });
});

describe("Quill's built-in uploader", () => {
  // NOTE: only the paste path is reproducible here. Quill's drop handler needs
  // `document.caretRangeFromPoint`, which jsdom does not implement, so the drop
  // case was verified in a real browser instead — where it did inject three
  // base64 images before this was disabled.
  it.each(["paste"] as const)(
    "never inlines a %sd file as base64",
    async (type) => {
      // Quill's uploader module reads image files and inserts them as data:
      // URLs. That bypasses Journiv's media pipeline, bloats the document, and
      // persists a payload no backup could map back to a file.
      const onFiles = vi.fn();
      const { ref, root } = mount(onFiles);
      root.dispatchEvent(fileEvent(type, [photo()]));
      // Quill's uploader reads the file asynchronously, so an immediate
      // assertion here would pass even with the bug present.
      await new Promise((resolve) => setTimeout(resolve, 50));

      const serialized = JSON.stringify(ref.current?.getContents());
      expect(serialized).not.toContain("data:image");
      expect(serialized).not.toContain("base64");
      // Journiv's own handler still receives the file.
      expect(onFiles).toHaveBeenCalledTimes(1);
    },
  );
});

describe("paste sanitiser", () => {
  it("refuses to embed an external image URL", () => {
    const { ref, quill } = mount();
    quill.clipboard.dangerouslyPasteHTML(
      0,
      '<p>text <img src="https://tracker.example.com/pixel.png"> more</p>',
    );
    const serialized = JSON.stringify(ref.current?.getContents());
    // Pasting HTML must never turn a journal entry into a beacon for a third
    // party, nor create a reference no backup could restore.
    expect(serialized).not.toContain("tracker.example.com");
    expect(serialized).toContain("text");
    expect(serialized).toContain("more");
  });

  it("keeps Journiv's own media when copied within the editor", () => {
    const { ref, quill } = mount();
    quill.clipboard.dangerouslyPasteHTML(
      0,
      `<p><img src="${window.location.origin}${OWN_MEDIA}"></p>`,
    );
    const serialized = JSON.stringify(ref.current?.getContents());
    // Stored relative, matching what the API hydrates.
    expect(serialized).toContain("/api/v1/media/media-1/signed");
    expect(serialized).not.toContain(window.location.origin);
  });
});
