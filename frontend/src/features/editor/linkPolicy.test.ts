import { describe, expect, it } from "vitest";
import { validateLinkUrl } from "./linkPolicy";

describe("link policy", () => {
  it.each([
    "https://journiv.com/docs",
    "http://localhost:8000/path",
    "mailto:hello@example.com",
  ])("accepts %s", (value) => {
    expect(validateLinkUrl(`  ${value}  `)).toBe(value);
  });

  it.each([
    "",
    "journiv.com",
    "javascript:alert(1)",
    "data:text/html,bad",
    "file:///tmp/private",
    "mailto:",
  ])("rejects %s", (value) => {
    expect(validateLinkUrl(value)).toBeNull();
  });
});
