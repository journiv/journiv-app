import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../../api/auth/session";
import { api } from "../../../api/client/api";
import type { UserSettingsResponse } from "../../../api/generated/types.gen";
import { createAppQueryClient } from "../../../app/queryClient";
import { createAppRouter } from "../../../app/router";

vi.mock("../../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    userSettings: vi.fn(),
    updateUserSettings: vi.fn(),
    instanceConfig: vi.fn(),
    journals: vi.fn(),
    moments: vi.fn(),
  },
}));

const now = "2026-08-27T09:00:00Z";
const settings: UserSettingsResponse = {
  user_id: "user-1",
  theme: "light",
  time_format: "system",
  start_of_week_day: 0,
  time_zone: "UTC",
  created_at: now,
  updated_at: now,
};

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue({
    id: "user-1",
    email: "writer@example.com",
    name: "Writer",
    role: "user",
    is_active: true,
    is_oidc_user: false,
    created_at: now,
    updated_at: now,
  });
  vi.mocked(api.userSettings).mockResolvedValue(settings);
  vi.mocked(api.updateUserSettings).mockResolvedValue(settings);
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
  vi.mocked(api.journals).mockResolvedValue([]);
  vi.mocked(api.moments).mockResolvedValue({ items: [] });
});

async function view() {
  const router = createAppRouter(
    createMemoryHistory({ initialEntries: ["/settings/appearance"] }),
  );
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

describe("Settings · Appearance", () => {
  it("initialises account defaults and disables a no-op save", async () => {
    const page = await view();
    expect(
      ((await page.findByLabelText("Account theme")) as HTMLSelectElement)
        .value,
    ).toBe("light");
    expect(
      (page.getByRole("button", { name: "Save changes" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("saves all appearance defaults and invalidates the shared settings query", async () => {
    vi.mocked(api.updateUserSettings).mockImplementation(async (body) => ({
      ...settings,
      theme: body.theme ?? settings.theme,
      time_format: body.time_format ?? settings.time_format,
      start_of_week_day: body.start_of_week_day ?? settings.start_of_week_day,
    }));
    const page = await view();
    await userEvent.selectOptions(
      await page.findByLabelText("Account theme"),
      "dark",
    );
    await userEvent.selectOptions(
      page.getByLabelText("Time format"),
      "twenty_four_hour",
    );
    await userEvent.selectOptions(page.getByLabelText("Week starts on"), "1");
    await userEvent.click(page.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(api.updateUserSettings).toHaveBeenCalledWith({
        theme: "dark",
        time_format: "twenty_four_hour",
        start_of_week_day: 1,
      }),
    );
  });

  it("keeps values and reports a failed save", async () => {
    vi.mocked(api.updateUserSettings).mockRejectedValueOnce(
      new Error("network"),
    );
    const page = await view();
    const theme = (await page.findByLabelText(
      "Account theme",
    )) as HTMLSelectElement;
    await userEvent.selectOptions(theme, "dark");
    await userEvent.click(page.getByRole("button", { name: "Save changes" }));
    expect((await page.findByRole("alert")).textContent).toContain(
      "couldn’t be saved",
    );
    expect(theme.value).toBe("dark");
  });
});
