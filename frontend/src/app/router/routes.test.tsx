import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createAppRouter } from ".";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import { ApiError } from "../../api/client/errors";
import { Toaster } from "../../components/ui/toast";
import type {
  EntryResponse,
  InstanceConfigResponse,
  JournalResponse,
  MomentPageResponse,
  MomentResponse,
  PromptResponse,
  UserResponse,
} from "../../api/generated/types.gen";
import { createAppQueryClient } from "../queryClient";

vi.mock("../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    journals: vi.fn(),
    moods: vi.fn(),
    moments: vi.fn(),
    moment: vi.fn(),
    momentCalendar: vi.fn(),
    mediaLibrary: vi.fn(),
    entry: vi.fn(),
    deleteEntry: vi.fn(),
    downloadEntryPdf: vi.fn(),
    tags: vi.fn(),
    createMoment: vi.fn(),
    updateMoment: vi.fn(),
    login: vi.fn(),
    instanceConfig: vi.fn(),
    refresh: vi.fn(),
    writingStreak: vi.fn(),
    writingPatterns: vi.fn(),
    productivityMetrics: vi.fn(),
    journalAnalytics: vi.fn(),
    moodStatistics: vi.fn(),
    moodStreak: vi.fn(),
    prompt: vi.fn(),
  },
}));

const now = "2026-08-24T08:30:00Z";
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
const user: UserResponse = {
  id: "user-1",
  email: "phase-b@example.com",
  name: "Phase B",
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
const otherJournal: JournalResponse = {
  ...journal,
  id: "journal-2",
  title: "Travel notes",
  entry_count: 0,
  total_words: 0,
};
const momentEntry: NonNullable<MomentResponse["entry"]> = {
  id: "entry-1",
  journal_id: journal.id,
  moment_id: "moment-1",
  title: "A rainy morning",
  content_plain_text: "Coffee while the rain moved past the windows.",
  created_at: now,
  updated_at: now,
};
const moment: MomentResponse = {
  id: "moment-1",
  user_id: user.id,
  logged_at_utc: now,
  logged_date_tz: "2026-08-24",
  logged_timezone: "Europe/Vienna",
  entry: momentEntry,
};
const page: MomentPageResponse = { items: [moment] };
const entry: EntryResponse = {
  id: "entry-1",
  user_id: user.id,
  journal_id: journal.id,
  moment_id: moment.id,
  title: "A rainy morning",
  content_plain_text: "Coffee while the rain moved past the windows.",
  content_delta: {
    ops: [{ insert: "Coffee while the rain moved past the windows.\n" }],
  },
  word_count: 8,
  created_at: now,
  updated_at: now,
};
const prompt: PromptResponse = {
  id: "11111111-1111-4111-8111-111111111111",
  text: "What made this rainy morning memorable?",
  category: "reflection",
  difficulty_level: 1,
  estimated_time_minutes: 5,
  is_active: true,
  usage_count: 0,
  answered_count: 0,
  created_at: now,
  updated_at: now,
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
  vi.mocked(api.instanceConfig).mockResolvedValue(instanceConfig);
  vi.mocked(api.journals).mockResolvedValue([journal, otherJournal]);
  vi.mocked(api.moods).mockResolvedValue([]);
  vi.mocked(api.moments).mockResolvedValue(page);
  vi.mocked(api.moment).mockResolvedValue(moment);
  vi.mocked(api.momentCalendar).mockResolvedValue([
    {
      logged_date_tz: "2026-08-24",
      primary_mood_id: null,
      moment_count: 1,
      thumbnail_url: null,
    },
  ]);
  vi.mocked(api.mediaLibrary).mockResolvedValue({ items: [] });
  vi.mocked(api.entry).mockResolvedValue(entry);
  vi.mocked(api.deleteEntry).mockResolvedValue(undefined);
  vi.mocked(api.downloadEntryPdf).mockResolvedValue({
    blob: new Blob(["pdf"], { type: "application/pdf" }),
    filename: "rainy-morning.pdf",
  });
  vi.mocked(api.tags).mockResolvedValue([]);
  vi.mocked(api.createMoment).mockResolvedValue({
    ...moment,
    id: "moment-new",
    entry: {
      id: "entry-new",
      journal_id: journal.id,
      moment_id: "moment-new",
      title: "Phone checkpoint",
      content_plain_text: "Typed from Quill",
      created_at: now,
      updated_at: now,
    },
  });
  vi.mocked(api.updateMoment).mockResolvedValue(moment);
  vi.mocked(api.writingStreak).mockResolvedValue({
    current_streak: 3,
    longest_streak: 9,
    total_entries: 40,
    total_words: 8000,
    average_words_per_entry: 200,
  });
  vi.mocked(api.writingPatterns).mockResolvedValue({
    period_days: 30,
    entries_by_day: [],
    mood_patterns: [],
    top_tags: [],
  });
  vi.mocked(api.productivityMetrics).mockResolvedValue({
    current_month_entries: 4,
    current_month_words: 800,
    entry_growth_percentage: 0,
    average_daily_entries: 0.5,
    average_words_per_day: 40,
  });
  vi.mocked(api.journalAnalytics).mockResolvedValue({ journals: [] });
  vi.mocked(api.moodStatistics).mockResolvedValue({
    total_logs: 0,
    date_range: { start_date: "2026-07-25", end_date: "2026-08-24" },
    mood_distribution: {},
    mood_counts: [],
    daily_trends: [],
  });
  vi.mocked(api.moodStreak).mockResolvedValue({
    current_streak: 0,
    total_days_logged: 0,
  });
  vi.mocked(api.prompt).mockResolvedValue(prompt);
});

async function renderRoute(path: string) {
  const history = createMemoryHistory({ initialEntries: [path] });
  const router = createAppRouter(history);
  const queryClient = createAppQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  // StrictMode, like the real app (src/main.tsx). React double-invokes effects
  // in development, and a mount/teardown/remount cycle has already deadlocked
  // one effect here — the editor sat on a skeleton forever because a read was
  // cancelled by the first cleanup and skipped by a guard on the second run.
  const view = render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <Toaster>
          <RouterProvider router={router} />
        </Toaster>
      </QueryClientProvider>
    </StrictMode>,
  );
  await router.load();
  return { ...view, router };
}

async function openEntryDeleteMenu() {
  await userEvent.click(
    await screen.findByRole("button", { name: "Entry actions" }),
  );
  await userEvent.click(await screen.findByText("Delete entry…"));
}

// Restores registered by stubPdfDownloadDom(); run after every test so a stub
// never leaks into the next one (vi.clearAllMocks in beforeEach clears call
// data, not spy installation, and jsdom has no URL.createObjectURL to begin
// with).
const domRestores: Array<() => void> = [];
afterEach(() => {
  for (const restore of domRestores.splice(0)) restore();
});

/**
 * Stub the DOM plumbing an anchor-click download reaches for, and register the
 * teardown. Returns the spies so a test can assert on them.
 */
function stubPdfDownloadDom() {
  const createObjectURL = vi.fn(() => "blob:entry-pdf");
  const revokeObjectURL = vi.fn();
  const nativeObjectUrl = Object.getOwnPropertyDescriptor(
    URL,
    "createObjectURL",
  );
  const nativeRevokeObjectUrl = Object.getOwnPropertyDescriptor(
    URL,
    "revokeObjectURL",
  );
  Object.defineProperties(URL, {
    createObjectURL: {
      configurable: true,
      writable: true,
      value: createObjectURL,
    },
    revokeObjectURL: {
      configurable: true,
      writable: true,
      value: revokeObjectURL,
    },
  });
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => undefined);

  domRestores.push(() => {
    click.mockRestore();
    if (nativeObjectUrl)
      Object.defineProperty(URL, "createObjectURL", nativeObjectUrl);
    else Reflect.deleteProperty(URL, "createObjectURL");
    if (nativeRevokeObjectUrl)
      Object.defineProperty(URL, "revokeObjectURL", nativeRevokeObjectUrl);
    else Reflect.deleteProperty(URL, "revokeObjectURL");
  });

  return { createObjectURL, revokeObjectURL, click };
}

describe("Phase B routes", () => {
  it("shows a read-only prompt attribution for a prompted Moment", async () => {
    vi.mocked(api.moment).mockResolvedValue({
      ...moment,
      prompt_id: prompt.id,
    });
    await renderRoute("/timeline/moment-1");

    const banner = await screen.findByRole("complementary", {
      name: "Written from a prompt",
    });
    expect(banner.textContent).toContain(prompt.text);
    expect(api.prompt).toHaveBeenCalledWith(prompt.id);
    expect(screen.queryByRole("button", { name: "Remove prompt" })).toBeNull();
  });

  it("renders one reader pane on a deep link and returns with search intact", async () => {
    const view = await renderRoute("/timeline/moment-1?q=rain");

    expect(
      (await screen.findAllByText("A rainy morning")).length,
    ).toBeGreaterThan(0);
    expect(
      view.container.querySelectorAll("section.jv-shell__page"),
    ).toHaveLength(1);
    expect(
      view.container
        .querySelector(".jv-shell")
        ?.classList.contains("is-detail"),
    ).toBe(true);

    await userEvent.click(await screen.findByRole("button", { name: "Back" }));
    await waitFor(() => {
      expect(view.router.state.location.pathname).toBe("/timeline");
      expect(view.router.state.location.search.q).toBe("rain");
    });
  });

  it("cancels entry deletion, then returns to the same scoped list when the Moment is pruned", async () => {
    vi.mocked(api.moment)
      .mockResolvedValueOnce(moment)
      .mockRejectedValueOnce(new ApiError("Moment not found", { status: 404 }));
    const view = await renderRoute("/timeline/moment-1?q=rain&tag=tag-1");

    await openEntryDeleteMenu();
    let dialog = screen.getByRole("alertdialog");
    expect(
      within(dialog).getByRole("heading", {
        name: "Delete “A rainy morning”?",
      }),
    ).toBeTruthy();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Cancel" }),
    );
    expect(api.deleteEntry).not.toHaveBeenCalled();

    await openEntryDeleteMenu();
    dialog = screen.getByRole("alertdialog");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Delete entry" }),
    );

    await waitFor(() =>
      expect(api.deleteEntry).toHaveBeenCalledWith("entry-1"),
    );
    await waitFor(() => {
      expect(view.router.state.location.pathname).toBe("/timeline");
      expect(view.router.state.location.search.q).toBe("rain");
      expect(view.router.state.location.search.tag).toBe("tag-1");
    });
  });

  it("keeps a surviving Moment open as a quick log after deleting its writing", async () => {
    const quickLog: MomentResponse = {
      ...moment,
      entry: null,
      is_pinned: true,
    };
    vi.mocked(api.moment)
      .mockResolvedValueOnce(moment)
      .mockResolvedValueOnce(quickLog);
    const view = await renderRoute("/timeline/moment-1?q=rain");

    await openEntryDeleteMenu();
    await userEvent.click(
      within(screen.getByRole("alertdialog")).getByRole("button", {
        name: "Delete entry",
      }),
    );

    expect(await screen.findByRole("button", { name: "Write" })).toBeTruthy();
    expect(view.router.state.location.pathname).toBe("/timeline/moment-1");
    expect(screen.queryByRole("button", { name: "Entry actions" })).toBeNull();
    expect(api.moment).toHaveBeenCalledTimes(2);
  });

  it("keeps the confirmation open and shows a human error when deletion fails", async () => {
    vi.mocked(api.deleteEntry).mockRejectedValueOnce(new Error("offline"));
    const view = await renderRoute("/timeline/moment-1");

    await openEntryDeleteMenu();
    const dialog = screen.getByRole("alertdialog");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Delete entry" }),
    );

    expect(
      await within(dialog).findByText(
        "The entry couldn’t be deleted. Check your connection and try again.",
      ),
    ).toBeTruthy();
    expect(view.router.state.location.pathname).toBe("/timeline/moment-1");
    expect(screen.getByRole("alertdialog")).toBeTruthy();
  });

  it("downloads an entry PDF from the reader action menu", async () => {
    const { createObjectURL, click } = stubPdfDownloadDom();

    await renderRoute("/timeline/moment-1");
    await userEvent.click(
      await screen.findByRole("button", { name: "Entry actions" }),
    );
    expect(
      await screen.findByRole("menuitem", { name: "Download PDF" }),
    ).toBeTruthy();
    await userEvent.click(
      screen.getByRole("menuitem", { name: "Download PDF" }),
    );

    await waitFor(() =>
      expect(api.downloadEntryPdf).toHaveBeenCalledWith("entry-1"),
    );
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(click).toHaveBeenCalledTimes(1);
    expect((click.mock.instances[0] as HTMLAnchorElement).download).toBe(
      "rainy-morning.pdf",
    );
  });

  it("shows a transient toast when a PDF download fails", async () => {
    vi.mocked(api.downloadEntryPdf).mockRejectedValueOnce(new Error("offline"));
    await renderRoute("/timeline/moment-1");

    await userEvent.click(
      await screen.findByRole("button", { name: "Entry actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Download PDF" }),
    );

    // A high-priority toast announces through a visually-hidden assertive
    // live region (Base UI keeps the visible surface out of the a11y tree
    // until focused).
    expect(
      within(await screen.findByRole("alert")).getByText(
        "Couldn’t download PDF. Try again.",
      ),
    ).toBeTruthy();
  });

  it("retries a failed PDF download from the toast action", async () => {
    const { click } = stubPdfDownloadDom();
    let resolveRetry: (() => void) | undefined;
    const pendingRetry = new Promise<void>((resolve) => {
      resolveRetry = resolve;
    });
    vi.mocked(api.downloadEntryPdf)
      .mockRejectedValueOnce(new Error("offline"))
      .mockImplementationOnce(async () => {
        await pendingRetry;
        return {
          blob: new Blob(["pdf"], { type: "application/pdf" }),
          filename: "rainy-morning.pdf",
        };
      });

    await renderRoute("/timeline/moment-1");
    await userEvent.click(
      await screen.findByRole("button", { name: "Entry actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Download PDF" }),
    );

    // The visible surface of a high-priority toast is aria-hidden until
    // focused, so reach the action with `hidden`.
    const toast = await screen.findByRole("alertdialog", { hidden: true });
    await userEvent.click(
      within(toast).getByRole("button", { name: "Retry", hidden: true }),
    );
    await userEvent.click(
      within(toast).getByRole("button", { name: "Retry", hidden: true }),
    );

    expect(api.downloadEntryPdf).toHaveBeenCalledTimes(2);
    if (!resolveRetry) throw new Error("The retry request did not start.");
    resolveRetry();

    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(click).toHaveBeenCalledTimes(1);
  });

  it("debounces search into the URL and query policy", async () => {
    const view = await renderRoute("/timeline");
    const input = await screen.findByRole("textbox", {
      name: /^Search/,
    });

    await userEvent.type(input, "coffee");

    await waitFor(
      () => expect(view.router.state.location.search.q).toBe("coffee"),
      { timeout: 1_500 },
    );
    await waitFor(() =>
      expect(vi.mocked(api.moments)).toHaveBeenCalledWith(
        expect.objectContaining({ search: "coffee" }),
      ),
    );
  });

  it("keeps New Entry as a journal-scoped first-class detail route", async () => {
    const view = await renderRoute("/journals/journal-1/new?q=idea");

    expect(await screen.findByLabelText("Entry title")).toBeTruthy();
    expect(await screen.findByLabelText("Entry body")).toBeTruthy();
    expect(
      view.container
        .querySelector(".jv-shell")
        ?.classList.contains("is-detail"),
    ).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => {
      expect(view.router.state.location.pathname).toBe("/journals/journal-1");
      expect(view.router.state.location.search.q).toBe("idea");
    });
  });

  it("creates a new Moment with an inline full document Delta", async () => {
    const view = await renderRoute("/journals/journal-1/new?q=idea");
    const title = await screen.findByLabelText("Entry title");
    const body = await screen.findByLabelText("Entry body");

    await userEvent.type(title, "Phone checkpoint");
    await userEvent.type(body, "Typed from Quill");
    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() =>
      expect(vi.mocked(api.createMoment)).toHaveBeenCalledWith(
        expect.objectContaining({
          entry: {
            title: "Phone checkpoint",
            journal_id: journal.id,
            content_delta: {
              ops: [
                expect.objectContaining({
                  insert: expect.stringMatching(/^Typed from Quill\n+$/),
                }),
              ],
            },
          },
          logged_at_utc: expect.any(String),
          logged_timezone: expect.any(String),
        }),
      ),
    );
    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe(
        "/journals/journal-1/moment-new",
      ),
    );
  });

  it("navigates to the selected Journal after cross-journal creation", async () => {
    vi.mocked(api.createMoment).mockResolvedValueOnce({
      ...moment,
      id: "moment-in-journal-2",
      entry: {
        ...momentEntry,
        id: "entry-in-journal-2",
        moment_id: "moment-in-journal-2",
        journal_id: otherJournal.id,
      },
    });
    const view = await renderRoute("/journals/journal-1/new?q=travel");
    await userEvent.selectOptions(
      await screen.findByLabelText("Journal"),
      otherJournal.id,
    );
    await userEvent.type(
      screen.getByLabelText("Entry title"),
      "Moved while new",
    );
    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() =>
      expect(vi.mocked(api.createMoment)).toHaveBeenCalledWith(
        expect.objectContaining({
          entry: expect.objectContaining({ journal_id: otherJournal.id }),
        }),
      ),
    );
    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe(
        "/journals/journal-2/moment-in-journal-2",
      ),
    );
    expect(view.router.state.location.search.q).toBe("travel");
  });

  it("loads an edit deep link and updates through Moment entry_update", async () => {
    const view = await renderRoute("/timeline/moment-1/edit?q=rain");
    const title = await screen.findByLabelText("Entry title");
    await userEvent.clear(title);
    await userEvent.type(title, "Edited title");
    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() =>
      expect(vi.mocked(api.updateMoment)).toHaveBeenCalledWith("moment-1", {
        entry_update: {
          title: "Edited title",
          journal_id: journal.id,
          content_delta: entry.content_delta,
          // Done finalises: an entry that was still a draft leaves the drafts
          // pile and becomes visible in the Timeline.
          is_draft: false,
          // The version this editor opened on, so the backend can refuse the
          // save rather than overwrite an edit made on another device.
          expected_updated_at: entry.updated_at,
        },
      }),
    );
    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe("/timeline/moment-1"),
    );
  });

  it("seeds a quick-logged note into the body and clears it on the first save", async () => {
    const noteMoment: MomentResponse = {
      id: "moment-note",
      user_id: user.id,
      logged_at_utc: now,
      logged_date_tz: "2026-08-24",
      logged_timezone: "Europe/Vienna",
      note: "Overheard a good line on the train",
    };
    vi.mocked(api.moment).mockResolvedValue(noteMoment);
    vi.mocked(api.updateMoment).mockResolvedValue({
      ...noteMoment,
      note: null,
      entry: {
        id: "entry-note",
        journal_id: journal.id,
        moment_id: "moment-note",
        title: null,
        content_plain_text: "Overheard a good line on the train",
        created_at: now,
        updated_at: now,
      },
    });

    const view = await renderRoute("/timeline/moment-note/edit?seedNote=true");

    // The note is now editable body text, not a separate metadata line.
    expect(
      await screen.findByText(/Overheard a good line on the train/),
    ).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() =>
      expect(vi.mocked(api.updateMoment)).toHaveBeenCalledWith(
        "moment-note",
        expect.objectContaining({
          entry_create: expect.objectContaining({ journal_id: journal.id }),
          // Same request that creates the entry drops the now-duplicated note.
          note: null,
        }),
      ),
    );
    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe("/timeline/moment-note"),
    );
  });

  it("keeps Journal context after saving an edit deep link", async () => {
    const view = await renderRoute("/journals/journal-1/moment-1/edit?q=rain");
    const title = await screen.findByLabelText("Entry title");
    await userEvent.clear(title);
    await userEvent.type(title, "Journal edit");
    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe(
        "/journals/journal-1/moment-1",
      ),
    );
    expect(view.router.state.location.search.q).toBe("rain");
  });

  it("navigates to the destination Journal after moving an existing entry", async () => {
    vi.mocked(api.updateMoment).mockResolvedValueOnce({
      ...moment,
      entry: { ...momentEntry, journal_id: otherJournal.id },
    });
    const view = await renderRoute("/journals/journal-1/moment-1/edit?q=move");
    await userEvent.selectOptions(
      await screen.findByLabelText("Journal"),
      otherJournal.id,
    );
    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() =>
      expect(vi.mocked(api.updateMoment)).toHaveBeenCalledWith(
        "moment-1",
        expect.objectContaining({
          entry_update: expect.objectContaining({
            journal_id: otherJournal.id,
          }),
        }),
      ),
    );
    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe(
        "/journals/journal-2/moment-1",
      ),
    );
    expect(view.router.state.location.search.q).toBe("move");
  });

  it("shows plain text for unsupported content without initializing Quill", async () => {
    vi.mocked(api.entry).mockResolvedValueOnce({
      ...entry,
      content_plain_text: "Photo from the server fallback",
      content_delta: {
        ops: [{ insert: { image: "media-id" } }, { insert: "\n" }],
      },
    });
    await renderRoute("/timeline/moment-1");

    expect(
      await screen.findByText("Photo from the server fallback"),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Entry content")).toBeNull();
  });

  it("blocks unsupported content from editing or submission", async () => {
    const unsupported = {
      ...entry,
      content_delta: {
        ops: [
          { insert: "Legacy", attributes: { color: "#ff0000" } },
          { insert: "\n" },
        ],
      },
    };
    vi.mocked(api.entry).mockResolvedValueOnce(unsupported);
    const view = await renderRoute("/timeline/moment-1/edit?q=legacy");

    expect(
      await screen.findByText(/cannot edit without losing data/i),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Entry body")).toBeNull();
    expect(screen.queryByRole("button", { name: "Done" })).toBeNull();
    expect(api.updateMoment).not.toHaveBeenCalled();

    await userEvent.click(
      screen.getByRole("button", { name: "Back without changes" }),
    );
    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe("/timeline/moment-1"),
    );
    expect(view.router.state.location.search.q).toBe("legacy");
    expect(api.updateMoment).not.toHaveBeenCalled();
  });

  it("saves the complete document with Command/Ctrl+S", async () => {
    const view = await renderRoute("/journals/journal-1/new");
    await userEvent.type(
      await screen.findByLabelText("Entry title"),
      "Shortcut entry",
    );
    await userEvent.type(
      await screen.findByLabelText("Entry body"),
      "Full document",
    );
    window.dispatchEvent(
      new KeyboardEvent("keydown", {
        bubbles: true,
        cancelable: true,
        ctrlKey: true,
        key: "s",
      }),
    );

    await waitFor(() => expect(api.createMoment).toHaveBeenCalledOnce());
    expect(vi.mocked(api.createMoment).mock.calls[0]?.[0].entry).toEqual(
      expect.objectContaining({
        title: "Shortcut entry",
        content_delta: {
          ops: [
            expect.objectContaining({
              insert: expect.stringMatching(/^Full document\n+$/),
            }),
          ],
        },
      }),
    );
    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe(
        "/journals/journal-1/moment-new",
      ),
    );
  });

  it("creates an Entry inline for a Moment that has no narrative", async () => {
    const emptyMoment = { ...moment, entry: null };
    const savedMoment = { ...moment, entry: moment.entry };
    vi.mocked(api.moment).mockResolvedValueOnce(emptyMoment);
    vi.mocked(api.updateMoment).mockResolvedValueOnce(savedMoment);
    await renderRoute("/timeline/moment-1/edit");
    await userEvent.type(
      await screen.findByLabelText("Entry title"),
      "Added later",
    );
    await userEvent.selectOptions(screen.getByLabelText("Journal"), journal.id);
    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() =>
      expect(vi.mocked(api.updateMoment)).toHaveBeenCalledWith(
        "moment-1",
        expect.objectContaining({
          entry_create: expect.objectContaining({
            title: "Added later",
            journal_id: journal.id,
          }),
        }),
      ),
    );
  });

  it("keeps unsaved input mounted after a save failure", async () => {
    vi.mocked(api.createMoment).mockRejectedValueOnce(
      new Error("Network unavailable"),
    );
    await renderRoute("/journals/journal-1/new");
    const title = await screen.findByLabelText("Entry title");
    await userEvent.type(title, "Still here");
    await userEvent.type(
      await screen.findByLabelText("Entry body"),
      "Unsaved words",
    );
    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Network unavailable",
    );
    expect((title as HTMLInputElement).value).toBe("Still here");
    expect(screen.getByLabelText("Entry body").textContent).toContain(
      "Unsaved words",
    );
  });

  it.each(["Authentication expired", "Forbidden", "Validation failed"])(
    "preserves title and Delta after %s",
    async (message) => {
      vi.mocked(api.createMoment).mockRejectedValueOnce(new Error(message));
      await renderRoute("/journals/journal-1/new");
      const title = await screen.findByLabelText("Entry title");
      const body = await screen.findByLabelText("Entry body");
      await userEvent.type(title, "Retry title");
      await userEvent.type(body, "Retry body");
      await userEvent.click(screen.getByRole("button", { name: "Done" }));

      expect((await screen.findByRole("alert")).textContent).toContain(message);
      expect((title as HTMLInputElement).value).toBe("Retry title");
      expect(body.textContent).toContain("Retry body");
    },
  );

  it("requires confirmation before Cancel discards dirty work", async () => {
    const view = await renderRoute("/journals/journal-1/new?q=draft");
    await userEvent.type(
      await screen.findByLabelText("Entry title"),
      "Do not lose",
    );
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(view.router.state.location.pathname).toBe("/journals/journal-1/new");
    // Cancel removes the local copy and cleans up the draft this session made,
    // so it must not borrow the wording of simply navigating away — that one is
    // true, this one would be a lie told at the moment it matters.
    expect(confirm).toHaveBeenCalledWith(
      "Discard this entry? The writing will not be kept on this device either.",
    );

    confirm.mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe("/journals/journal-1"),
    );
    confirm.mockRestore();
  });

  it("clears the temporary session and returns to login on logout", async () => {
    const view = await renderRoute("/timeline");
    await screen.findByText("phase-b@example.com");

    await userEvent.click(screen.getByRole("button", { name: "Log out" }));

    await screen.findByRole("heading", { name: "Welcome back" });
    expect(sessionStore.read()).toBeNull();
    expect(view.router.state.location.pathname).toBe("/login");
  });

  it("resolves /insights to the Insights workspace with default tab and period", async () => {
    const view = await renderRoute("/insights");

    expect(
      await screen.findByRole("heading", { name: "Insights", level: 1 }),
    ).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Overview" })).toBeTruthy();
    await waitFor(() =>
      expect(vi.mocked(api.writingPatterns)).toHaveBeenCalledWith(30),
    );
    expect(view.router.state.location.search.tab).toBe("overview");
    expect(view.router.state.location.search.period).toBe(30);
  });

  it("renders the calendar in the list pane for ?view=calendar", async () => {
    await renderRoute("/timeline?view=calendar&month=2026-08");

    expect(
      await screen.findByRole("heading", { name: "Calendar" }),
    ).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "All journals" })).toBeNull();
    await waitFor(() =>
      expect(vi.mocked(api.momentCalendar)).toHaveBeenCalled(),
    );
  });

  it("keeps the calendar view, its month and selected day mounted beside the reader and through Back", async () => {
    const view = await renderRoute(
      "/timeline/moment-1?view=calendar&month=2026-07&date=2026-07-15&q=rain",
    );

    expect(
      await screen.findByRole("heading", { name: "Calendar" }),
    ).toBeTruthy();
    expect(
      (await screen.findAllByText("A rainy morning")).length,
    ).toBeGreaterThan(0);
    expect(
      view.container.querySelectorAll("section.jv-shell__page"),
    ).toHaveLength(1);

    await userEvent.click(await screen.findByRole("button", { name: "Back" }));
    await waitFor(() => {
      expect(view.router.state.location.pathname).toBe("/timeline");
      expect(view.router.state.location.search.view).toBe("calendar");
      expect(view.router.state.location.search.month).toBe("2026-07");
      expect(view.router.state.location.search.date).toBe("2026-07-15");
      expect(view.router.state.location.search.q).toBe("rain");
    });
  });
});
