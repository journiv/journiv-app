import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/client/errors";
import { createAppQueryClient } from "../../../app/queryClient";
import { UpdatesLicensePage } from "./UpdatesLicensePage";

vi.mock("../../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    versionInfo: vi.fn(),
    versionCheckEnabled: vi.fn(),
    updateVersionCheckEnabled: vi.fn(),
    forceVersionCheck: vi.fn(),
    licenseInfo: vi.fn(),
    registerLicense: vi.fn(),
    instanceConfig: vi.fn(),
  },
}));

import { api } from "../../../api/client/api";

const now = "2026-09-05T16:30:00Z";
const admin = {
  id: "admin-1",
  email: "admin@example.com",
  name: "Admin",
  role: "admin" as const,
  is_active: true,
  time_zone: "America/Los_Angeles",
  is_oidc_user: false,
  created_at: now,
  updated_at: now,
};

const version = {
  current_version: "1.2.0",
  install_id: "install-1",
  latest_version: "1.2.0",
  update_available: false,
  last_checked: now,
  last_check_success: true,
};

function renderPage() {
  const queryClient = createAppQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  return render(
    <QueryClientProvider client={queryClient}>
      <UpdatesLicensePage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.me).mockResolvedValue(admin);
  vi.mocked(api.versionInfo).mockResolvedValue(version);
  vi.mocked(api.versionCheckEnabled).mockResolvedValue({ enabled: true });
  vi.mocked(api.updateVersionCheckEnabled).mockImplementation(
    async ({ enabled }) => ({ enabled }),
  );
  vi.mocked(api.forceVersionCheck).mockResolvedValue({
    success: true,
    message: "Version check completed successfully",
    version_info: version,
  });
  vi.mocked(api.licenseInfo).mockRejectedValue(
    new ApiError("No license", { status: 404 }),
  );
  vi.mocked(api.registerLicense).mockResolvedValue({ successful: true });
  vi.mocked(api.instanceConfig).mockResolvedValue({
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
  });
});

describe("UpdatesLicensePage", () => {
  it("shows cached version state and a prefilled registration form when no license exists", async () => {
    renderPage();

    expect(await screen.findByText("1.2.0")).toBeTruthy();
    expect(screen.getByText("Up to date")).toBeTruthy();
    expect(
      screen
        .getByRole("switch", { name: "Automatic version checking" })
        .getAttribute("data-checked"),
    ).not.toBeNull();
    expect(screen.getByDisplayValue("admin@example.com")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Register license" }),
    ).toBeTruthy();
  });

  it("keeps a rate-limited manual check inline and prevents another immediate request", async () => {
    vi.mocked(api.forceVersionCheck).mockResolvedValue({
      success: false,
      message: "Rate limited",
      retry_after_seconds: 120,
    });
    renderPage();

    await userEvent.click(
      await screen.findByRole("button", { name: "Check for updates" }),
    );

    expect(
      await screen.findByText(/release service is rate limiting/i),
    ).toBeTruthy();
    expect(
      (
        screen.getByRole("button", {
          name: /try again in/i,
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(api.forceVersionCheck).toHaveBeenCalledTimes(1);
  });

  it("uses the backend toggle endpoint and refreshes cached version data after enabling", async () => {
    vi.mocked(api.versionCheckEnabled).mockResolvedValue({ enabled: false });
    renderPage();

    const automatic = await screen.findByRole("switch", {
      name: "Automatic version checking",
    });
    await userEvent.click(automatic);

    await waitFor(() =>
      expect(api.updateVersionCheckEnabled).toHaveBeenCalledWith({
        enabled: true,
      }),
    );
    expect(api.forceVersionCheck).not.toHaveBeenCalled();
  });

  it("shows an expired license and offers registration without an unbind action", async () => {
    vi.mocked(api.licenseInfo).mockResolvedValue({
      is_active: false,
      tier: "supporter",
      license_type: "subscription",
      subscription_expires_at: "2026-01-01T00:00:00Z",
      install_id: "install-1",
      registered_email: "buyer@example.com",
    });
    renderPage();

    expect((await screen.findAllByText("Expired")).length).toBeGreaterThan(0);
    expect(screen.getByText("buyer@example.com")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Register license" }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: /unbind|reset/i })).toBeNull();
  });

  it.each([403, 500, 501, 503])(
    "shows the load-error state, not the registration form, when license info fails with %i",
    async (status) => {
      vi.mocked(api.licenseInfo).mockRejectedValue(
        new ApiError("nope", { status }),
      );
      renderPage();

      // A non-404 is an error/capability answer — never a cue to register.
      // `retryTransient` may retry a 5xx a couple of times first; the settled
      // state is a load error, and the registration form must never appear.
      await waitFor(
        () =>
          expect(
            screen.getByText(/license details couldn.t be loaded/i),
          ).toBeTruthy(),
        { timeout: 6000 },
      );
      expect(
        screen.queryByRole("button", { name: "Register license" }),
      ).toBeNull();
      expect(screen.queryByLabelText("License key")).toBeNull();
    },
  );

  it("registers a license with the editable email and then refreshes status", async () => {
    vi.mocked(api.licenseInfo)
      .mockRejectedValueOnce(new ApiError("No license", { status: 404 }))
      .mockResolvedValue({
        is_active: true,
        tier: "supporter",
        license_type: "lifetime",
        install_id: "install-1",
      });
    renderPage();

    const license = await screen.findByLabelText("License key");
    const email = screen.getByLabelText("Admin email");
    await userEvent.type(license, "lic_abcdefghijklmnopqrstuvwxyz123456");
    await userEvent.clear(email);
    await userEvent.type(email, "buyer@example.com");
    await userEvent.click(
      screen.getByRole("button", { name: "Register license" }),
    );

    await waitFor(() =>
      expect(api.registerLicense).toHaveBeenCalledWith({
        license: "lic_abcdefghijklmnopqrstuvwxyz123456",
        email: "buyer@example.com",
      }),
    );
    expect(await screen.findByText("Active")).toBeTruthy();
  });

  it("surfaces the backend's failure reason instead of the generic message", async () => {
    vi.mocked(api.registerLicense).mockResolvedValue({
      successful: false,
      error_message: "License already bound to another installation.",
    });
    renderPage();

    await userEvent.type(
      await screen.findByLabelText("License key"),
      "lic_abcdefghijklmnopqrstuvwxyz123456",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Register license" }),
    );

    expect(
      await screen.findByText("License already bound to another installation."),
    ).toBeTruthy();
    expect(screen.queryByText(/check the key and email/i)).toBeNull();
  });

  it("surfaces a rate-limited registration with the server's cooldown message", async () => {
    vi.mocked(api.registerLicense).mockResolvedValue({
      successful: false,
      rate_limited: true,
      retry_after: 120,
      error_message: "Rate limit exceeded. Please try again in 2 minutes.",
    });
    renderPage();

    await userEvent.type(
      await screen.findByLabelText("License key"),
      "lic_abcdefghijklmnopqrstuvwxyz123456",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Register license" }),
    );

    expect(await screen.findByText(/rate limit exceeded/i)).toBeTruthy();
  });

  it("keeps a typed admin email when the current user query resolves late", async () => {
    let resolveMe: (value: typeof admin) => void = () => {};
    vi.mocked(api.me).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveMe = resolve;
        }),
    );
    renderPage();

    const email = await screen.findByLabelText("Admin email");
    await userEvent.type(email, "someone.else@example.com");

    // The signed-in admin's email arrives only now, after typing has started.
    resolveMe(admin);
    await waitFor(() =>
      expect(screen.getByLabelText("Admin email")).toHaveProperty(
        "value",
        "someone.else@example.com",
      ),
    );
    expect(screen.queryByDisplayValue("admin@example.com")).toBeNull();
  });
});
