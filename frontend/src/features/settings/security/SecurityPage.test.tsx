import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../../api/auth/session";
import { api } from "../../../api/client/api";
import type { UserResponse } from "../../../api/generated/types.gen";
import { createAppQueryClient } from "../../../app/queryClient";
import { createAppRouter } from "../../../app/router";

vi.mock("../../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    userSettings: vi.fn(),
    instanceConfig: vi.fn(),
    updateMe: vi.fn(),
    journals: vi.fn(),
    moments: vi.fn(),
  },
}));

const now = "2026-08-27T09:00:00Z";
const passwordUser: UserResponse = {
  id: "user-1",
  email: "writer@example.com",
  name: "Casey",
  role: "user",
  is_active: true,
  is_oidc_user: false,
  created_at: now,
  updated_at: now,
};

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue(passwordUser);
  vi.mocked(api.userSettings).mockResolvedValue({
    user_id: "user-1",
    time_zone: "UTC",
    daily_prompt_enabled: true,
    push_notifications: true,
    start_of_week_day: 0,
    time_format: "system",
    theme: "light",
    created_at: now,
    updated_at: now,
  });
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
  vi.mocked(api.updateMe).mockResolvedValue(passwordUser);
  vi.mocked(api.journals).mockResolvedValue([]);
  vi.mocked(api.moments).mockResolvedValue({ items: [] });
});

async function renderSecurity() {
  const history = createMemoryHistory({
    initialEntries: ["/settings/security"],
  });
  const router = createAppRouter(history);
  const queryClient = createAppQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
  return within(await screen.findByRole("dialog"));
}

describe("Settings · Security", () => {
  it("shows the password form for a password account", async () => {
    const view = await renderSecurity();
    expect(await view.findByLabelText("Current password")).toBeTruthy();
    expect(view.getByLabelText("New password")).toBeTruthy();
    expect(view.getByLabelText("Confirm new password")).toBeTruthy();
    expect(view.getByRole("button", { name: "Change password" })).toBeTruthy();
  });

  it("shows a provider notice and no form for an OIDC account", async () => {
    vi.mocked(api.me).mockResolvedValue({
      ...passwordUser,
      is_oidc_user: true,
    });
    const view = await renderSecurity();
    expect(await view.findByText(/identity provider/i)).toBeTruthy();
    expect(view.queryByLabelText("New password")).toBeNull();
    expect(view.queryByRole("button", { name: "Change password" })).toBeNull();
  });

  it("rejects a weak new password and a mismatch before calling the API", async () => {
    const view = await renderSecurity();
    await userEvent.type(
      await view.findByLabelText("Current password"),
      "old-pass-1",
    );
    await userEvent.type(view.getByLabelText("New password"), "short");
    await userEvent.type(
      view.getByLabelText("Confirm new password"),
      "different",
    );
    await userEvent.click(
      view.getByRole("button", { name: "Change password" }),
    );

    expect(await view.findByText("Use at least 8 characters.")).toBeTruthy();
    expect(view.getByText("This doesn’t match the new password.")).toBeTruthy();
    expect(api.updateMe).not.toHaveBeenCalled();
  });

  it("changes the password, clears the fields, and confirms", async () => {
    const view = await renderSecurity();
    const current = (await view.findByLabelText(
      "Current password",
    )) as HTMLInputElement;
    const next = view.getByLabelText("New password") as HTMLInputElement;
    const confirm = view.getByLabelText(
      "Confirm new password",
    ) as HTMLInputElement;
    await userEvent.type(current, "old-pass-1");
    await userEvent.type(next, "brand-new-2");
    await userEvent.type(confirm, "brand-new-2");
    await userEvent.click(
      view.getByRole("button", { name: "Change password" }),
    );

    await waitFor(() =>
      expect(api.updateMe).toHaveBeenCalledWith({
        current_password: "old-pass-1",
        new_password: "brand-new-2",
      }),
    );
    expect(
      await view.findByText("Your password has been changed."),
    ).toBeTruthy();
    expect(current.value).toBe("");
    expect(next.value).toBe("");
    expect(confirm.value).toBe("");
  });

  it("keeps the fields and reports failure when the change is rejected", async () => {
    vi.mocked(api.updateMe).mockRejectedValueOnce({
      detail: "Current password is incorrect",
    });
    const view = await renderSecurity();
    const current = (await view.findByLabelText(
      "Current password",
    )) as HTMLInputElement;
    await userEvent.type(current, "wrong-pass-1");
    await userEvent.type(view.getByLabelText("New password"), "brand-new-2");
    await userEvent.type(
      view.getByLabelText("Confirm new password"),
      "brand-new-2",
    );
    await userEvent.click(
      view.getByRole("button", { name: "Change password" }),
    );

    expect(
      (await view.findAllByRole("alert")).some((node) =>
        node.textContent?.includes("couldn’t be changed"),
      ),
    ).toBe(true);
    expect(current.value).toBe("wrong-pass-1");
  });

  it("never writes password input to storage", async () => {
    const view = await renderSecurity();
    await userEvent.type(
      await view.findByLabelText("New password"),
      "brand-new-2",
    );
    const dump = JSON.stringify([
      { ...window.localStorage },
      { ...window.sessionStorage },
    ]);
    expect(dump).not.toContain("brand-new-2");
  });
});
