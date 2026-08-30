import { beforeEach, describe, expect, it } from "vitest";
import { oidcLoginHref, oidcReturnToStore } from "./oidc";
import { safeReturnTo } from "./returnTo";

describe("OIDC navigation state", () => {
  beforeEach(() => sessionStorage.clear());

  it("stores only safe same-origin return paths", () => {
    oidcReturnToStore.write("https://evil.example/steal");
    expect(oidcReturnToStore.read()).toBe("/timeline");

    oidcReturnToStore.write("//evil.example/steal");
    expect(oidcReturnToStore.read()).toBe("/timeline");

    oidcReturnToStore.write("/timeline/moment-1?q=rain");
    expect(oidcReturnToStore.read()).toBe("/timeline/moment-1?q=rain");
  });

  it("fails closed when storage is absent and builds the same-origin login URL", () => {
    expect(oidcReturnToStore.read()).toBe("/timeline");
    expect(safeReturnTo("/\\evil.example/steal")).toBe("/timeline");
    expect(oidcLoginHref()).toBe("/api/v1/auth/oidc/login");
  });
});
