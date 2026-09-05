import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { InstanceConfigResponse } from "../../api/generated";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import { ApiError } from "../../api/client/errors";
import { queryKeys } from "../../api/query/keys";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";
import { signUpErrorMessage } from "./SignUpPage";
import { oidcReturnToStore } from "./oidc";

vi.mock("../../api/client/api", () => ({
  api: {
    instanceConfig: vi.fn(),
    register: vi.fn(),
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

async function renderSignUp(path = "/signup?returnTo=%2Flogin") {
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

async function completeForm(options?: { password?: string; confirm?: string }) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Name"), "  Rowan Lee  ");
  await user.type(screen.getByLabelText("Email"), "ROWAN@Example.com");
  await user.type(
    screen.getByLabelText("Password", { selector: "input" }),
    options?.password ?? "memory-lane",
  );
  await user.type(
    screen.getByLabelText("Confirm password"),
    options?.confirm ?? options?.password ?? "memory-lane",
  );
  return user;
}

describe("SignUpPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.mocked(api.instanceConfig).mockResolvedValue(instanceConfig);
    vi.mocked(api.register).mockResolvedValue({} as never);
    vi.mocked(api.login).mockResolvedValue({
      access_token: "new-access",
      refresh_token: "new-refresh",
    } as never);
  });

  it("renders the complete form and keeps returnTo on the sign-in link", async () => {
    const view = await renderSignUp(
      "/signup?returnTo=%2Ftimeline%2Fmoment-1%3Fq%3Drain",
    );

    expect(
      await screen.findByRole("heading", { name: "Create your account" }),
    ).toBeTruthy();
    expect(screen.getByLabelText("Name")).toBeTruthy();
    expect(screen.getByLabelText("Email")).toBeTruthy();
    expect(
      screen
        .getByLabelText("Password", { selector: "input" })
        .getAttribute("autocomplete"),
    ).toBe("new-password");
    expect(
      screen.getByLabelText("Confirm password").getAttribute("autocomplete"),
    ).toBe("new-password");

    await userEvent.click(screen.getByRole("link", { name: "Sign in" }));
    await waitFor(() => {
      expect(view.router.state.location.pathname).toBe("/login");
      expect(view.router.state.location.search.returnTo).toBe(
        "/timeline/moment-1?q=rain",
      );
    });
  });

  it("is linked from login without losing the intended destination", async () => {
    const view = await renderSignUp(
      "/login?returnTo=%2Ftimeline%2Fmoment-1%3Fq%3Drain",
    );

    await userEvent.click(
      await screen.findByRole("link", { name: "Create an account" }),
    );

    await waitFor(() => {
      expect(view.router.state.location.pathname).toBe("/signup");
      expect(view.router.state.location.search.returnTo).toBe(
        "/timeline/moment-1?q=rain",
      );
    });
  });

  it("offers OIDC alongside password signup and preserves returnTo", async () => {
    vi.mocked(api.instanceConfig).mockResolvedValue({
      ...instanceConfig,
      oidc_enabled: true,
    });
    await renderSignUp("/signup?returnTo=%2Ftimeline%2Fmoment-1");

    expect(await screen.findByLabelText("Name")).toBeTruthy();
    expect(screen.queryAllByRole("separator")).toHaveLength(0);
    expect(screen.getAllByRole("separator", { hidden: true })).toHaveLength(2);
    const oidc = screen.getByRole("link", {
      name: "Continue with single sign-on",
    });
    expect(oidc.getAttribute("href")).toBe("/api/v1/auth/oidc/login");
    oidc.addEventListener("click", (event) => event.preventDefault());
    await userEvent.click(oidc);
    expect(oidcReturnToStore.read()).toBe("/timeline/moment-1");
  });

  it("uses OIDC instead of a password form in OIDC-only mode", async () => {
    vi.mocked(api.instanceConfig).mockResolvedValue({
      ...instanceConfig,
      disable_signup: true,
      oidc_enabled: true,
      oidc_only: true,
    });
    await renderSignUp();

    expect(
      await screen.findByRole("heading", {
        name: "Create or access your account",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Continue with single sign-on" }),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Name")).toBeNull();
    expect(screen.queryByLabelText("Password")).toBeNull();
  });

  it("keeps OIDC available when only password signup is disabled", async () => {
    vi.mocked(api.instanceConfig).mockResolvedValue({
      ...instanceConfig,
      disable_signup: true,
      oidc_enabled: true,
    });
    await renderSignUp();

    expect(
      await screen.findByRole("heading", {
        name: "Password sign up is disabled",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Continue with single sign-on" }),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Name")).toBeNull();
  });

  it("normalizes supported fields, signs in, stores the session and returns", async () => {
    const view = await renderSignUp();
    sessionStore.write({
      version: 1,
      accessToken: "previous-access",
      refreshToken: "previous-refresh",
    });
    view.queryClient.setQueryData(queryKeys.promptAnalytics, {
      prompts_answered: 7,
    });
    const user = await completeForm();

    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() =>
      expect(api.register).toHaveBeenCalledWith({
        name: "Rowan Lee",
        email: "rowan@example.com",
        password: "memory-lane",
      }),
    );
    expect(api.login).toHaveBeenCalledWith("rowan@example.com", "memory-lane");
    expect(sessionStore.read()).toEqual({
      version: 1,
      accessToken: "new-access",
      refreshToken: "new-refresh",
    });
    expect(
      view.queryClient.getQueryData(queryKeys.promptAnalytics),
    ).toBeUndefined();
    expect(view.router.state.location.pathname).toBe("/login");
  });

  it("surfaces every empty or malformed field without sending a request", async () => {
    await renderSignUp();
    await userEvent.click(
      await screen.findByRole("button", { name: "Create account" }),
    );

    expect(screen.getByText("Enter your name.")).toBeTruthy();
    expect(screen.getByText("Enter a valid email address.")).toBeTruthy();
    expect(screen.getByText("Enter a password.")).toBeTruthy();
    expect(screen.getByText("Confirm your password.")).toBeTruthy();
    expect(screen.getByLabelText("Name").getAttribute("aria-invalid")).toBe(
      "true",
    );
    expect(api.register).not.toHaveBeenCalled();
    expect(api.login).not.toHaveBeenCalled();
  });

  it("refuses mismatched confirmation and preserves the entered values", async () => {
    await renderSignUp();
    const user = await completeForm({
      password: "memory-lane",
      confirm: "different-memory",
    });

    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(screen.getByText("The passwords don’t match.")).toBeTruthy();
    expect(
      (screen.getByLabelText("Confirm password") as HTMLInputElement).value,
    ).toBe("different-memory");
    expect(api.register).not.toHaveBeenCalled();
  });

  it("does not invent a password-strength rule absent from UserCreate", async () => {
    await renderSignUp();
    const user = await completeForm({ password: "x", confirm: "x" });

    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() =>
      expect(api.register).toHaveBeenCalledWith(
        expect.objectContaining({ password: "x" }),
      ),
    );
  });

  it("disables duplicate submits and communicates pending progress", async () => {
    let finishRegistration: (() => void) | undefined;
    vi.mocked(api.register).mockImplementation(
      () =>
        new Promise((resolve) => {
          finishRegistration = () => resolve({} as never);
        }),
    );
    await renderSignUp();
    const user = await completeForm();

    await user.click(screen.getByRole("button", { name: "Create account" }));

    const pendingButton = screen.getByRole("button", {
      name: "Creating account…",
    });
    expect((pendingButton as HTMLButtonElement).disabled).toBe(true);
    await user.click(pendingButton);
    expect(api.register).toHaveBeenCalledTimes(1);
    finishRegistration?.();
    await waitFor(() => expect(api.login).toHaveBeenCalledTimes(1));
  });

  it("shows a status-aware failure, retains fields and never starts login", async () => {
    vi.mocked(api.register).mockRejectedValue(
      new ApiError("Sign up is disabled", { status: 403 }),
    );
    await renderSignUp();
    const user = await completeForm();

    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(
      await screen.findByText(
        "Account creation isn’t available on this Journiv instance.",
      ),
    ).toBeTruthy();
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe(
      "  Rowan Lee  ",
    );
    expect((screen.getByLabelText("Email") as HTMLInputElement).value).toBe(
      "ROWAN@Example.com",
    );
    expect(api.login).not.toHaveBeenCalled();
    expect(sessionStore.read()).toBeNull();
  });

  it("moves to a sign-in recovery state when registration alone succeeds", async () => {
    vi.mocked(api.login).mockRejectedValue(
      new ApiError("Login unavailable", { status: 503 }),
    );
    await renderSignUp();
    const user = await completeForm();

    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(
      await screen.findByRole("heading", { name: "Account created" }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Create account" })).toBeNull();
    expect(screen.getByRole("link", { name: "Sign in" })).toBeTruthy();
    expect(sessionStore.read()).toBeNull();
  });

  it("rejects external returnTo values", async () => {
    const view = await renderSignUp(
      "/signup?returnTo=https%3A%2F%2Fevil.example%2Fsteal",
    );
    expect(view.router.state.location.search.returnTo).toBe("/timeline");
  });

  it("fails closed with guidance when signup is disabled", async () => {
    vi.mocked(api.instanceConfig).mockResolvedValue({
      ...instanceConfig,
      disable_signup: true,
    });
    const view = await renderSignUp("/signup?returnTo=%2Ftimeline%2Fmoment-1");

    expect(
      await screen.findByRole("heading", { name: "Sign up is disabled" }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /administrator can enable sign up in the server configuration and restart Journiv/i,
      ),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Email")).toBeNull();
    expect(screen.queryByRole("button", { name: "Create account" })).toBeNull();
    expect(api.register).not.toHaveBeenCalled();

    await userEvent.click(
      screen.getByRole("link", { name: "Return to sign in" }),
    );
    await waitFor(() => {
      expect(view.router.state.location.pathname).toBe("/login");
      expect(view.router.state.location.search.returnTo).toBe(
        "/timeline/moment-1",
      );
    });
  });

  it("hides the login signup link when signup is disabled", async () => {
    vi.mocked(api.instanceConfig).mockResolvedValue({
      ...instanceConfig,
      disable_signup: true,
    });
    await renderSignUp("/login");

    expect(
      await screen.findByRole("heading", { name: "Welcome back" }),
    ).toBeTruthy();
    await waitFor(() => expect(api.instanceConfig).toHaveBeenCalledTimes(1));
    expect(
      screen.queryByRole("link", { name: "Create an account" }),
    ).toBeNull();
  });

  it("keeps the signup form unavailable when configuration cannot load", async () => {
    vi.mocked(api.instanceConfig).mockRejectedValueOnce(
      new ApiError("Unavailable", { status: 503 }),
    );
    await renderSignUp();

    expect(
      await screen.findByRole("heading", { name: "Sign up unavailable" }),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Email")).toBeNull();
    expect(screen.queryByRole("button", { name: "Create account" })).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("rechecks configuration before revealing the signup form", async () => {
    vi.mocked(api.instanceConfig)
      .mockRejectedValueOnce(new ApiError("Unavailable", { status: 503 }))
      .mockResolvedValueOnce(instanceConfig);
    await renderSignUp();

    await userEvent.click(
      await screen.findByRole("button", { name: "Try again" }),
    );

    expect(
      await screen.findByRole("heading", { name: "Create your account" }),
    ).toBeTruthy();
    expect(api.instanceConfig).toHaveBeenCalledTimes(2);
  });
});

describe("signUpErrorMessage", () => {
  it.each([
    [
      400,
      "We couldn’t create that account. Check your details or sign in if you already have one.",
    ],
    [403, "Account creation isn’t available on this Journiv instance."],
    [422, "Check your account details and try again."],
    [429, "Too many account creation attempts. Wait a moment and try again."],
    [500, "We couldn’t create your account. Try again."],
  ])("maps status %i without exposing server detail", (status, expected) => {
    expect(
      signUpErrorMessage(new ApiError("sensitive backend detail", { status })),
    ).toBe(expected);
  });

  it("uses the same safe fallback for a network failure", () => {
    expect(signUpErrorMessage(new TypeError("Failed to fetch"))).toBe(
      "We couldn’t create your account. Try again.",
    );
  });
});
