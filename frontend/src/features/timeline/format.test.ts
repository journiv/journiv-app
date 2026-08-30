import { describe, expect, it } from "vitest";
import { excerpt, formatMomentDateTime } from "./format";

describe("timeline presentation helpers", () => {
  it("formats in the supplied timezone", () =>
    expect(
      formatMomentDateTime("2026-01-01T00:00:00Z", "Europe/Vienna", "en-GB"),
    ).toContain("2026"));
  it("uses a stable, bounded excerpt", () =>
    expect(excerpt("x".repeat(141))).toHaveLength(138));
});
