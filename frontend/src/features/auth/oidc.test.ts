import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  oidcLoginHref,
  oidcLogoutHref,
  oidcReturnToStore,
  startOidcLogout,
} from "./oidc";
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

  it("uses the backend SSO endpoint for OIDC logout", () => {
    const navigate = vi.fn();
    startOidcLogout(navigate);
    expect(oidcLogoutHref()).toBe("/api/v1/auth/oidc/logout");
    expect(navigate).toHaveBeenCalledWith("/api/v1/auth/oidc/logout");
  });
});
