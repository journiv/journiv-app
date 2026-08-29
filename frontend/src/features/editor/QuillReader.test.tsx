import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CANONICAL_DELTA_FIXTURES } from "./fixtures";
import { planReaderContent, QuillReader } from "./QuillReader";

const SIGNED = "/api/v1/media/media-1/signed?uid=u&exp=1&sig=abc";

describe("QuillReader", () => {
  it("renders every canonical fixture as a non-editable document", () => {
    for (const [name, fixture] of CANONICAL_DELTA_FIXTURES) {
      const view = render(
        <QuillReader content={fixture} entryId={`entry-${name}`} />,
      );
      const editor = screen.getByLabelText("Entry content");
      expect(editor.getAttribute("contenteditable"), name).toBe("false");
      expect(editor.getAttribute("tabindex"), name).toBe("-1");
      expect(editor.getAttribute("role"), name).toBeNull();
      expect(editor.getAttribute("aria-multiline"), name).toBeNull();
      view.unmount();
    }
  });

  it("renders the inline image URL the backend hydrated into the document", () => {
    render(
      <QuillReader
        content={{
          ops: [
            { insert: "Before the photo\n" },
            { insert: { image: SIGNED } },
            { insert: "After the photo\n" },
          ],
        }}
        entryId="inline"
      />,
    );
    const editor = screen.getByLabelText("Entry content");
    expect(editor.querySelector("img")?.getAttribute("src")).toBe(SIGNED);
    expect(editor.textContent).toContain("Before the photo");
    expect(editor.textContent).toContain("After the photo");
  });

  it("reports the inline paths so the gallery can avoid showing a photo twice", () => {
    const plan = planReaderContent({
      ops: [{ insert: { image: SIGNED } }, { insert: "\n" }],
    });
    expect(plan.renderable).toBe(true);
    expect([...plan.inlinePaths]).toEqual(["/api/v1/media/media-1/signed"]);
  });

  it("refuses to fetch an absolute third-party media URL", () => {
    render(
      <QuillReader
        content={{
          ops: [
            { insert: { image: "https://tracker.example.com/pixel.jpg" } },
            { insert: "\n" },
          ],
        }}
        entryId="external"
        plainText="A safe server-derived description"
      />,
    );
    expect(screen.queryByLabelText("Entry content")).toBeNull();
    expect(screen.getByText("A safe server-derived description")).toBeTruthy();
  });

  it("renders inline video as a real video element, never an iframe", () => {
    render(
      <QuillReader
        content={{ ops: [{ insert: { video: SIGNED } }, { insert: "\n" }] }}
        entryId="video"
      />,
    );
    const editor = screen.getByLabelText("Entry content");
    const video = editor.querySelector("video");
    expect(video?.getAttribute("src")).toBe(SIGNED);
    expect(video?.hasAttribute("controls")).toBe(true);
    // No autoplay: a journal must not start making noise when opened.
    expect(video?.hasAttribute("autoplay")).toBe(false);
    expect(editor.querySelector("iframe")).toBeNull();
  });

  it("renders inline audio as a real audio element", () => {
    render(
      <QuillReader
        content={{ ops: [{ insert: { audio: SIGNED } }, { insert: "\n" }] }}
        entryId="audio"
      />,
    );
    const editor = screen.getByLabelText("Entry content");
    expect(editor.querySelector("audio")?.getAttribute("src")).toBe(SIGNED);
  });

  it("falls back for embed kinds Journiv does not render", () => {
    render(
      <QuillReader
        content={{ ops: [{ insert: { formula: "x" } }, { insert: "\n" }] }}
        entryId="formula"
        plainText="Plain text"
      />,
    );
    expect(screen.queryByLabelText("Entry content")).toBeNull();
    expect(screen.getByRole("note").textContent).toContain(
      "cannot be displayed yet",
    );
  });
});
