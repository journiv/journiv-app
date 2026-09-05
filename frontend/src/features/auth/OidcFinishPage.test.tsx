import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import { queryKeys } from "../../api/query/keys";
import type { InstanceConfigResponse } from "../../api/generated";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";
import { oidcReturnToStore } from "./oidc";

vi.mock("../../api/client/api", () => ({
  api: {
    instanceConfig: vi.fn(),
    oidcExchange: vi.fn(),
  },
}));

const instanceConfig: InstanceConfigResponse = {
  import_export_max_file_size_mb: 100,
  max_file_size_mb: 50,
  disable_signup: false,
  oidc_enabled: true,
  oidc_only: false,
  plus: {
    available: false,
    tier: "member",
    upgrade_url: "https://journiv.com/plus",
  },
};

async function renderFinish(path: string) {
  const history = createMemoryHistory({ initialEntries: [path] });
  const router = createAppRouter(history);
  const queryClient = createAppQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  const view = render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  );
  await router.load();
  return { ...view, queryClient, router };
}

describe("OidcFinishPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.mocked(api.instanceConfig).mockResolvedValue(instanceConfig);
    vi.mocked(api.oidcExchange).mockResolvedValue({
      access_token: "oidc-access",
      refresh_token: "oidc-refresh",
    } as never);
  });

  it("exchanges a ticket exactly once, stores the session and returns", async () => {
    let completeExchange!: (tokens: {
      access_token: string;
      refresh_token: string;
    }) => void;
    vi.mocked(api.oidcExchange).mockImplementation(
      () =>
        new Promise((resolve) => {
          completeExchange = resolve as typeof completeExchange;
        }) as never,
    );
    oidcReturnToStore.write("/signup");
    const view = await renderFinish("/oidc-finish?ticket=one-time-ticket");
    sessionStore.write({
      version: 1,
      accessToken: "previous-access",
      refreshToken: "previous-refresh",
    });
    view.queryClient.setQueryData(queryKeys.promptAnalytics, {
      prompts_answered: 7,
    });

    expect(
      await screen.findByRole("heading", { name: "Completing sign in" }),
    ).toBeTruthy();
    completeExchange({
      access_token: "oidc-access",
      refresh_token: "oidc-refresh",
    });
    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe("/signup"),
    );
    expect(api.oidcExchange).toHaveBeenCalledTimes(1);
    expect(api.oidcExchange).toHaveBeenCalledWith("one-time-ticket");
    expect(sessionStore.read()).toEqual({
      version: 1,
      accessToken: "oidc-access",
      refreshToken: "oidc-refresh",
    });
    expect(
      view.queryClient.getQueryData(queryKeys.promptAnalytics),
    ).toBeUndefined();
    expect(oidcReturnToStore.read()).toBe("/timeline");
  });

  it("rejects a missing ticket without calling the exchange endpoint", async () => {
    await renderFinish("/oidc-finish");

    expect(
      await screen.findByRole("heading", {
        name: "Sign in wasn’t completed",
      }),
    ).toBeTruthy();
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(api.oidcExchange).not.toHaveBeenCalled();
    expect(sessionStore.read()).toBeNull();
  });

  it("shows a safe recovery state for an expired or reused ticket", async () => {
    vi.mocked(api.oidcExchange).mockRejectedValue(
      new Error("ticket 123 is invalid: sensitive detail"),
    );
    oidcReturnToStore.write("/timeline/moment-1?q=rain");
    await renderFinish("/oidc-finish?ticket=expired-ticket");

    expect(
      await screen.findByText(/link may have expired or already been used/i),
    ).toBeTruthy();
    expect(screen.queryByText(/ticket 123/)).toBeNull();
    const recovery = screen.getByRole("link", { name: "Return to sign in" });
    expect(recovery.getAttribute("href")).toContain(
      "returnTo=%2Ftimeline%2Fmoment-1%3Fq%3Drain",
    );
    expect(sessionStore.read()).toBeNull();
  });

  it("does not send an overlong ticket from a crafted URL", async () => {
    await renderFinish(`/oidc-finish?ticket=${"x".repeat(513)}`);

    expect(
      await screen.findByRole("heading", {
        name: "Sign in wasn’t completed",
      }),
    ).toBeTruthy();
    expect(api.oidcExchange).not.toHaveBeenCalled();
  });
});
