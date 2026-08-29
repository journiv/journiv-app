import Quill from "quill";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { stripUploadPlaceholders } from "./deltaProfile";
import {
  findPlaceholderIndex,
  placeholderPreview,
  registerPlaceholder,
  releaseAllPlaceholders,
  setPlaceholderState,
  UPLOAD_BLOT_NAME,
} from "./uploadPlaceholder";

function makeEditor() {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const quill = new Quill(host, {
    formats: ["bold", "image", UPLOAD_BLOT_NAME],
    modules: { toolbar: false },
  });
  quill.setContents([{ insert: "before\nafter\n" }] as never, "silent");
  return { quill, host };
}

beforeEach(() => {
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:fake-preview"),
    revokeObjectURL: vi.fn(),
  });
});
afterEach(() => {
  releaseAllPlaceholders();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe("upload placeholder blot", () => {
  it("serializes only the upload id — never a blob URL", () => {
    registerPlaceholder("u1", {
      kind: "image",
      fileName: "photo.jpg",
      objectUrl: "blob:fake-preview",
    });
    const { quill } = makeEditor();
    quill.insertEmbed(6, UPLOAD_BLOT_NAME, { uploadId: "u1" }, "user");

    const serialized = JSON.stringify(quill.getContents().ops);
    expect(serialized).toContain("u1");
    expect(serialized).not.toContain("blob:");
    expect(serialized).not.toContain("photo.jpg");
  });

  it("renders the local preview in the DOM without putting it in the document", () => {
    registerPlaceholder("u1", {
      kind: "image",
      fileName: "photo.jpg",
      objectUrl: "blob:fake-preview",
    });
    const { quill, host } = makeEditor();
    quill.insertEmbed(6, UPLOAD_BLOT_NAME, { uploadId: "u1" }, "user");

    const image = host.querySelector<HTMLImageElement>(".jv-upload__preview");
    expect(image?.getAttribute("src")).toBe("blob:fake-preview");
    expect(host.querySelector(".jv-upload__status")?.textContent).toBe(
      "Uploading photo…",
    );
  });

  it("finds a placeholder by id, and reports -1 once it is gone", () => {
    registerPlaceholder("u1", { kind: "image", fileName: "a.jpg" });
    const { quill } = makeEditor();
    quill.insertEmbed(6, UPLOAD_BLOT_NAME, { uploadId: "u1" }, "user");

    expect(findPlaceholderIndex(quill, "u1")).toBe(6);
    expect(findPlaceholderIndex(quill, "nope")).toBe(-1);

    quill.deleteText(6, 1, "user");
    // This is the race guard: a completing upload must see that it has nowhere
    // to go and must not reinsert the media.
    expect(findPlaceholderIndex(quill, "u1")).toBe(-1);
  });

  it("survives undo and redo, keeping its identity", () => {
    registerPlaceholder("u1", { kind: "image", fileName: "a.jpg" });
    const { quill } = makeEditor();
    quill.insertEmbed(6, UPLOAD_BLOT_NAME, { uploadId: "u1" }, "user");
    expect(findPlaceholderIndex(quill, "u1")).toBe(6);

    quill.history.undo();
    expect(findPlaceholderIndex(quill, "u1")).toBe(-1);

    quill.history.redo();
    expect(findPlaceholderIndex(quill, "u1")).toBe(6);
    expect(placeholderPreview("u1")?.fileName).toBe("a.jpg");
  });

  it("shows real progress only when the browser reported it", () => {
    registerPlaceholder("u1", { kind: "image", fileName: "a.jpg" });
    const { quill, host } = makeEditor();
    quill.insertEmbed(6, UPLOAD_BLOT_NAME, { uploadId: "u1" }, "user");
    const status = () => host.querySelector(".jv-upload__status")?.textContent;

    setPlaceholderState(host, "u1", "uploading", 0.63);
    expect(status()).toBe("Uploading photo… 63%");

    setPlaceholderState(host, "u1", "uploading", undefined);
    expect(status()).toBe("Uploading photo…");

    setPlaceholderState(host, "u1", "processing");
    expect(status()).toBe("Processing…");

    setPlaceholderState(host, "u1", "failed");
    expect(status()).toBe("Couldn’t upload this photo");
    expect(host.querySelector<HTMLElement>(".jv-upload")?.dataset.state).toBe(
      "failed",
    );
  });

  it("uses the right noun for video and audio", () => {
    registerPlaceholder("v1", { kind: "video", fileName: "clip.mp4" });
    const { quill, host } = makeEditor();
    quill.insertEmbed(6, UPLOAD_BLOT_NAME, { uploadId: "v1" }, "user");
    expect(host.querySelector(".jv-upload__status")?.textContent).toBe(
      "Uploading video…",
    );
  });

  it("is stripped out of any Delta that leaves the editor", () => {
    const delta = {
      ops: [
        { insert: "before" },
        { insert: { [UPLOAD_BLOT_NAME]: { uploadId: "u1" } } },
        { insert: "\n" },
      ],
    } as never;
    const stripped = stripUploadPlaceholders(delta);
    expect(JSON.stringify(stripped)).not.toContain(UPLOAD_BLOT_NAME);
    expect(stripped.ops).toHaveLength(2);
  });

  it("revokes every object URL when the session ends", () => {
    registerPlaceholder("u1", {
      kind: "image",
      fileName: "a.jpg",
      objectUrl: "blob:one",
    });
    registerPlaceholder("u2", {
      kind: "image",
      fileName: "b.jpg",
      objectUrl: "blob:two",
    });
    releaseAllPlaceholders();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:one");
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:two");
    expect(placeholderPreview("u1")).toBeUndefined();
  });
});
