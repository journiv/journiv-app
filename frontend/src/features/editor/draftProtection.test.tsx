import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import { ApiError } from "../../api/client/errors";
import type {
  EntryResponse,
  JournalResponse,
  MomentMediaResponse,
  MomentPageResponse,
  MomentResponse,
  UserResponse,
} from "../../api/generated/types.gen";
import { queryKeys } from "../../api/query/keys";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";
import type { DurableDraftDelta } from "./draftCanonical";
import {
  draftRepository,
  DraftStorageError,
  type EditorDraftV1,
} from "./draftRepository";

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
    login: vi.fn(),
    refresh: vi.fn(),
  },
}));

const now = "2026-08-24T08:30:00Z";
const later = "2026-08-24T11:00:00Z";
const PHOTO = "0f8b1c2d-3e4f-4a5b-8c9d-0e1f2a3b4c5d";
const signed = (id: string, sig: string) =>
  `/api/v1/media/${id}/signed?uid=user-1&exp=1790000000&sig=${sig}`;

const user: UserResponse = {
  id: "user-1",
  email: "d@example.com",
  name: "Phase D",
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
    content_plain_text: "Coffee while the rain moved past.",
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
  content_plain_text: "Coffee while the rain moved past.",
  content_delta: { ops: [{ insert: "Coffee while the rain moved past.\n" }] },
  word_count: 6,
  created_at: now,
  updated_at: now,
};
/** The server draft a new entry acquires on its first media attach. */
const draftMoment: MomentResponse = {
  id: "moment-9",
  user_id: user.id,
  logged_at_utc: now,
  logged_date_tz: "2026-08-24",
  logged_timezone: "Europe/Vienna",
  entry: {
    id: "draft-entry-9",
    journal_id: journal.id,
    moment_id: "moment-9",
    created_at: now,
    updated_at: now,
  },
};
const photo: MomentMediaResponse = {
  id: PHOTO,
  moment_id: moment.id,
  media_type: "image",
  mime_type: "image/jpeg",
  created_at: now,
  signed_url: signed(PHOTO, "fresh"),
  upload_status: "completed",
};

const durable = (ops: unknown[]) => ({ ops }) as unknown as DurableDraftDelta;

const storedDraft = (over: Partial<EditorDraftV1> = {}): EditorDraftV1 => ({
  key: "user-1:entry:entry-1",
  userId: "user-1",
  entryId: "entry-1",
  momentId: "moment-1",
  journalId: "journal-1",
  title: "A rainy morning",
  contentDelta: durable([
    { insert: "Writing that never reached the server\n" },
  ]),
  baseUpdatedAt: now,
  modifiedAt: later,
  dirty: true,
  ...over,
});

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
  vi.mocked(api.moments).mockResolvedValue({
    items: [moment],
  } as MomentPageResponse);
  // Id-aware, because recovery now VERIFIES the Moment a draft records rather
  // than trusting it: a mock that answers every id with the same Moment would
  // hide exactly the mismatch that check exists to catch.
  vi.mocked(api.moment).mockImplementation(async (id: string) => {
    if (id === moment.id) return moment;
    if (id === "moment-9") return draftMoment;
    throw new ApiError("Moment not found", { status: 404 });
  });
  vi.mocked(api.entry).mockResolvedValue(entry);
  vi.mocked(api.momentMedia).mockResolvedValue([photo]);
  vi.mocked(api.mediaFormats).mockResolvedValue({});
  vi.mocked(api.updateMoment).mockResolvedValue(moment);
  vi.mocked(api.createMoment).mockResolvedValue({
    ...moment,
    id: "moment-new",
  });
  vi.mocked(api.createDraftEntry).mockResolvedValue({
    ...entry,
    id: "draft-entry-9",
  });
});

async function renderRoute(
  path: string,
  options: { signedInAlready?: boolean } = {},
) {
  const history = createMemoryHistory({ initialEntries: [path] });
  const router = createAppRouter(history);
  const queryClient = createAppQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  // Opening the editor from inside the running app, where the signed-in user is
  // already cached. The draft key then exists on the FIRST render rather than
  // arriving later — a different, and much more common, mount order.
  if (options.signedInAlready) queryClient.setQueryData(queryKeys.me, user);
  // StrictMode, like the real app (src/main.tsx). React double-invokes effects
  // in development, and a mount/teardown/remount cycle has already deadlocked
  // one effect here — the editor sat on a skeleton forever because a read was
  // cancelled by the first cleanup and skipped by a guard on the second run.
  const view = render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  );
  await router.load();
  return { ...view, router };
}

const bodyText = () =>
  screen.getByLabelText("Entry body").textContent?.trim() ?? "";

describe("offering a stored draft", () => {
  it("opens on the server's content when there is no draft", async () => {
    await renderRoute("/timeline/moment-1/edit");
    expect(await screen.findByLabelText("Entry body")).toBeTruthy();
    expect(screen.queryByText(/unsaved changes to this entry/i)).toBeNull();
  });

  it("offers Recover or Discard, and Recover opens on the draft", async () => {
    await draftRepository.write(storedDraft());
    await renderRoute("/timeline/moment-1/edit");

    expect(
      await screen.findByText(/unsaved changes to this entry/i),
    ).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Recover" }));

    await waitFor(() =>
      expect(bodyText()).toContain("Writing that never reached the server"),
    );
    // The stored copy stays until a save confirms; recovering is not saving.
    expect(await draftRepository.read("user-1:entry:entry-1")).not.toBeNull();
  });

  it("asks before discarding, and keeps the draft when the answer is no", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await draftRepository.write(storedDraft());
    await renderRoute("/timeline/moment-1/edit");

    await userEvent.click(
      await screen.findByRole("button", { name: "Discard draft" }),
    );

    expect(confirm).toHaveBeenCalled();
    // Still offered, still stored: discarding is the one irreversible thing
    // either surface can do.
    expect(screen.getByRole("button", { name: "Recover" })).toBeTruthy();
    expect(await draftRepository.read("user-1:entry:entry-1")).not.toBeNull();
  });

  it("Discard deletes the record and opens on the server's content", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await draftRepository.write(storedDraft());
    await renderRoute("/timeline/moment-1/edit");

    await userEvent.click(
      await screen.findByRole("button", { name: "Discard draft" }),
    );

    await waitFor(() =>
      expect(bodyText()).toContain("Coffee while the rain moved past"),
    );
    expect(await draftRepository.read("user-1:entry:entry-1")).toBeNull();
  });

  it("warns when the entry changed elsewhere since the draft was written", async () => {
    // The draft was written against an older version of the server's entry.
    await draftRepository.write(
      storedDraft({ baseUpdatedAt: "2026-08-20T09:00:00Z" }),
    );
    await renderRoute("/timeline/moment-1/edit");

    const warning = await screen.findByText(
      /changed somewhere else since then/i,
    );
    expect(warning).toBeTruthy();
    // Warned about, never merged and never chosen automatically.
    expect(screen.getByRole("button", { name: "Recover" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Discard draft" })).toBeTruthy();
  });

  it("does not warn when the server has not moved", async () => {
    await draftRepository.write(storedDraft());
    await renderRoute("/timeline/moment-1/edit");

    await screen.findByText(/unsaved changes to this entry/i);
    expect(screen.queryByText(/changed somewhere else since then/i)).toBeNull();
  });

  it("silently drops a draft that matches the server and asks nothing", async () => {
    // What is left behind when a save lands in another tab.
    await draftRepository.write(
      storedDraft({
        contentDelta: durable([
          { insert: "Coffee while the rain moved past.\n" },
        ]),
      }),
    );
    await renderRoute("/timeline/moment-1/edit");

    expect(await screen.findByLabelText("Entry body")).toBeTruthy();
    expect(screen.queryByText(/unsaved changes to this entry/i)).toBeNull();
    await waitFor(async () =>
      expect(await draftRepository.read("user-1:entry:entry-1")).toBeNull(),
    );
  });

  it("never offers one user's draft to another", async () => {
    await draftRepository.write(
      storedDraft({ key: "user-2:entry:entry-1", userId: "user-2" }),
    );
    await renderRoute("/timeline/moment-1/edit");

    expect(await screen.findByLabelText("Entry body")).toBeTruthy();
    expect(screen.queryByText(/unsaved changes to this entry/i)).toBeNull();
    expect(bodyText()).toContain("Coffee while the rain moved past");
  });
});

describe("media in a recovered draft", () => {
  const withPhoto = () =>
    storedDraft({
      contentDelta: durable([
        { insert: "Look at this\n" },
        { insert: { image: PHOTO } },
        { insert: "\n" },
      ]),
    });

  it("resolves stored media ids to fresh signed URLs", async () => {
    await draftRepository.write(withPhoto());
    const view = await renderRoute("/timeline/moment-1/edit");

    await userEvent.click(
      await screen.findByRole("button", { name: "Recover" }),
    );

    await waitFor(() => {
      const image = view.container.querySelector<HTMLImageElement>(
        ".jv-editor__surface img",
      );
      expect(image?.getAttribute("src")).toBe(signed(PHOTO, "fresh"));
    });
  });

  it("keeps the editor closed, and the writing visible, when media cannot be reached", async () => {
    vi.mocked(api.momentMedia).mockRejectedValue(new Error("offline"));
    await draftRepository.write(withPhoto());
    await renderRoute("/timeline/moment-1/edit");

    expect(
      await screen.findByText(/attachments need a connection/i),
    ).toBeTruthy();
    // Nothing is lost: the writing is on screen, and the record is untouched.
    expect(screen.getByText(/Look at this/)).toBeTruthy();
    expect(screen.queryByLabelText("Entry body")).toBeNull();
    expect(await draftRepository.read("user-1:entry:entry-1")).not.toBeNull();
  });

  it("opens the editor once media can be reached again", async () => {
    vi.mocked(api.momentMedia).mockRejectedValueOnce(new Error("offline"));
    await draftRepository.write(withPhoto());
    await renderRoute("/timeline/moment-1/edit");

    await userEvent.click(
      await screen.findByRole("button", { name: "Try again" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Recover" }),
    );

    await waitFor(() => expect(bodyText()).toContain("Look at this"));
  });

  it("drops media the Moment no longer has, and says how many", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([]);
    await draftRepository.write(withPhoto());
    const view = await renderRoute("/timeline/moment-1/edit");

    expect(
      await screen.findByText(/attachment is no longer available/i),
    ).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Recover" }));

    await waitFor(() => expect(bodyText()).toContain("Look at this"));
    expect(view.container.querySelector(".jv-editor__surface img")).toBeNull();
  });
});

describe("a recovered new entry keeps its server Moment", () => {
  const localDraftId = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";

  it("finalises the Moment the media already belongs to, creating no second one", async () => {
    // What a new entry looks like after a photo was attached and the tab died:
    // the draft Moment and draft Entry already exist on the server.
    await draftRepository.write(
      storedDraft({
        key: `user-1:new:${localDraftId}`,
        entryId: "draft-entry-9",
        momentId: "moment-9",
        localDraftId,
        baseUpdatedAt: undefined,
        title: "Half-written",
        contentDelta: durable([
          { insert: "Started this\n" },
          { insert: { image: PHOTO } },
          { insert: "\n" },
        ]),
      }),
    );
    vi.mocked(api.momentMedia).mockResolvedValue([
      { ...photo, moment_id: "moment-9" },
    ]);

    await renderRoute(`/journals/journal-1/new?draft=${localDraftId}`);
    await userEvent.click(
      await screen.findByRole("button", { name: "Recover" }),
    );
    await waitFor(() => expect(bodyText()).toContain("Started this"));

    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() => expect(api.updateMoment).toHaveBeenCalled());
    // The whole point: the recovered Moment is finalised, not duplicated.
    expect(vi.mocked(api.updateMoment).mock.calls[0]?.[0]).toBe("moment-9");
    expect(api.createMoment).not.toHaveBeenCalled();
  });

  it("still cleans that Moment up if the writer cancels", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await draftRepository.write(
      storedDraft({
        key: `user-1:new:${localDraftId}`,
        entryId: "draft-entry-9",
        momentId: "moment-9",
        localDraftId,
        baseUpdatedAt: undefined,
        contentDelta: durable([{ insert: "Started this\n" }]),
      }),
    );

    await renderRoute(`/journals/journal-1/new?draft=${localDraftId}`);
    await userEvent.click(
      await screen.findByRole("button", { name: "Recover" }),
    );
    await screen.findByLabelText("Entry body");

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() =>
      expect(api.deleteMoment).toHaveBeenCalledWith("moment-9"),
    );
    // An explicit discard is one of the two things that may delete the record.
    await waitFor(async () =>
      expect(
        await draftRepository.read(`user-1:new:${localDraftId}`),
      ).toBeNull(),
    );
  });
});

describe("recovering a draft for an entry that already exists", () => {
  /**
   * The Moment on the route is the reader's OWN saved entry. It is not a draft
   * this editing session created, and nothing the local-draft path does may
   * make it look like one — Cancel would then delete a real journal entry.
   */
  it("never deletes the saved Moment when the writer cancels", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await draftRepository.write(storedDraft());

    await renderRoute("/timeline/moment-1/edit");
    await userEvent.click(
      await screen.findByRole("button", { name: "Recover" }),
    );
    await waitFor(() =>
      expect(bodyText()).toContain("Writing that never reached the server"),
    );

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(api.deleteMoment).not.toHaveBeenCalled());
    expect(api.deleteEntry).not.toHaveBeenCalled();
  });
});

describe("a recovered draft whose server draft is gone", () => {
  const localDraftId = "aaaaaaaa-bbbb-4ccc-8ddd-111111111111";

  const orphaned = (over: Partial<EditorDraftV1> = {}) =>
    storedDraft({
      key: `user-1:new:${localDraftId}`,
      entryId: "draft-entry-9",
      momentId: "moment-gone",
      localDraftId,
      baseUpdatedAt: undefined,
      title: "Half-written",
      contentDelta: durable([{ insert: "Started this\n" }]),
      ...over,
    });

  it("saves the writing into a fresh Moment instead of failing forever", async () => {
    // A second tab cancelled the same draft, so the Moment it recorded is gone.
    // Finalising through it could only ever 404; the writing must still land.
    await draftRepository.write(orphaned());

    await renderRoute(`/journals/journal-1/new?draft=${localDraftId}`);
    await userEvent.click(
      await screen.findByRole("button", { name: "Recover" }),
    );
    await waitFor(() => expect(bodyText()).toContain("Started this"));

    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() => expect(api.createMoment).toHaveBeenCalled());
    expect(api.updateMoment).not.toHaveBeenCalled();
  });

  it("says the attachments are not coming back", async () => {
    await draftRepository.write(
      orphaned({
        contentDelta: durable([
          { insert: "Started this\n" },
          { insert: { image: PHOTO } },
          { insert: "\n" },
        ]),
      }),
    );

    await renderRoute(`/journals/journal-1/new?draft=${localDraftId}`);

    // Not a dead end behind "could not be reached": the Moment is gone, so the
    // photo is gone, and the writing is still offered.
    expect(
      await screen.findByText(/no longer available and will not come back/i),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Recover" })).toBeTruthy();
  });

  it("keeps the recorded identity when the server cannot be reached at all", async () => {
    // Offline is not "gone". Dropping the identity here would leave the draft
    // Moment orphaned and create a second one beside it.
    vi.mocked(api.moment).mockRejectedValue(
      new ApiError("Failed to fetch", {}),
    );
    await draftRepository.write(orphaned({ momentId: "moment-9" }));

    await renderRoute(`/journals/journal-1/new?draft=${localDraftId}`);
    await userEvent.click(
      await screen.findByRole("button", { name: "Recover" }),
    );
    await waitFor(() => expect(bodyText()).toContain("Started this"));

    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() => expect(api.updateMoment).toHaveBeenCalled());
    expect(vi.mocked(api.updateMoment).mock.calls[0]?.[0]).toBe("moment-9");
    expect(api.createMoment).not.toHaveBeenCalled();
  });

  it("creates the entry when only the draft Entry was deleted", async () => {
    // Cancel-with-media keeps the Moment and drops just its draft Entry. The
    // record still names that Entry; the Moment is the authority.
    vi.mocked(api.moment).mockResolvedValue({ ...draftMoment, entry: null });
    await draftRepository.write(orphaned({ momentId: "moment-9" }));

    await renderRoute(`/journals/journal-1/new?draft=${localDraftId}`);
    await userEvent.click(
      await screen.findByRole("button", { name: "Recover" }),
    );
    await waitFor(() => expect(bodyText()).toContain("Started this"));

    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() => expect(api.updateMoment).toHaveBeenCalled());
    const [id, body] = vi.mocked(api.updateMoment).mock.calls[0] ?? [];
    expect(id).toBe("moment-9");
    // `entry_update` would address an Entry that is not there any more.
    expect(body).toHaveProperty("entry_create");
  });
});

describe("media on a recovered draft that is then cancelled", () => {
  const localDraftId = "aaaaaaaa-bbbb-4ccc-8ddd-ffffffffffff";

  it("keeps the photos, exactly as an unreloaded session would", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    await draftRepository.write(
      storedDraft({
        key: `user-1:new:${localDraftId}`,
        entryId: "draft-entry-9",
        momentId: "moment-9",
        localDraftId,
        baseUpdatedAt: undefined,
        contentDelta: durable([
          { insert: "Started this\n" },
          { insert: { image: PHOTO } },
          { insert: "\n" },
        ]),
      }),
    );
    vi.mocked(api.momentMedia).mockResolvedValue([
      { ...photo, moment_id: "moment-9" },
    ]);

    await renderRoute(`/journals/journal-1/new?draft=${localDraftId}`);
    await userEvent.click(
      await screen.findByRole("button", { name: "Recover" }),
    );
    await screen.findByLabelText("Entry body");

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    // Cancelling never deletes photographs someone attached. A reload must not
    // change that: only the draft Entry goes, and the Moment survives with its
    // media, exactly as it would have without the recovery.
    await waitFor(() =>
      expect(api.deleteEntry).toHaveBeenCalledWith("draft-entry-9"),
    );
    expect(api.deleteMoment).not.toHaveBeenCalled();
    expect(confirm.mock.calls[0]?.[0]).toContain("will stay on this moment");
  });
});

describe("opening the editor when the user is already loaded", () => {
  it("reaches the recovery prompt instead of hanging on a skeleton", async () => {
    // React double-invokes effects under StrictMode. When the draft key is
    // known at first mount, that is mount -> cleanup -> mount on the effect
    // that reads the local draft: a read cancelled by the first cleanup and
    // then skipped on the second run leaves the editor on a skeleton forever.
    await draftRepository.write(storedDraft());
    await renderRoute("/timeline/moment-1/edit", { signedInAlready: true });

    expect(await screen.findByRole("button", { name: "Recover" })).toBeTruthy();
  });

  it("opens the editor when there is no draft to offer", async () => {
    await renderRoute("/timeline/moment-1/edit", { signedInAlready: true });
    expect(await screen.findByLabelText("Entry body")).toBeTruthy();
  });

  it("opens a new entry when there is no draft to offer", async () => {
    await renderRoute("/journals/journal-1/new", { signedInAlready: true });
    expect(await screen.findByLabelText("Entry body")).toBeTruthy();
  });
});

describe("writing is kept as it is typed", () => {
  it("keeps a new entry's writing and puts its draft id in the URL", async () => {
    const view = await renderRoute("/journals/journal-1/new");
    await userEvent.type(
      await screen.findByLabelText("Entry body"),
      "Something worth keeping",
    );

    await waitFor(
      () => expect(view.router.state.location.search.draft).toBeTruthy(),
      { timeout: 2_000 },
    );
    const draftId = view.router.state.location.search.draft as string;
    await waitFor(async () =>
      expect(await draftRepository.read(`user-1:new:${draftId}`)).toMatchObject(
        {
          contentDelta: {
            ops: [
              { insert: expect.stringContaining("Something worth keeping") },
            ],
          },
        },
      ),
    );
  });

  it("does not prompt to discard when it records the draft id in the URL", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const view = await renderRoute("/journals/journal-1/new");
    await userEvent.type(await screen.findByLabelText("Entry body"), "Typing");

    await waitFor(
      () => expect(view.router.state.location.search.draft).toBeTruthy(),
      { timeout: 2_000 },
    );
    // A same-path navigation is the editor talking to itself, not the writer
    // leaving. Prompting here would fire on the first keystroke of every entry.
    expect(confirm).not.toHaveBeenCalled();
    expect(view.router.state.location.pathname).toBe("/journals/journal-1/new");
  });

  it("says so on screen when the browser will not keep a local copy", async () => {
    const write = vi
      .spyOn(draftRepository, "write")
      .mockRejectedValue(
        new DraftStorageError("blocked", { unavailable: true }),
      );
    await renderRoute("/journals/journal-1/new");
    await userEvent.type(await screen.findByLabelText("Entry body"), "Typing");

    expect(
      await screen.findByText(
        /won’t keep a local copy/i,
        {},
        { timeout: 2_000 },
      ),
    ).toBeTruthy();
    write.mockRestore();
  });
});

describe("when the entry changed somewhere else", () => {
  it("sends the version it opened on, so the server can refuse", async () => {
    await renderRoute("/timeline/moment-1/edit");
    await userEvent.type(
      await screen.findByLabelText("Entry body"),
      " and more",
    );

    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() => expect(api.updateMoment).toHaveBeenCalled());
    const [, body] = vi.mocked(api.updateMoment).mock.calls[0] ?? [];
    expect(body).toMatchObject({
      entry_update: { expected_updated_at: entry.updated_at },
    });
  });

  it("refuses quietly and keeps every word, offering the decision", async () => {
    vi.mocked(api.updateMoment).mockRejectedValue(
      new ApiError("This entry changed somewhere else", { status: 409 }),
    );
    await renderRoute("/timeline/moment-1/edit");
    await userEvent.type(
      await screen.findByLabelText("Entry body"),
      " and more",
    );

    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    expect(await screen.findByText(/saved somewhere else/i)).toBeTruthy();
    // The writing is untouched, and the local copy survives a refused save.
    expect(bodyText()).toContain("and more");
    await waitFor(async () =>
      expect(await draftRepository.read("user-1:entry:entry-1")).not.toBeNull(),
    );
  });

  it("drops the version only for the save the writer asked to force", async () => {
    vi.mocked(api.updateMoment).mockRejectedValueOnce(
      new ApiError("This entry changed somewhere else", { status: 409 }),
    );
    await renderRoute("/timeline/moment-1/edit");
    await userEvent.type(
      await screen.findByLabelText("Entry body"),
      " and more",
    );
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    await screen.findByRole("button", { name: "Save anyway" });

    await userEvent.click(screen.getByRole("button", { name: "Save anyway" }));

    await waitFor(() =>
      expect(vi.mocked(api.updateMoment).mock.calls.length).toBe(2),
    );
    const [, forced] = vi.mocked(api.updateMoment).mock.calls[1] ?? [];
    expect(
      (forced as { entry_update?: Record<string, unknown> }).entry_update,
    ).not.toHaveProperty("expected_updated_at");
    // And the local copy goes only once the server has confirmed.
    await waitFor(async () =>
      expect(await draftRepository.read("user-1:entry:entry-1")).toBeNull(),
    );
  });

  it("claims no version for a draft nobody else can see", async () => {
    // A draft Moment is invisible to every other device, so there is nothing to
    // defend and a spurious 409 would only block the first real save.
    const localDraftId = "aaaaaaaa-bbbb-4ccc-8ddd-222222222222";
    await draftRepository.write(
      storedDraft({
        key: `user-1:new:${localDraftId}`,
        entryId: "draft-entry-9",
        momentId: "moment-9",
        localDraftId,
        baseUpdatedAt: undefined,
        contentDelta: durable([{ insert: "Started this\n" }]),
      }),
    );

    await renderRoute(`/journals/journal-1/new?draft=${localDraftId}`);
    await userEvent.click(
      await screen.findByRole("button", { name: "Recover" }),
    );
    await screen.findByLabelText("Entry body");
    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() => expect(api.updateMoment).toHaveBeenCalled());
    const [, body] = vi.mocked(api.updateMoment).mock.calls[0] ?? [];
    expect(
      (body as { entry_update?: Record<string, unknown> }).entry_update,
    ).not.toHaveProperty("expected_updated_at");
  });
});

describe("when the draft may be deleted", () => {
  it("keeps it after a failed server save", async () => {
    vi.mocked(api.updateMoment).mockRejectedValue(new Error("boom"));
    await renderRoute("/timeline/moment-1/edit");
    await userEvent.type(
      await screen.findByLabelText("Entry body"),
      " and more",
    );

    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    await screen.findByRole("alert");

    await waitFor(async () =>
      expect(await draftRepository.read("user-1:entry:entry-1")).not.toBeNull(),
    );
  });

  it("deletes it only after the server confirms the save", async () => {
    await renderRoute("/timeline/moment-1/edit");
    await userEvent.type(
      await screen.findByLabelText("Entry body"),
      " and more",
    );
    await waitFor(
      async () =>
        expect(
          await draftRepository.read("user-1:entry:entry-1"),
        ).not.toBeNull(),
      { timeout: 2_000 },
    );

    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() => expect(api.updateMoment).toHaveBeenCalled());
    await waitFor(async () =>
      expect(await draftRepository.read("user-1:entry:entry-1")).toBeNull(),
    );
    // And it STAYS deleted. Leaving the editor unmounts it, and the unmount is
    // a flush point — one that must not write back the record the save just
    // retired.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(await draftRepository.read("user-1:entry:entry-1")).toBeNull();
  });

  it("stays deleted after the writer cancels", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await renderRoute("/timeline/moment-1/edit");
    await userEvent.type(
      await screen.findByLabelText("Entry body"),
      " and more",
    );
    await waitFor(
      async () =>
        expect(
          await draftRepository.read("user-1:entry:entry-1"),
        ).not.toBeNull(),
      { timeout: 2_000 },
    );

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    // Cancel is an explicit discard. The editor then unmounts, and its unmount
    // flush must not resurrect what the writer just threw away — a draft that
    // comes back is offered again on the next visit.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(await draftRepository.read("user-1:entry:entry-1")).toBeNull();
  });
});
