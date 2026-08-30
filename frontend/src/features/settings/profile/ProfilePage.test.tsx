import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../../api/auth/session";
import { api } from "../../../api/client/api";
import type {
  UserResponse,
  UserSettingsResponse,
} from "../../../api/generated/types.gen";
import { createAppQueryClient } from "../../../app/queryClient";
import { createAppRouter } from "../../../app/router";

vi.mock("../../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    userSettings: vi.fn(),
    instanceConfig: vi.fn(),
    updateMe: vi.fn(),
    updateUserSettings: vi.fn(),
    journals: vi.fn(),
    moments: vi.fn(),
  },
}));

const now = "2026-08-27T09:00:00Z";
const user: UserResponse = {
  id: "user-1",
  email: "writer@example.com",
  name: "Casey",
  role: "user",
  is_active: true,
  time_zone: "Europe/Vienna",
  is_oidc_user: false,
  created_at: now,
  updated_at: now,
};
const settings: UserSettingsResponse = {
  user_id: user.id,
  time_zone: "Europe/Vienna",
  daily_prompt_enabled: true,
  push_notifications: true,
  start_of_week_day: 0,
  time_format: "system",
  theme: "light",
  created_at: now,
  updated_at: now,
};

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({
    version: 1,
    accessToken: "a",
    refreshToken: "r",
  });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.userSettings).mockResolvedValue(settings);
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
  vi.mocked(api.updateMe).mockResolvedValue(user);
  vi.mocked(api.updateUserSettings).mockResolvedValue(settings);
  vi.mocked(api.journals).mockResolvedValue([]);
  vi.mocked(api.moments).mockResolvedValue({ items: [] });
});

async function renderProfile() {
  const history = createMemoryHistory({
    initialEntries: ["/settings/profile"],
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
  const dialog = await screen.findByRole("dialog");
  return within(dialog);
}

describe("Settings · Profile", () => {
  it("initialises from the current user and settings", async () => {
    const view = await renderProfile();
    expect(
      ((await view.findByLabelText("Display name")) as HTMLInputElement).value,
    ).toBe("Casey");
    expect(view.getAllByText("writer@example.com").length).toBeGreaterThan(0);
    expect((view.getByLabelText("Timezone") as HTMLInputElement).value).toBe(
      "Europe/Vienna",
    );
  });

  it("keeps Save disabled until something changes", async () => {
    const view = await renderProfile();
    await view.findByLabelText("Display name");
    expect(
      (view.getByRole("button", { name: "Save changes" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("saves only the display name when only the name changed", async () => {
    vi.mocked(api.updateMe).mockImplementation(async (body) => {
      const updated = { ...user, ...body } as UserResponse;
      vi.mocked(api.me).mockResolvedValue(updated);
      return updated;
    });
    const view = await renderProfile();
    const name = (await view.findByLabelText(
      "Display name",
    )) as HTMLInputElement;
    await userEvent.type(name, " Jordan");
    await userEvent.click(view.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(api.updateMe).toHaveBeenCalledWith({ name: "Casey Jordan" }),
    );
    expect(api.updateUserSettings).not.toHaveBeenCalled();
    expect(await view.findByText("Profile saved.")).toBeTruthy();
    // current-user cache was refreshed for the sidebar.
    await waitFor(() =>
      expect(vi.mocked(api.me).mock.calls.length).toBeGreaterThan(1),
    );
  });

  it("saves only the timezone when only the timezone changed", async () => {
    const view = await renderProfile();
    await view.findByLabelText("Display name");
    const zone = view.getByLabelText("Timezone") as HTMLInputElement;
    await userEvent.tripleClick(zone);
    await userEvent.keyboard("UTC");
    // The combobox listbox portals to document.body, outside the dialog scope.
    await userEvent.click(await screen.findByRole("option", { name: "UTC" }));
    await userEvent.click(view.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(api.updateUserSettings).toHaveBeenCalledWith({ time_zone: "UTC" }),
    );
    expect(api.updateMe).not.toHaveBeenCalled();
  });

  it("blocks an empty display name with a field error", async () => {
    const view = await renderProfile();
    const name = (await view.findByLabelText(
      "Display name",
    )) as HTMLInputElement;
    await userEvent.clear(name);
    await userEvent.click(view.getByRole("button", { name: "Save changes" }));

    expect(await view.findByText("Enter a display name.")).toBeTruthy();
    expect(api.updateMe).not.toHaveBeenCalled();
  });

  it("keeps entered values and shows a message when the save fails", async () => {
    vi.mocked(api.updateMe).mockRejectedValueOnce(new Error("network"));
    const view = await renderProfile();
    const name = (await view.findByLabelText(
      "Display name",
    )) as HTMLInputElement;
    await userEvent.type(name, " Rivers");
    await userEvent.click(view.getByRole("button", { name: "Save changes" }));

    expect(
      (await view.findAllByRole("alert")).some((node) =>
        node.textContent?.includes("couldn’t be saved"),
      ),
    ).toBe(true);
    expect(name.value).toBe("Casey Rivers");
  });
});
