import { beforeEach, describe, expect, it } from "vitest";
import { sessionStore } from "./session";

describe("sessionStore", () => {
  beforeEach(() => sessionStorage.clear());
  it("rejects malformed or unsupported sessions", () => {
    sessionStorage.setItem(
      "journiv.session.v1",
      JSON.stringify({ version: 2, accessToken: "a" }),
    );
    expect(sessionStore.read()).toBeNull();
  });
  it("stores and clears only versioned sessions", () => {
    sessionStore.write({
      version: 1,
      accessToken: "access",
      refreshToken: "refresh",
    });
    expect(sessionStore.read()).toEqual({
      version: 1,
      accessToken: "access",
      refreshToken: "refresh",
    });
    sessionStore.clear();
    expect(sessionStore.read()).toBeNull();
  });
});
