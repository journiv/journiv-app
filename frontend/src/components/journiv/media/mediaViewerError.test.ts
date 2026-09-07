import { describe, expect, it } from "vitest";
import { resolveFailedMediaUrl } from "./mediaViewerError";

const SIGNED = "https://host.test/api/v1/media/x/signed?sig=1";

describe("resolveFailedMediaUrl", () => {
  it("reads a failed <img>", () => {
    const img = document.createElement("img");
    img.src = SIGNED;
    expect(resolveFailedMediaUrl(img)).toBe(SIGNED);
  });

  it("reads a failed <source> (Video plugin child; error does not bubble)", () => {
    const source = document.createElement("source");
    source.src = SIGNED;
    expect(resolveFailedMediaUrl(source)).toBe(SIGNED);
  });

  it("reads a failed <video> via its first <source> when currentSrc is empty", () => {
    const video = document.createElement("video");
    const source = document.createElement("source");
    source.src = SIGNED;
    video.append(source);
    expect(resolveFailedMediaUrl(video)).toBe(SIGNED);
  });

  it("ignores unrelated targets", () => {
    expect(resolveFailedMediaUrl(document.createElement("div"))).toBe("");
    expect(resolveFailedMediaUrl(null)).toBe("");
  });
});
