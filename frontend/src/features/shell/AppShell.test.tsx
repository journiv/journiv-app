import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { resetSessionForTests, sessionStore } from "../../api/auth/session";
import { ApiError } from "../../api/client/errors";
import { AppShell } from "./AppShell";

const mocks = vi.hoisted(() => ({
  clearQueries: vi.fn(),
  navigate: vi.fn(),
  query: {
    data: undefined,
    error: undefined as unknown,
    isError: false,
    isLoading: false,
  },
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => mocks.query,
  useQueryClient: () => ({ clear: mocks.clearQueries }),
  queryOptions: (options: unknown) => options,
}));

vi.mock("@tanstack/react-router", () => ({
  Outlet: () => null,
  useLocation: () => ({ href: "/timeline" }),
  useMatches: () => [],
  useRouter: () => ({ navigate: mocks.navigate }),
}));

vi.mock("./AppSidebar", () => ({ AppSidebar: () => null }));

describe("AppShell session handling", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    resetSessionForTests();
    sessionStore.adopt({ accessToken: "access", userId: "user-1" });
    mocks.query.error = undefined;
    mocks.query.isError = false;
  });

  it("clears the session when /users/me rejects an inactive account", async () => {
    mocks.query.error = new ApiError("User account is inactive", {
      status: 403,
    });
    mocks.query.isError = true;

    render(<AppShell />);

    await waitFor(() => expect(sessionStore.getAccessToken()).toBeNull());
    expect(mocks.clearQueries).toHaveBeenCalledOnce();
    expect(mocks.navigate).toHaveBeenCalledWith({
      to: "/login",
      search: { returnTo: "/timeline" },
    });
  });
});
