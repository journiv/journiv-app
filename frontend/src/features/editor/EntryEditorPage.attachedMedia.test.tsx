import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
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
 * "Write about this moment" on a Moment that already has attached media.
 *
 * The attached-media gallery shows above the prose; "Add to entry" promotes an
 * item into the writing. What must hold: the original MomentMedia is never
 * copied, never uploaded again, and never deleted by opening or cancelling the
 * editor — it stays attached to the Moment until a save actually drops it from
 * the document (docs/features/editor.md).
 */
vi.mock("../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    journals: vi.fn(),
    moments: vi.fn(),
    moment: vi.fn(),
    entry: vi.fn(),
    mediaFormats: vi.fn(),
    momentMedia: vi.fn(),
    createMoment: vi.fn(),
    updateMoment: vi.fn(),
    createDraftEntry: vi.fn(),
    deleteMedia: vi.fn(),
    instanceConfig: vi.fn(),
    integrationStatus: vi.fn(),
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
// A note-only Moment: no Entry yet, but photos already attached to it — plus
// one attachment of a kind the editor cannot embed inline.
const moment: MomentResponse = {
  id: "moment-1",
  user_id: user.id,
  logged_at_utc: now,
  logged_date_tz: "2026-08-24",
  logged_timezone: "Europe/Vienna",
  note: "Walked the coast path",
  media_count: 3,
};

const BEACH_URL = "/api/v1/media/m-a/signed?sig=a";
const SUNSET_URL = "/api/v1/media/m-b/signed?sig=b";

const attachedMedia: MomentMediaResponse[] = [
  {
    id: "m-a",
    created_at: now,
    media_type: "image",
    mime_type: "image/jpeg",
    upload_status: "completed",
    width: 1600,
    height: 1067,
    alt_text: "Beach",
    signed_url: BEACH_URL,
    moment_id: "moment-1",
  } as MomentMediaResponse,
  {
    id: "m-b",
    created_at: now,
    media_type: "image",
    mime_type: "image/jpeg",
    upload_status: "completed",
    width: 1600,
    height: 1067,
    alt_text: "Sunset",
    signed_url: SUNSET_URL,
    moment_id: "moment-1",
  } as MomentMediaResponse,
  {
    id: "m-x",
    created_at: now,
    media_type: "unknown",
    mime_type: "application/octet-stream",
    upload_status: "completed",
    alt_text: "capture.bin",
    signed_url: "/api/v1/media/m-x/signed?sig=x",
    moment_id: "moment-1",
  } as MomentMediaResponse,
];

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([journal]);
  vi.mocked(api.moments).mockResolvedValue({ items: [moment] } as never);
  vi.mocked(api.moment).mockResolvedValue(moment);
  vi.mocked(api.entry).mockResolvedValue(undefined as never);
  vi.mocked(api.mediaFormats).mockResolvedValue({});
  vi.mocked(api.momentMedia).mockResolvedValue(attachedMedia);
  vi.mocked(api.updateMoment).mockResolvedValue(moment as never);
  vi.mocked(api.instanceConfig).mockResolvedValue({
    import_export_max_file_size_mb: 100,
    max_file_size_mb: 50,
    disable_signup: false,
    oidc_enabled: false,
    oidc_only: false,
    plus: { available: false, tier: "member", upgrade_url: "x" },
  } as never);
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
  await screen.findAllByRole(
    "button",
    { name: "Add to entry" },
    { timeout: 10_000 },
  );
  return { router };
}

describe("EntryEditorPage · attached moment media", () => {
  it("shows attachments in a labelled tray above the prose before anything is inserted", async () => {
    await openEditor();

    // The tray reads as attachments, not entry content.
    expect(screen.getByText("On this moment")).toBeTruthy();
    expect(screen.getByText(/aren’t in your entry yet/i)).toBeTruthy();
    expect(screen.getByAltText("Beach")).toBeTruthy();
    expect(screen.getByAltText("Sunset")).toBeTruthy();
    // "Add to entry" only for the two images — the editor can embed image,
    // video and audio inline, not the "unknown" attachment.
    expect(
      screen.getAllByRole("button", { name: "Add to entry" }),
    ).toHaveLength(2);
  });

  it("keeps a kind it cannot embed in the tray, with no Add to entry", async () => {
    await openEditor();

    const tray = screen
      .getByText("On this moment")
      .closest("section") as HTMLElement;
    // Three tiles (two images + the unknown attachment); the unknown one is not
    // hidden or lost.
    expect(tray.querySelectorAll(".jv-media__tile")).toHaveLength(3);
    // Two images → two actions; the unknown item contributes none.
    expect(
      screen.getAllByRole("button", { name: "Add to entry" }),
    ).toHaveLength(2);
  });

  it("moves one item into the prose, marks its tile Added, and neither uploads nor deletes media", async () => {
    await openEditor();
    const adds = screen.getAllByRole("button", { name: "Add to entry" });
    await userEvent.click(adds[0]);

    // The media is now in the writing.
    const prose = document.querySelector(".ql-editor");
    await waitFor(() =>
      expect(prose?.querySelector(`img[src="${BEACH_URL}"]`)).toBeTruthy(),
    );
    // The source tile stays visible but flips to an Added state — it does not
    // silently vanish — and loses its action. The other tile is untouched.
    const beachTile = screen
      .getByAltText("Beach")
      .closest(".jv-media__tile") as HTMLElement;
    expect(beachTile.className).toContain("jv-media__tile--added");
    expect(
      screen.getAllByRole("button", { name: "Add to entry" }),
    ).toHaveLength(1);

    // Using an existing attachment is a document edit only: no new MomentMedia
    // record, no re-upload, and nothing deleted.
    expect(api.deleteMedia).not.toHaveBeenCalled();
    expect(api.updateMoment).not.toHaveBeenCalled();
  });

  it("keeps the attached media on the Moment when the editor is cancelled before saving", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { router } = await openEditor();
    const adds = screen.getAllByRole("button", { name: "Add to entry" });
    await userEvent.click(adds[0]);

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/timeline/moment-1"),
    );
    expect(api.deleteMedia).not.toHaveBeenCalled();
    expect(api.updateMoment).not.toHaveBeenCalled();
  });

  it("saves the moved media inline in content_delta for the backend to orphan-diff", async () => {
    const { router } = await openEditor();
    const adds = screen.getAllByRole("button", { name: "Add to entry" });
    await userEvent.click(adds[0]);

    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() => expect(api.updateMoment).toHaveBeenCalled());
    const [id, body] = vi.mocked(api.updateMoment).mock.calls[0];
    expect(id).toBe("moment-1");
    const delta =
      // note-only Moment → first save creates the entry
      (body as { entry_create?: { content_delta?: unknown } }).entry_create
        ?.content_delta;
    expect(JSON.stringify(delta)).toContain("/api/v1/media/m-a/signed");
    // The other attachment was left alone; nothing was deleted client-side.
    expect(api.deleteMedia).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/timeline/moment-1"),
    );
  });
});
