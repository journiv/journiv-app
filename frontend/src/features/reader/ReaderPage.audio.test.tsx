import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import type {
  JournalResponse,
  MomentMediaResponse,
  MomentResponse,
  UserResponse,
} from "../../api/generated/types.gen";
import { queryKeys } from "../../api/query/keys";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";

/**
 * Deleting an audio clip from the reader's PageBar menu
 * (docs/features/reader.md). The clips offered are the ones the prose does not
 * embed, which is what makes a delete offered here safe for the document.
 */
vi.mock("../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    journals: vi.fn(),
    moods: vi.fn(),
    moments: vi.fn(),
    moment: vi.fn(),
    entry: vi.fn(),
    momentMedia: vi.fn(),
    deleteMedia: vi.fn(),
  },
}));

const now = "2026-09-12T09:00:00Z";
const user: UserResponse = {
  id: "user-1",
  email: "reader@example.com",
  name: "Reader",
  role: "user",
  is_active: true,
  created_at: now,
  updated_at: now,
};
const journal: JournalResponse = {
  id: "journal-1",
  user_id: user.id,
  title: "Harbour",
  is_favorite: false,
  is_archived: false,
  entry_count: 1,
  total_words: 4,
  created_at: now,
  updated_at: now,
};
const entry = {
  id: "entry-1",
  journal_id: journal.id,
  moment_id: "moment-1",
  title: "Harbour morning",
  content_plain_text: "The ferries were late.",
  created_at: now,
  updated_at: now,
};
const moment = {
  id: "moment-1",
  user_id: user.id,
  logged_at_utc: now,
  logged_date_tz: "2026-09-12",
  logged_timezone: "Europe/Vienna",
  media_count: 1,
  entry,
} as MomentResponse;
/** The reported case: a clip logged on its own, with nothing written. */
const mediaOnly = { ...moment, entry: null } as MomentResponse;
/**
 * A processed clip: peaks present, so the gallery draws the waveform player and
 * the tests can locate it by its seek slider rather than a raw `<audio>`.
 */
const recording = (over: Partial<MomentMediaResponse> = {}) =>
  ({
    id: "audio-1",
    created_at: now,
    media_type: "audio",
    mime_type: "audio/mp4",
    upload_status: "completed",
    duration: 42,
    waveform_peaks: Array.from({ length: 400 }, (_, index) => index % 100),
    signed_url: "/api/v1/media/audio-1/signed?sig=abc",
    moment_id: moment.id,
    ...over,
  }) as MomentMediaResponse;

/**
 * The entry-content response. `delta` is what decides whether a clip is on
 * offer, so each test states the document it is reading against.
 */
const prose = (delta: unknown) =>
  ({
    ...entry,
    user_id: user.id,
    content_delta: delta,
    word_count: 4,
  }) as never;

let deleted = false;

beforeEach(() => {
  vi.clearAllMocks();
  deleted = false;
  sessionStorage.clear();
  sessionStore.adopt({ accessToken: "a", userId: user.id });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([journal]);
  vi.mocked(api.moods).mockResolvedValue([]);
  vi.mocked(api.moments).mockResolvedValue({ items: [moment] } as never);
  vi.mocked(api.moment).mockImplementation(async () =>
    deleted ? { ...moment, media_count: 0 } : moment,
  );
  vi.mocked(api.entry).mockResolvedValue(
    prose({ ops: [{ insert: "The ferries were late.\n" }] }),
  );
  vi.mocked(api.momentMedia).mockImplementation(async () =>
    deleted ? [] : [recording()],
  );
  vi.mocked(api.deleteMedia).mockImplementation(async () => {
    deleted = true;
    return undefined as never;
  });
});

/**
 * The reader on the real router, not the component in isolation: the PageBar
 * menu is the thing under test, and it only exists as part of the route.
 */
async function openReader() {
  const history = createMemoryHistory({
    initialEntries: ["/timeline/moment-1"],
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
  return { router };
}

/** Walks the whole affordance: PageBar ⋯ → menu item → confirmation. */
const chooseDelete = async (name = "Delete audio clip…") => {
  await userEvent.click(
    await screen.findByRole("button", { name: "Moment actions" }),
  );
  await userEvent.click(await screen.findByRole("menuitem", { name }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Delete audio clip" }),
  );
};

describe("reader audio actions", () => {
  it("deletes a clip from the PageBar menu of a moment with no writing", async () => {
    vi.mocked(api.moment).mockImplementation(async () =>
      deleted ? { ...mediaOnly, media_count: 0 } : mediaOnly,
    );
    await openReader();
    await screen.findByRole("slider", { name: "Seek audio" });
    // The reported surface: the menu sits in the PageBar beside Write, which
    // was the only control there before.
    const actions = document.querySelector(
      ".jv-page-bar__actions",
    ) as HTMLElement;
    expect(within(actions).getByRole("button", { name: "Write" })).toBeTruthy();
    expect(
      within(actions).getByRole("button", { name: "Moment actions" }),
    ).toBeTruthy();

    await chooseDelete();

    await waitFor(() =>
      expect(api.deleteMedia).toHaveBeenCalledWith("audio-1"),
    );
    // The Moment is never pruned, so the reader stays and loses the clip.
    await waitFor(() =>
      expect(screen.queryByRole("slider", { name: "Seek audio" })).toBeNull(),
    );
    expect(screen.getByRole("button", { name: "Write" })).toBeTruthy();
  });

  it("keeps the clip below the entry's own actions when both exist", async () => {
    await openReader();
    await screen.findByRole("slider", { name: "Seek audio" });

    await userEvent.click(
      await screen.findByRole("button", { name: "Moment actions" }),
    );
    const items = await screen.findAllByRole("menuitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "Download PDF",
      "Delete entry…",
      "Delete audio clip…",
    ]);
  });

  it("numbers the clips when a moment carries more than one", async () => {
    vi.mocked(api.moment).mockResolvedValue({ ...moment, media_count: 2 });
    vi.mocked(api.momentMedia).mockResolvedValue([
      recording(),
      recording({
        id: "audio-2",
        signed_url: "/api/v1/media/audio-2/signed?sig=abc",
      }),
    ]);
    await openReader();
    await userEvent.click(
      await screen.findByRole("button", { name: "Moment actions" }),
    );

    await screen.findByRole("menuitem", { name: "Delete audio clip 1…" });
    await userEvent.click(
      screen.getByRole("menuitem", { name: "Delete audio clip 2…" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Delete audio clip" }),
    );

    await waitFor(() =>
      expect(api.deleteMedia).toHaveBeenCalledWith("audio-2"),
    );
  });

  it("offers the delete for a clip that cannot be played", async () => {
    vi.mocked(api.momentMedia).mockImplementation(async () =>
      deleted ? [] : [recording({ upload_status: "failed" })],
    );
    await openReader();
    expect(await screen.findByText("Media unavailable")).toBeTruthy();

    await chooseDelete();

    await waitFor(() =>
      expect(api.deleteMedia).toHaveBeenCalledWith("audio-1"),
    );
  });

  it("keeps the confirmation open with a reason when the delete fails", async () => {
    vi.mocked(api.deleteMedia).mockRejectedValue(new Error("network"));
    await openReader();
    await screen.findByRole("slider", { name: "Seek audio" });

    await chooseDelete();

    expect(
      await screen.findByText(
        "The audio clip couldn’t be deleted. Check your connection and try again.",
      ),
    ).toBeTruthy();
    // Still asking, so the failure can be retried rather than silently dropped.
    expect(
      screen.getByRole("button", { name: "Delete audio clip" }),
    ).toBeTruthy();
  });

  it("offers no delete for a clip the prose embeds", async () => {
    vi.mocked(api.entry).mockResolvedValue(
      prose({
        ops: [
          { insert: "Listen.\n" },
          { insert: { audio: "/api/v1/media/audio-1/signed?sig=zzz" } },
          { insert: "\n" },
        ],
      }),
    );
    await openReader();
    await screen.findByRole("heading", { name: "Harbour morning" });
    await waitFor(() =>
      expect(document.querySelector(".jv-prose__audio")).toBeTruthy(),
    );

    await userEvent.click(
      screen.getByRole("button", { name: "Moment actions" }),
    );
    const items = await screen.findAllByRole("menuitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "Download PDF",
      "Delete entry…",
    ]);
  });

  it("withholds the delete until the entry says what the prose embeds", async () => {
    vi.mocked(api.entry).mockImplementation(() => new Promise(() => {}));
    await openReader();
    await screen.findByRole("slider", { name: "Seek audio" });

    await userEvent.click(
      screen.getByRole("button", { name: "Moment actions" }),
    );
    expect(
      screen.queryByRole("menuitem", { name: "Delete audio clip…" }),
    ).toBeNull();
  });

  it("withholds the delete for a document that falls back to plain text", async () => {
    // No trailing text op: unreadable, so it never reports what it embeds.
    vi.mocked(api.entry).mockResolvedValue(
      prose({
        ops: [{ insert: { audio: "/api/v1/media/audio-1/signed?sig=zzz" } }],
      }),
    );
    await openReader();
    await screen.findByRole("slider", { name: "Seek audio" });

    await userEvent.click(
      screen.getByRole("button", { name: "Moment actions" }),
    );
    expect(
      screen.queryByRole("menuitem", { name: "Delete audio clip…" }),
    ).toBeNull();
  });
});
