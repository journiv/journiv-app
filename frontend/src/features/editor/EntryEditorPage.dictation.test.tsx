import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
import { FakeRecorder, fakeStream } from "./dictationTestKit";
import { MediaUploadError, uploadMedia } from "./mediaUpload";
import { recordingRepository } from "./recordingRepository";

/**
 * Dictation in the editor: a recording becomes a Moment attachment shown in the
 * tray, and the prose is never touched (docs/features/editor.md, Voice notes).
 */
// A routed editor plus the IndexedDB round-trips behind a recording is slow on a
// busy machine; the repo's routed-editor tests carry the same allowance
// (EntryEditorPage.datetime.test.tsx).
vi.setConfig({ testTimeout: 25_000 });

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
vi.mock("./mediaUpload", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./mediaUpload")>()),
  uploadMedia: vi.fn(),
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
const emptyMoment: MomentResponse = {
  id: "moment-1",
  user_id: user.id,
  logged_at_utc: now,
  logged_date_tz: "2026-08-24",
  logged_timezone: "Europe/Vienna",
  note: "Walked the coast path",
  media_count: 0,
};
const recording = {
  id: "audio-1",
  created_at: now,
  media_type: "audio",
  mime_type: "audio/webm",
  upload_status: "completed",
  duration: 12,
  waveform_peaks: Array.from({ length: 400 }, (_, i) => (i * 3) % 100),
  signed_url: "/api/v1/media/audio-1/signed?sig=a",
  moment_id: "moment-1",
} as MomentMediaResponse;

let uploaded = false;
let stream: ReturnType<typeof fakeStream>;

beforeEach(() => {
  vi.clearAllMocks();
  uploaded = false;
  FakeRecorder.instances = [];
  stream = fakeStream();
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  // jsdom implements no media playback.
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(
    () => undefined,
  );
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => stream.stream) },
  });
  Object.defineProperty(window, "isSecureContext", {
    configurable: true,
    value: true,
  });

  sessionStorage.clear();
  sessionStore.adopt({ accessToken: "a", userId: "user-1" });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([journal]);
  vi.mocked(api.moments).mockResolvedValue({ items: [emptyMoment] } as never);
  vi.mocked(api.moment).mockImplementation(async () =>
    uploaded ? { ...emptyMoment, media_count: 1 } : emptyMoment,
  );
  vi.mocked(api.entry).mockResolvedValue(undefined as never);
  vi.mocked(api.mediaFormats).mockResolvedValue({});
  vi.mocked(api.momentMedia).mockImplementation(async () =>
    uploaded ? [recording] : [],
  );
  vi.mocked(api.updateMoment).mockResolvedValue(emptyMoment as never);
  vi.mocked(api.instanceConfig).mockResolvedValue({
    import_export_max_file_size_mb: 100,
    max_file_size_mb: 50,
    disable_signup: false,
    oidc_enabled: false,
    oidc_only: false,
    plus: { available: false, tier: "member", upgrade_url: "x" },
  } as never);
  vi.mocked(uploadMedia).mockImplementation(() => ({
    promise: (async () => {
      uploaded = true;
      return recording;
    })(),
    abort: vi.fn(),
  }));
});

afterEach(() => vi.unstubAllGlobals());

async function openEditor(path = "/timeline/moment-1/edit") {
  const history = createMemoryHistory({
    initialEntries: [path],
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
  await screen.findByRole(
    "button",
    { name: "Voice note" },
    { timeout: 10_000 },
  );
  return { router };
}

/**
 * The Stop and Discard controls appear as soon as recording is *starting*, before
 * the recorder exists (microphone permission) and before it has attached its
 * listeners (staging opens IndexedDB first). Anything the test does to the
 * recorder must wait for it to actually be recording, or it races that start-up
 * and passes or fails with machine load.
 */
const recorderRecording = () =>
  waitFor(() => expect(FakeRecorder.instances[0]?.state).toBe("recording"), {
    timeout: 10_000,
  });

const prose = () => document.querySelector(".ql-editor") as HTMLElement;

const anchorFor = (mediaId: string, capturedAt = "2026-01-01T00:00:00.000Z") =>
  recordingRepository.saveAnchor({
    mediaId,
    userId: "user-1",
    draftKey: "user-1:moment:moment-1",
    momentId: "moment-1",
    anchor: { index: 2, before: "b", after: "a" },
    capturedAt,
  });

describe("dictation anchors follow their media", () => {
  it("drops the anchor of a recording that is gone when the editor opens", async () => {
    await anchorFor("removed-elsewhere");
    await openEditor(); // moment-1 has no media: media_count 0

    await waitFor(
      async () =>
        expect(
          await recordingRepository.readAnchor("removed-elsewhere"),
        ).toBeNull(),
      { timeout: 10_000 },
    );
  });

  it("prunes in the reader, where a writer lands after a save that dropped a recording", async () => {
    uploaded = true; // moment-1 now holds one recording: audio-1
    await anchorFor("audio-1");
    await anchorFor("dropped-by-a-save");

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

    await waitFor(
      async () =>
        expect(
          await recordingRepository.readAnchor("dropped-by-a-save"),
        ).toBeNull(),
      { timeout: 10_000 },
    );
    // The recording still on the Moment keeps its anchor.
    expect(await recordingRepository.readAnchor("audio-1")).not.toBeNull();
  });
});

describe("EntryEditorPage · dictation", () => {
  it("offers a Voice note control in the Insert group, unpressed at rest", async () => {
    await openEditor();
    const insert = screen.getByRole("group", { name: "Insert" });
    const dictate = screen.getByRole("button", { name: "Voice note" });
    expect(insert.contains(dictate)).toBe(true);
    expect(dictate.getAttribute("aria-pressed")).toBe("false");
  });

  it("records, attaches the audio to the Moment tray, and leaves the prose alone", async () => {
    await openEditor();
    const proseBefore = prose().innerHTML;

    await userEvent.click(screen.getByRole("button", { name: "Voice note" }));
    // The live region appears with the two controls a recording needs.
    const stop = await screen.findByRole(
      "button",
      { name: "Stop" },
      { timeout: 10_000 },
    );
    await recorderRecording();
    expect(screen.getByRole("button", { name: "Discard" })).toBeTruthy();
    expect(
      screen
        .getByRole("button", { name: "Voice note" })
        .getAttribute("aria-pressed"),
    ).toBe("true");

    (FakeRecorder.instances[0] as FakeRecorder).emit(2048);
    await act(async () => {
      await Promise.resolve();
    });
    await userEvent.click(stop);

    // It uploaded as a Moment attachment, through the shared transport…
    await waitFor(() => expect(uploadMedia).toHaveBeenCalledTimes(1), {
      timeout: 10_000,
    });
    const sent = vi.mocked(uploadMedia).mock.calls[0]?.[0];
    expect(sent?.momentId).toBe("moment-1");
    expect(sent?.file.type).toBe("audio/webm;codecs=opus");

    // …and shows up in the tray as a waveform player, with no manual poll of ours.
    const player = await screen.findByRole(
      "slider",
      { name: "Seek audio" },
      { timeout: 5000 },
    );
    expect(player).toBeTruthy();
    const tray = screen
      .getByText("On this moment")
      .closest("section") as HTMLElement;
    expect(tray.querySelector(".jv-media__tile--audio")).toBeTruthy();

    // The writing is byte-for-byte what it was, and nothing was saved or deleted.
    expect(prose().innerHTML).toBe(proseBefore);
    expect(api.updateMoment).not.toHaveBeenCalled();
    expect(api.deleteMedia).not.toHaveBeenCalled();
    // The staged copy is gone only because the upload succeeded.
    await waitFor(
      async () =>
        expect(await recordingRepository.listUnfinished("user-1")).toHaveLength(
          0,
        ),
      { timeout: 10_000 },
    );
  });

  it("confirms deletion of an attached voice note and refreshes the tray", async () => {
    uploaded = true;
    vi.mocked(api.deleteMedia).mockImplementation(async () => {
      uploaded = false;
      return {
        message: "Media deleted successfully",
        media_id: recording.id,
      } as never;
    });
    await openEditor();
    await screen.findByRole("button", { name: "Delete voice note" });

    await userEvent.click(
      screen.getByRole("button", { name: "Delete voice note" }),
    );
    const dialog = await screen.findByRole("alertdialog");
    expect(api.deleteMedia).not.toHaveBeenCalled();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Keep voice note" }),
    );
    expect(api.deleteMedia).not.toHaveBeenCalled();

    await userEvent.click(
      screen.getByRole("button", { name: "Delete voice note" }),
    );
    await userEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", {
        name: "Delete voice note",
      }),
    );
    await waitFor(() =>
      expect(api.deleteMedia).toHaveBeenCalledWith(recording.id),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Delete voice note" }),
      ).toBeNull(),
    );
  });

  it("refuses to save while a recording is in progress", async () => {
    await openEditor();
    await userEvent.click(screen.getByRole("button", { name: "Voice note" }));
    await screen.findByRole("button", { name: "Stop" }, { timeout: 10_000 });
    await recorderRecording();

    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    expect(
      await screen.findByText(
        "Stop the recording before saving",
        {},
        { timeout: 10_000 },
      ),
    ).toBeTruthy();
    expect(api.updateMoment).not.toHaveBeenCalled();
  });

  it("keeps a new entry open while its voice note upload has failed", async () => {
    vi.mocked(api.createMoment).mockResolvedValue({
      ...emptyMoment,
      id: "draft-moment",
    });
    vi.mocked(uploadMedia).mockImplementation(() => ({
      promise: Promise.reject(new MediaUploadError("network", "offline")),
      abort: vi.fn(),
    }));
    await openEditor(
      "/timeline/new?draft=11111111-1111-1111-1111-111111111111",
    );
    await userEvent.click(screen.getByRole("button", { name: "Voice note" }));
    await screen.findByRole("button", { name: "Stop" });
    await recorderRecording();
    (FakeRecorder.instances[0] as FakeRecorder).emit(128);
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    await screen.findByRole("button", { name: "Retry" });

    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(
      await screen.findByText("Retry or discard the voice note before saving"),
    ).toBeTruthy();
    expect(api.updateMoment).not.toHaveBeenCalled();
  });

  it("keeps a new entry open while a voice note awaits recovery", async () => {
    const draftId = "22222222-2222-2222-2222-222222222222";
    const startedAt = "2026-09-19T10:00:00.000Z";
    await recordingRepository.createSession({
      id: "recover-note",
      userId: user.id,
      draftKey: `user-1:new:${draftId}`,
      mimeType: "audio/webm",
      startedAt,
      updatedAt: startedAt,
      durationMs: 1000,
      chunkCount: 1,
      status: "stopped",
      anchor: { index: 0, before: "", after: "" },
    });
    await recordingRepository.appendChunk(
      "recover-note",
      0,
      new Uint8Array([1, 2, 3]).buffer,
    );
    await openEditor(`/timeline/new?draft=${draftId}`);
    await screen.findByRole("button", { name: "Recover" });

    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(
      await screen.findByText("Retry or discard the voice note before saving"),
    ).toBeTruthy();
    expect(api.createMoment).not.toHaveBeenCalled();
  });

  it("explains why it cannot record on an insecure connection, without opening the microphone", async () => {
    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: false,
    });
    await openEditor();

    await userEvent.click(screen.getByRole("button", { name: "Voice note" }));

    const alert = await screen.findByRole("alert", {}, { timeout: 10_000 });
    expect(alert.textContent).toMatch(/secure connection/);
    expect(alert.textContent).toMatch(/HTTPS/);
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
  });

  it("says so when the microphone is blocked", async () => {
    vi.mocked(navigator.mediaDevices.getUserMedia).mockRejectedValueOnce(
      new DOMException("blocked", "NotAllowedError"),
    );
    await openEditor();

    await userEvent.click(screen.getByRole("button", { name: "Voice note" }));

    expect(
      (await screen.findByRole("alert", {}, { timeout: 10_000 })).textContent,
    ).toMatch(/Microphone access is blocked/);
    expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
  });

  it("asks before discarding a recording, and keeps it if the writer says no", async () => {
    await openEditor();
    await userEvent.click(screen.getByRole("button", { name: "Voice note" }));
    await screen.findByRole("button", { name: "Stop" }, { timeout: 10_000 });
    await recorderRecording();

    await userEvent.click(screen.getByRole("button", { name: "Discard" }));
    const dialog = await screen.findByRole(
      "alertdialog",
      {},
      { timeout: 10_000 },
    );
    expect(dialog.textContent).toMatch(/can’t be undone/);
    await userEvent.click(
      screen.getByRole("button", { name: "Keep recording" }),
    );

    // Still recording, microphone still open.
    expect(screen.getByRole("button", { name: "Stop" })).toBeTruthy();
    expect(stream.track.stop).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Discard" }));
    await userEvent.click(
      await screen.findByRole(
        "button",
        { name: "Discard voice note" },
        { timeout: 10_000 },
      ),
    );
    await waitFor(
      () => expect(screen.queryByRole("button", { name: "Stop" })).toBeNull(),
      { timeout: 10_000 },
    );
    expect(stream.track.stop).toHaveBeenCalled();
    expect(uploadMedia).not.toHaveBeenCalled();
  });

  it("does not leave the microphone open when the editor is left", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { router } = await openEditor();
    await userEvent.click(screen.getByRole("button", { name: "Voice note" }));
    await screen.findByRole("button", { name: "Stop" }, { timeout: 10_000 });
    await recorderRecording();

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(window.confirm).toHaveBeenCalledWith(
      expect.stringMatching(/voice note that hasn’t been added yet/),
    );
    await waitFor(
      () => expect(router.state.location.pathname).toBe("/timeline/moment-1"),
      { timeout: 10_000 },
    );
    // Released when the editor unmounts, not left to the garbage collector.
    await waitFor(() => expect(stream.track.stop).toHaveBeenCalled(), {
      timeout: 10_000,
    });
  });
});

describe("EntryEditorPage · a voice note still waiting on the microphone", () => {
  const holdPrompt = () => {
    let answer!: (stream: MediaStream) => void;
    const promise = new Promise<MediaStream>((resolve) => {
      answer = resolve;
    });
    vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementationOnce(
      () => promise,
    );
    return answer;
  };

  it("offers only a way to cancel, not Stop or Discard, and never records once cancelled", async () => {
    const answer = holdPrompt();
    await openEditor();

    await userEvent.click(screen.getByRole("button", { name: "Voice note" }));
    expect(
      await screen.findByText(
        "Waiting for the microphone…",
        {},
        { timeout: 10_000 },
      ),
    ).toBeTruthy();
    // There is nothing to stop or discard yet, so neither control is offered.
    expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Discard" })).toBeNull();
    expect(
      screen
        .getByRole("button", { name: "Voice note" })
        .getAttribute("aria-pressed"),
    ).toBe("true");

    await userEvent.click(
      screen.getByRole("button", { name: "Cancel recording" }),
    );
    await waitFor(
      () =>
        expect(screen.queryByText("Waiting for the microphone…")).toBeNull(),
      { timeout: 10_000 },
    );
    expect(
      screen
        .getByRole("button", { name: "Voice note" })
        .getAttribute("aria-pressed"),
    ).toBe("false");

    // The prompt is answered after the cancel: the microphone is released and
    // nothing records.
    await act(async () => {
      answer(stream.stream);
      await Promise.resolve();
    });
    await waitFor(() => expect(stream.track.stop).toHaveBeenCalled(), {
      timeout: 10_000,
    });
    expect(FakeRecorder.instances.every((r) => r.state === "inactive")).toBe(
      true,
    );
    expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
    expect(uploadMedia).not.toHaveBeenCalled();
  });

  it("cancels when the toolbar control is pressed again", async () => {
    holdPrompt();
    await openEditor();
    const toggle = screen.getByRole("button", { name: "Voice note" });

    await userEvent.click(toggle);
    await screen.findByText(
      "Waiting for the microphone…",
      {},
      { timeout: 10_000 },
    );
    await userEvent.click(toggle);

    await waitFor(
      () =>
        expect(screen.queryByText("Waiting for the microphone…")).toBeNull(),
      { timeout: 10_000 },
    );
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
  });

  it("does not block Done or warn on Cancel: nothing has been recorded yet", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    holdPrompt();
    const { router } = await openEditor();

    await userEvent.click(screen.getByRole("button", { name: "Voice note" }));
    await screen.findByText(
      "Waiting for the microphone…",
      {},
      { timeout: 10_000 },
    );
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    // The page's own Cancel leaves without asking about a recording.
    expect(window.confirm).not.toHaveBeenCalled();
    await waitFor(
      () => expect(router.state.location.pathname).toBe("/timeline/moment-1"),
      { timeout: 10_000 },
    );
  });
});
