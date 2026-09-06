import { describe, expect, it } from "vitest";
import { mediaPath } from "./mediaUrl";

describe("mediaPath", () => {
  it("normalizes absolute and relative media URLs to their stable pathname", () => {
    expect(mediaPath("/api/v1/media/a/signed?sig=old")).toBe(
      "/api/v1/media/a/signed",
    );
    expect(
      mediaPath("https://journiv.example/api/v1/media/a/signed?sig=new"),
    ).toBe("/api/v1/media/a/signed");
  });
});
