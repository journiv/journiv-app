import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import { ApiError } from "../../api/client/errors";
import type {
  EntryResponse,
  JournalResponse,
  MomentResponse,
  UserResponse,
} from "../../api/generated/types.gen";
import { queryKeys } from "../../api/query/keys";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";
import { browserTimeZone, wallTimePartsInZone } from "../../lib/datetime";
import type { DurableDraftDelta } from "./draftCanonical";
import { type EditorDraftV1, draftRepository } from "./draftRepository";

vi.mock("../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    journals: vi.fn(),
    moments: vi.fn(),
    moment: vi.fn(),
    momentMedia: vi.fn(),
    entry: vi.fn(),
    createMoment: vi.fn(),
    updateMoment: vi.fn(),
    createDraftEntry: vi.fn(),
    deleteMoment: vi.fn(),
    deleteEntry: vi.fn(),
    mediaFormats: vi.fn(),
  },
}));

const now = "2026-08-24T08:30:00Z"; // 10:30 in Europe/Vienna (UTC+2 in August)

const user: UserResponse = {
  id: "user-1",
  email: "d@example.com",
  name: "Date Tester",
  role: "user",
  is_active: true,
  created_at: now,
  updated_at: now,
};
const journal: JournalResponse = {
  id: "journal-1",
  user_id: user.id,
  title: "Daily notes",
  is_favorite: false,
  is_archived: false,
  entry_count: 1,
  total_words: 4,
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
    title: "A rainy morning",
    created_at: now,
    updated_at: now,
  },
};
const entry: EntryResponse = {
  id: "entry-1",
  user_id: user.id,
  journal_id: journal.id,
  moment_id: moment.id,
  title: "A rainy morning",
  content_plain_text: "Coffee.",
  content_delta: { ops: [{ insert: "Coffee.\n" }] },
  word_count: 1,
  created_at: now,
  updated_at: now,
};

const durable = (ops: unknown[]) => ({ ops }) as unknown as DurableDraftDelta;

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({
    version: 1,
    accessToken: "access",
    refreshToken: "refresh",
  });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([journal]);
  vi.mocked(api.moments).mockResolvedValue({ items: [moment] } as never);
  vi.mocked(api.moment).mockImplementation(async (id: string) => {
    if (id === moment.id) return moment;
    throw new ApiError("Moment not found", { status: 404 });
  });
  vi.mocked(api.entry).mockResolvedValue(entry);
  vi.mocked(api.momentMedia).mockResolvedValue([]);
  vi.mocked(api.mediaFormats).mockResolvedValue({});
  vi.mocked(api.updateMoment).mockResolvedValue(moment);
  vi.mocked(api.createMoment).mockResolvedValue({
    ...moment,
    id: "moment-new",
  });
});

async function renderRoute(path: string) {
  const history = createMemoryHistory({ initialEntries: [path] });
  const router = createAppRouter(history);
  const queryClient = createAppQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  queryClient.setQueryData(queryKeys.me, user);
  render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  );
  await router.load();
}

const dateTrigger = () =>
  screen.getByRole("button", { name: /change entry date and time/i });

// This integration test mounts the complete application router and editor.
// During the full CI suite that can take longer than Testing Library's 1 s
// default, even though the mocked requests resolve immediately.
const findDateTrigger = () =>
  screen.findByRole(
    "button",
    { name: /change entry date and time/i },
    { timeout: 10_000 },
  );

async function pickDay(
  user: ReturnType<typeof userEvent.setup>,
  label: string,
) {
  await user.click(dateTrigger());
  const calendar = await screen.findByRole("grid", {}, { timeout: 10_000 });
  // Limit the search to the calendar. The page has other controls and the
  // calendar can render neighbouring-month days with the same visible number.
  const day = within(calendar)
    .getAllByRole("button")
    .find((button) => button.textContent?.trim() === label);
  if (!day) throw new Error(`no day button "${label}"`);
  await user.click(day);
}

describe("editing an existing entry's date", () => {
  it("persists immediately, keeping the Moment's own timezone", async () => {
    const user = userEvent.setup();
    await renderRoute("/timeline/moment-1/edit");
    await findDateTrigger();

    await pickDay(user, "20");

    await waitFor(() => expect(api.updateMoment).toHaveBeenCalled());
    expect(api.updateMoment).toHaveBeenCalledWith("moment-1", {
      // 10:30 Vienna on the 20th — the wall-clock is preserved, the zone is the
      // Moment's own, not the test machine's.
      logged_at_utc: "2026-08-20T08:30:00.000Z",
      logged_timezone: "Europe/Vienna",
    });
    // An immediate metadata write does not make the form dirty.
    expect(screen.queryByText("Unsaved changes")).toBeNull();
  });
});

describe("choosing a date for a new entry", () => {
  it("carries the chosen date and the browser zone into createMoment", async () => {
    const user = userEvent.setup();
    await renderRoute("/timeline/new");
    const title = await screen.findByLabelText("Entry title");
    await user.type(title, "Backdated");

    // Typing creates the first local draft, which adds its id to the URL.
    // Let that one-time router transition settle before changing `draftAt`.
    // Subsequent draft writes reuse that id and cannot remount the editor.
    await screen.findByText(/Saved locally/, {}, { timeout: 4_000 });
    await pickDay(user, "20");
    // The date change is local for a new entry. Wait for React to commit it
    // before the immediate save below reads `draftAt` in its mutation.
    await waitFor(() =>
      expect(dateTrigger().textContent).toMatch(/\b20,\s*\d{4}/),
    );
    await user.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() => expect(api.createMoment).toHaveBeenCalled());
    const body = vi.mocked(api.createMoment).mock.calls[0][0];
    expect(body.logged_timezone).toBe(browserTimeZone());
    expect(
      wallTimePartsInZone(body.logged_at_utc as string, browserTimeZone()).day,
    ).toBe(20);
  });
});

describe("recovering a backdated new-entry draft", () => {
  const localDraftId = "aaaaaaaa-bbbb-4ccc-8ddd-2222aaaa2222";

  it("restores the picked date/time from the local draft", async () => {
    const record: EditorDraftV1 = {
      key: `user-1:new:${localDraftId}`,
      userId: "user-1",
      localDraftId,
      journalId: "journal-1",
      title: "Half-written",
      loggedAtUtc: "2026-01-15T19:00:00.000Z", // 20:00 Europe/Vienna
      loggedTimezone: "Europe/Vienna",
      contentDelta: durable([{ insert: "Backdated thoughts\n" }]),
      modifiedAt: now,
      dirty: true,
    };
    await draftRepository.write(record);

    const user = userEvent.setup();
    await renderRoute(`/journals/journal-1/new?draft=${localDraftId}`);
    await user.click(await screen.findByRole("button", { name: "Recover" }));

    await waitFor(() =>
      expect(dateTrigger().textContent).toContain("January 15, 2026"),
    );
    expect(dateTrigger().textContent).toMatch(/8:00\s?PM/i);
  });
});
