import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import type {
  EntryResponse,
  IntegrationStatusResponse,
  JournalResponse,
  MomentResponse,
  UserResponse,
} from "../../api/generated/types.gen";
import { queryKeys } from "../../api/query/keys";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";

vi.mock("../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    journals: vi.fn(),
    moments: vi.fn(),
    moment: vi.fn(),
    momentMedia: vi.fn(),
    entry: vi.fn(),
    mediaFormats: vi.fn(),
    createMoment: vi.fn(),
    updateMoment: vi.fn(),
    createDraftEntry: vi.fn(),
    instanceConfig: vi.fn(),
    integrationStatus: vi.fn(),
    immichAssets: vi.fn(),
  },
}));

vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }: { count: number }) => ({
    getTotalSize: () => count * 140,
    getVirtualItems: () =>
      Array.from({ length: count }, (_, index) => ({
        key: index,
        index,
        start: index * 140,
        size: 140,
      })),
    measure: () => {},
    measureElement: () => {},
  }),
}));

const now = "2026-08-24T08:30:00Z";
const user: UserResponse = {
  id: "user-1",
  email: "w@example.com",
  name: "W",
  role: "user",
  is_active: true,
  created_at: now,
  updated_at: now,
};
const journal: JournalResponse = {
  id: "journal-1",
  user_id: user.id,
  title: "Daily",
  is_favorite: false,
  is_archived: false,
  entry_count: 1,
  total_words: 1,
  created_at: now,
  updated_at: now,
};
const moment: MomentResponse = {
  id: "moment-1",
  user_id: user.id,
  logged_at_utc: now,
  logged_date_tz: "2026-08-24",
  logged_timezone: "Europe/Vienna",
  entry: {
    id: "entry-1",
    journal_id: journal.id,
    moment_id: "moment-1",
    title: "Morning",
    created_at: now,
    updated_at: now,
  },
};
const entry: EntryResponse = {
  id: "entry-1",
  user_id: user.id,
  journal_id: journal.id,
  moment_id: moment.id,
  title: "Morning",
  content_plain_text: "Coffee.",
  content_delta: { ops: [{ insert: "Coffee.\n" }] },
  word_count: 1,
  created_at: now,
  updated_at: now,
};

const connected: IntegrationStatusResponse = {
  provider: "immich",
  status: "connected",
  is_active: true,
  import_mode: "link_only",
};

function baseConfig(immich: boolean) {
  return {
    import_export_max_file_size_mb: 100,
    max_file_size_mb: 50,
    disable_signup: false,
    oidc_enabled: false,
    oidc_only: false,
    ...(immich ? { immich_base_url: "https://photos.example.com" } : {}),
    plus: { available: false, tier: "member", upgrade_url: "x" },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([journal]);
  vi.mocked(api.moments).mockResolvedValue({ items: [moment] } as never);
  vi.mocked(api.moment).mockResolvedValue(moment);
  vi.mocked(api.entry).mockResolvedValue(entry);
  vi.mocked(api.momentMedia).mockResolvedValue([]);
  vi.mocked(api.mediaFormats).mockResolvedValue({});
  vi.mocked(api.instanceConfig).mockResolvedValue(baseConfig(true));
  vi.mocked(api.integrationStatus).mockResolvedValue(connected);
  vi.mocked(api.immichAssets).mockResolvedValue({
    assets: [
      {
        id: "asset-a",
        type: "IMAGE",
        title: "a.jpg",
        taken_at: now,
        thumb_url: "/thumb/a",
        original_url: "/orig/a",
      },
    ],
    page: 1,
    limit: 100,
    total: 1,
    has_more: false,
  });
});

async function openEditor() {
  const history = createMemoryHistory({
    initialEntries: ["/timeline/moment-1/edit"],
  });
  const router = createAppRouter(history);
  const queryClient = createAppQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  queryClient.setQueryData(queryKeys.me, user);
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
  return screen.findByRole(
    "button",
    { name: /add photo, video or audio/i },
    { timeout: 10_000 },
  );
}

describe("EntryEditorPage · Immich media", () => {
  it("opens the source-chooser dialog when Immich is connected", async () => {
    const trigger = await openEditor();
    await userEvent.click(trigger);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("tab", { name: "Immich" })).toBeTruthy();
    expect(
      within(dialog).getByRole("tab", { name: "This device" }),
    ).toBeTruthy();
    expect(
      await within(dialog).findByRole("checkbox", { name: "a.jpg" }),
    ).toBeTruthy();
  });

  it("goes straight to the OS file picker when no Immich server is configured", async () => {
    vi.mocked(api.instanceConfig).mockResolvedValue(baseConfig(false));
    const clickSpy = vi.spyOn(HTMLInputElement.prototype, "click");
    const trigger = await openEditor();
    await userEvent.click(trigger);

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(clickSpy).toHaveBeenCalled();
    clickSpy.mockRestore();
  });

  it("routes the dialog's device tab back to the file input", async () => {
    const clickSpy = vi.spyOn(HTMLInputElement.prototype, "click");
    const trigger = await openEditor();
    await userEvent.click(trigger);
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(
      within(dialog).getByRole("tab", { name: "This device" }),
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Choose files" }),
    );

    expect(clickSpy).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    clickSpy.mockRestore();
  });
});
