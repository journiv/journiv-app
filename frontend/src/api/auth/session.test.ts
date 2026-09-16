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
    });
    expect(sessionStore.read()).toEqual({
      version: 1,
      accessToken: "access",
    });
    sessionStore.clear();
    expect(sessionStore.read()).toBeNull();
  });

  it("removes refresh tokens left by older PWA sessions", () => {
    sessionStorage.setItem(
      "journiv.session.v1",
      JSON.stringify({
        version: 1,
        accessToken: "access",
        refreshToken: "legacy-browser-refresh",
      }),
    );

    expect(sessionStore.read()).toEqual({ version: 1, accessToken: "access" });
    expect(sessionStorage.getItem("journiv.session.v1")).not.toContain(
      "refreshToken",
    );
  });
});
