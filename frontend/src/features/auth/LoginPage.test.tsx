import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
    login: vi.fn(),
  },
}));

const instanceConfig: InstanceConfigResponse = {
  import_export_max_file_size_mb: 100,
  max_file_size_mb: 50,
  disable_signup: false,
  oidc_enabled: false,
  oidc_only: false,
  plus: {
    available: false,
    tier: "member",
    upgrade_url: "https://journiv.com/plus",
  },
};

async function renderLogin(path = "/login") {
  const history = createMemoryHistory({ initialEntries: [path] });
  const router = createAppRouter(history);
  const queryClient = createAppQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
  return { ...view, queryClient, router };
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.mocked(api.instanceConfig).mockResolvedValue(instanceConfig);
    vi.mocked(api.login).mockResolvedValue({
      access_token: "access-token",
      refresh_token: "refresh-token",
    } as never);
  });

  it("shows password and OIDC choices together without losing returnTo", async () => {
    vi.mocked(api.instanceConfig).mockResolvedValue({
      ...instanceConfig,
      oidc_enabled: true,
    });
    await renderLogin("/login?returnTo=%2Ftimeline%2Fmoment-1%3Fq%3Drain");

    expect(await screen.findByLabelText("Email")).toBeTruthy();
    expect(screen.getByLabelText("Password")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeTruthy();
    expect(screen.getByText("or")).toBeTruthy();
    expect(screen.queryAllByRole("separator")).toHaveLength(0);
    expect(screen.getAllByRole("separator", { hidden: true })).toHaveLength(2);
    const oidc = screen.getByRole("link", {
      name: "Continue with single sign-on",
    });
    expect(oidc.getAttribute("href")).toBe("/api/v1/auth/oidc/login");

    oidc.addEventListener("click", (event) => event.preventDefault());
    fireEvent.click(oidc);
    expect(oidcReturnToStore.read()).toBe("/timeline/moment-1?q=rain");
  });

  it("renders only the OIDC action when the instance is OIDC-only", async () => {
    vi.mocked(api.instanceConfig).mockResolvedValue({
      ...instanceConfig,
      disable_signup: true,
      oidc_enabled: true,
      oidc_only: true,
    });
    await renderLogin();

    expect(
      await screen.findByRole("link", {
        name: "Continue with single sign-on",
      }),
    ).toBeTruthy();
    expect(screen.getByText(/uses single sign-on/i)).toBeTruthy();
    expect(screen.queryByLabelText("Email")).toBeNull();
    expect(screen.queryByLabelText("Password")).toBeNull();
    expect(screen.queryByRole("button", { name: "Sign in" })).toBeNull();
    expect(
      screen.queryByRole("link", { name: "Create an account" }),
    ).toBeNull();
  });

  it("keeps OIDC available when password signup is disabled", async () => {
    vi.mocked(api.instanceConfig).mockResolvedValue({
      ...instanceConfig,
      disable_signup: true,
      oidc_enabled: true,
    });
    await renderLogin();

    expect(
      await screen.findByRole("link", {
        name: "Continue with single sign-on",
      }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("link", { name: "Create an account" }),
    ).toBeNull();
  });

  it("fails closed and retries when sign-in capabilities cannot load", async () => {
    vi.mocked(api.instanceConfig)
      .mockRejectedValueOnce(new Error("network detail"))
      .mockResolvedValueOnce(instanceConfig);
    await renderLogin();

    expect(
      await screen.findByRole("heading", { name: "Sign in unavailable" }),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Email")).toBeNull();
    expect(screen.queryByText("network detail")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByLabelText("Email")).toBeTruthy();
    expect(api.instanceConfig).toHaveBeenCalledTimes(2);
  });

  it("stores a password session and returns to the intended route", async () => {
    const view = await renderLogin("/login?returnTo=%2Fsignup");
    sessionStore.write({
      version: 1,
      accessToken: "previous-access",
      refreshToken: "previous-refresh",
    });
    view.queryClient.setQueryData(queryKeys.promptAnalytics, {
      prompts_answered: 7,
    });
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("Email"),
      "person@example.com",
    );
    await user.type(screen.getByLabelText("Password"), "private-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe("/signup"),
    );
    expect(api.login).toHaveBeenCalledWith(
      "person@example.com",
      "private-password",
    );
    expect(sessionStore.read()).toEqual({
      version: 1,
      accessToken: "access-token",
      refreshToken: "refresh-token",
    });
    expect(
      view.queryClient.getQueryData(queryKeys.promptAnalytics),
    ).toBeUndefined();
  });

  it("uses a generic password error and retains entered credentials", async () => {
    vi.mocked(api.login).mockRejectedValue(
      new Error("sensitive server detail"),
    );
    await renderLogin();
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("Email"),
      "person@example.com",
    );
    await user.type(screen.getByLabelText("Password"), "still-here");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(
      await screen.findByText("Sign in failed. Check your email and password."),
    ).toBeTruthy();
    expect(screen.queryByText("sensitive server detail")).toBeNull();
    expect((screen.getByLabelText("Email") as HTMLInputElement).value).toBe(
      "person@example.com",
    );
    expect((screen.getByLabelText("Password") as HTMLInputElement).value).toBe(
      "still-here",
    );
    expect(sessionStore.read()).toBeNull();
  });
});
