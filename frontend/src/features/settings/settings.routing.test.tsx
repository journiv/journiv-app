import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import type {
  AdminUserListResponse,
  InstanceConfigResponse,
  MomentResponse,
  UserResponse,
  UserSettingsResponse,
} from "../../api/generated/types.gen";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";
import { setTestViewportWidth } from "../../test/viewport";

vi.mock("../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    userSettings: vi.fn(),
    instanceConfig: vi.fn(),
    updateMe: vi.fn(),
    updateUserSettings: vi.fn(),
    journals: vi.fn(),
    moments: vi.fn(),
    moment: vi.fn(),
    entry: vi.fn(),
    tags: vi.fn(),
    people: vi.fn(),
    moods: vi.fn(),
    activities: vi.fn(),
    goals: vi.fn(),
    versionInfo: vi.fn(),
    licenseInfo: vi.fn(),
    integrationStatus: vi.fn(),
    adminUsers: vi.fn(),
    createAdminUser: vi.fn(),
    updateAdminUser: vi.fn(),
    deleteAdminUser: vi.fn(),
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
const adminUser: UserResponse = { ...user, role: "admin" };
const adminListUser: AdminUserListResponse = {
  id: adminUser.id,
  email: adminUser.email,
  name: adminUser.name ?? "Casey",
  role: "admin",
  is_active: true,
  last_login_at: now,
  created_at: now,
  login_type: "local",
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
const instance: InstanceConfigResponse = {
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
const moment: MomentResponse = {
  id: "moment-1",
  user_id: user.id,
  logged_at_utc: now,
  logged_date_tz: "2026-08-27",
  logged_timezone: "Europe/Vienna",
  entry: {
    id: "entry-1",
    journal_id: "journal-1",
    moment_id: "moment-1",
    title: "A clear morning",
    content_plain_text: "The sky was open.",
    created_at: now,
    updated_at: now,
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({
    version: 1,
    accessToken: "access",
    refreshToken: "refresh",
  });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.userSettings).mockResolvedValue(settings);
  vi.mocked(api.instanceConfig).mockResolvedValue(instance);
  vi.mocked(api.updateMe).mockResolvedValue(user);
  vi.mocked(api.updateUserSettings).mockResolvedValue(settings);
  vi.mocked(api.journals).mockResolvedValue([]);
  vi.mocked(api.moments).mockResolvedValue({ items: [] });
  vi.mocked(api.moment).mockResolvedValue(moment);
  vi.mocked(api.entry).mockResolvedValue({
    id: "entry-1",
    user_id: user.id,
    journal_id: "journal-1",
    moment_id: "moment-1",
    title: "A clear morning",
    content_plain_text: "The sky was open.",
    content_delta: { ops: [{ insert: "The sky was open.\n" }] },
    word_count: 4,
    created_at: now,
    updated_at: now,
  });
  vi.mocked(api.tags).mockResolvedValue([]);
  vi.mocked(api.people).mockResolvedValue([]);
  vi.mocked(api.moods).mockResolvedValue([]);
  vi.mocked(api.activities).mockResolvedValue([]);
  vi.mocked(api.goals).mockResolvedValue([]);
  vi.mocked(api.versionInfo).mockResolvedValue({
    current_version: "1.0.0",
    install_id: "install-1",
  });
  vi.mocked(api.licenseInfo).mockResolvedValue({
    is_active: false,
    license_type: "lifetime",
    install_id: "install-1",
  });
  vi.mocked(api.integrationStatus).mockResolvedValue({
    provider: "immich",
    status: "disconnected",
    import_mode: "link_only",
  });
  vi.mocked(api.adminUsers).mockResolvedValue([adminListUser]);
  vi.mocked(api.createAdminUser).mockResolvedValue(adminUser);
  vi.mocked(api.updateAdminUser).mockResolvedValue(adminUser);
  vi.mocked(api.deleteAdminUser).mockResolvedValue({});
});

async function renderRoute(path: string) {
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
  return { ...view, router };
}

describe("Settings routing and modal", () => {
  it("opens the modal on a direct deep link to a section", async () => {
    const view = await renderRoute("/settings/security");

    const dialog = await screen.findByRole("dialog");
    expect(view.router.state.location.pathname).toBe("/settings/security");
    expect(
      await within(dialog).findByRole("heading", { name: "Password" }),
    ).toBeTruthy();
  });

  it.each([
    ["/settings/appearance", "Appearance", "Theme & time"],
    ["/settings/integrations", "No integrations available", "Providers"],
    ["/settings/data/import", "Import", "Import"],
    ["/settings/data/export", "Export", "Export"],
    ["/settings/support/help", "Help & feedback", "Help & feedback"],
    ["/settings/support/about", "About Journiv", "About"],
  ])("opens %s and marks its nav item active", async (path, heading, link) => {
    await renderRoute(path);
    const dialog = await screen.findByRole("dialog");
    expect(
      (await within(dialog).findAllByText(heading)).length,
    ).toBeGreaterThan(0);
    expect(
      within(dialog)
        .getByRole("link", { name: link })
        .getAttribute("aria-current"),
    ).toBe("page");
  });

  it("does not list content collections as Settings sections", async () => {
    await renderRoute("/settings/profile");
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByRole("link", { name: "People" })).toBeNull();
    expect(within(dialog).queryByRole("link", { name: "Tags" })).toBeNull();
    expect(within(dialog).queryByText("Journaling")).toBeNull();
    expect(within(dialog).queryByRole("link", { name: "Users" })).toBeNull();
  });

  it("shows user administration only to admins and marks its real route active", async () => {
    vi.mocked(api.me).mockResolvedValue(adminUser);
    const view = await renderRoute("/settings/admin/users");
    const dialog = await screen.findByRole("dialog");

    expect(view.router.state.location.pathname).toBe("/settings/admin/users");
    expect(
      await within(dialog).findByRole("heading", { name: "Users" }),
    ).toBeTruthy();
    expect(
      within(dialog)
        .getByRole("link", { name: "Users" })
        .getAttribute("aria-current"),
    ).toBe("page");
  });

  it("redirects a non-admin deep link before mounting the admin list", async () => {
    const view = await renderRoute("/settings/admin/users");

    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe("/settings/profile"),
    );
    expect(api.adminUsers).not.toHaveBeenCalled();
    expect(screen.queryByRole("link", { name: "Users" })).toBeNull();
  });

  it("switches section from the in-modal navigation without closing", async () => {
    const view = await renderRoute("/settings/profile");
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByRole("heading", {
      name: "Personal information",
    });

    await userEvent.click(
      within(dialog).getByRole("link", { name: "Security" }),
    );

    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe("/settings/security"),
    );
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(
      within(screen.getByRole("dialog"))
        .getByRole("link", { name: "Security" })
        .getAttribute("aria-current"),
    ).toBe("page");
  });

  it("marks the active section from the route, not the search params", async () => {
    await renderRoute("/settings/profile?q=whatever");
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog)
        .getByRole("link", { name: "Profile" })
        .getAttribute("aria-current"),
    ).toBe("page");
    expect(
      within(dialog)
        .getByRole("link", { name: "Security" })
        .getAttribute("aria-current"),
    ).toBeNull();
  });

  it("opens from the current route and closes back to it", async () => {
    // Compact: /settings stays on the section list rather than redirecting to
    // Profile (DESIGN.md §23). Pinned explicitly — this used to depend on the
    // jsdom matchMedia stub matching nothing.
    setTestViewportWidth(860);
    const view = await renderRoute("/timeline/moment-1?q=rain");
    await screen.findAllByText("A clear morning");

    await userEvent.click(screen.getByRole("button", { name: "Settings" }));
    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe("/settings"),
    );
    await screen.findByRole("dialog");

    await userEvent.click(
      screen.getByRole("button", { name: "Close settings" }),
    );

    await waitFor(() => {
      expect(view.router.state.location.pathname).toBe("/timeline/moment-1");
      expect(view.router.state.location.search.q).toBe("rain");
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("falls back to the timeline when closed after a direct deep link", async () => {
    const view = await renderRoute("/settings/security");
    await screen.findByRole("dialog");

    await userEvent.click(
      screen.getByRole("button", { name: "Close settings" }),
    );

    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe("/timeline"),
    );
  });

  it("shows the section list on compact /settings and drills into a section", async () => {
    // Below Settings' 1101px boundary, /settings does not redirect.
    setTestViewportWidth(860);
    const view = await renderRoute("/settings");
    const dialog = await screen.findByRole("dialog");
    const links = within(dialog).getAllByRole("link", { name: "Profile" });
    expect(links.length).toBeGreaterThan(0);

    await userEvent.click(links[0]);
    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe("/settings/profile"),
    );
  });

  it("redirects /settings to Profile on desktop widths", async () => {
    const original = window.matchMedia;
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: (query: string) => ({
        matches: query.includes("min-width: 1101px"),
        media: query,
        onchange: null,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        addListener: () => undefined,
        removeListener: () => undefined,
        dispatchEvent: () => false,
      }),
    });
    try {
      const view = await renderRoute("/settings");
      await waitFor(() =>
        expect(view.router.state.location.pathname).toBe("/settings/profile"),
      );
    } finally {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        value: original,
      });
    }
  });

  it("warns before discarding unsaved profile edits, and stays when cancelled", async () => {
    const view = await renderRoute("/settings/profile");
    const dialog = await screen.findByRole("dialog");
    const name = await within(dialog).findByLabelText("Display name");
    await userEvent.type(name, " Jordan");

    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await userEvent.click(
      screen.getByRole("button", { name: "Close settings" }),
    );

    expect(confirm).toHaveBeenCalledWith("Discard your unsaved changes?");
    expect(view.router.state.location.pathname).toBe("/settings/profile");

    confirm.mockReturnValue(true);
    await userEvent.click(
      screen.getByRole("button", { name: "Close settings" }),
    );
    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe("/timeline"),
    );
    confirm.mockRestore();
  });

  it("keeps focus inside the dialog", async () => {
    await renderRoute("/settings/profile");
    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(dialog.contains(document.activeElement)).toBe(true),
    );
  });

  it("closes on Escape", async () => {
    const view = await renderRoute("/settings/security");
    await screen.findByRole("dialog");

    await userEvent.keyboard("{Escape}");

    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe("/timeline"),
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("carries the origin through the desktop redirect so close returns there", async () => {
    const original = window.matchMedia;
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: (query: string) => ({
        matches: query.includes("min-width: 1101px"),
        media: query,
        onchange: null,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        addListener: () => undefined,
        removeListener: () => undefined,
        dispatchEvent: () => false,
      }),
    });
    try {
      const view = await renderRoute("/timeline/moment-1?q=rain");
      await screen.findAllByText("A clear morning");

      await userEvent.click(screen.getByRole("button", { name: "Settings" }));
      await waitFor(() =>
        expect(view.router.state.location.pathname).toBe("/settings/profile"),
      );

      await userEvent.click(
        screen.getByRole("button", { name: "Close settings" }),
      );
      await waitFor(() => {
        expect(view.router.state.location.pathname).toBe("/timeline/moment-1");
        expect(view.router.state.location.search.q).toBe("rain");
      });
    } finally {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        value: original,
      });
    }
  });
});
