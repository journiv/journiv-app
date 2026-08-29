import { afterEach, describe, expect, it, vi } from "vitest";
import { uuid } from "./uuid";

const V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

afterEach(() => vi.unstubAllGlobals());

describe("uuid", () => {
  it("works when crypto.randomUUID exists", () => {
    expect(uuid()).toMatch(V4);
  });

  it("works without a secure context, where randomUUID is undefined", () => {
    // A self-hosted Journiv reached over plain HTTP on a LAN is not a secure
    // context, so `crypto.randomUUID` is undefined there. Calling it threw, and
    // attaching a photo did nothing at all.
    vi.stubGlobal("crypto", {
      getRandomValues: globalThis.crypto.getRandomValues.bind(
        globalThis.crypto,
      ),
    });
    expect(typeof globalThis.crypto.randomUUID).toBe("undefined");
    expect(uuid()).toMatch(V4);
  });

  it("still works with no crypto at all", () => {
    vi.stubGlobal("crypto", undefined);
    expect(uuid()).toMatch(V4);
  });

  it("does not repeat itself", () => {
    const seen = new Set(Array.from({ length: 500 }, () => uuid()));
    expect(seen.size).toBe(500);
  });
});
