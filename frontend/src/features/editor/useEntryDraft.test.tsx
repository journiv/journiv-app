import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client/api";
import type { MomentResponse } from "../../api/generated/types.gen";
import { useEntryDraft } from "./useEntryDraft";

vi.mock("../../api/client/api", () => ({
  api: {
    createMoment: vi.fn(),
    createDraftEntry: vi.fn(),
    deleteMoment: vi.fn(),
    deleteEntry: vi.fn(),
  },
}));

const options = { loggedAtUtc: "2026-08-26T12:00:00Z", loggedTimezone: "UTC" };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.createMoment).mockResolvedValue({
    id: "moment-new",
  } as MomentResponse);
  vi.mocked(api.createDraftEntry).mockResolvedValue({
    id: "entry-draft",
  } as never);
});

describe("useEntryDraft", () => {
  it("creates a Moment and a draft Entry on first use", async () => {
    const { result } = renderHook(() => useEntryDraft(options));
    let identity: unknown;
    await act(async () => {
      identity = await result.current.ensure("journal-1");
    });

    expect(identity).toEqual({
      momentId: "moment-new",
      entryId: "entry-draft",
    });
    expect(api.createMoment).toHaveBeenCalledTimes(1);
    expect(vi.mocked(api.createDraftEntry).mock.calls[0][0]).toMatchObject({
      journal_id: "journal-1",
      moment_id: "moment-new",
    });
  });

  it("is single-flight: selecting several files does not create several Moments", async () => {
    const { result } = renderHook(() => useEntryDraft(options));
    await act(async () => {
      await Promise.all([
        result.current.ensure("journal-1"),
        result.current.ensure("journal-1"),
        result.current.ensure("journal-1"),
      ]);
    });
    expect(api.createMoment).toHaveBeenCalledTimes(1);
  });

  it("reuses an existing Moment and never creates a draft for it", async () => {
    const existing = {
      id: "moment-1",
      entry: { id: "entry-1" },
    } as MomentResponse;
    const { result } = renderHook(() =>
      useEntryDraft({ ...options, moment: existing }),
    );
    let identity: unknown;
    await act(async () => {
      identity = await result.current.ensure("journal-1");
    });
    expect(identity).toEqual({ momentId: "moment-1", entryId: "entry-1" });
    expect(api.createMoment).not.toHaveBeenCalled();
  });

  it("still attaches media when the draft Entry cannot be created", async () => {
    vi.mocked(api.createDraftEntry).mockRejectedValue(new Error("nope"));
    const { result } = renderHook(() => useEntryDraft(options));
    let identity: { momentId: string; entryId: string | null } | undefined;
    await act(async () => {
      identity = await result.current.ensure("journal-1");
    });
    // The Moment alone is enough to own media.
    expect(identity?.momentId).toBe("moment-new");
    expect(identity?.entryId).toBeNull();
  });

  it("keeps uploaded media on cancel by dropping only the draft Entry", async () => {
    const { result } = renderHook(() => useEntryDraft(options));
    await act(async () => {
      await result.current.ensure("journal-1");
    });
    await act(async () => {
      await result.current.discard(true);
    });
    // The Moment survives, so its media becomes a visible media-only Moment.
    expect(api.deleteEntry).toHaveBeenCalledWith("entry-draft");
    expect(api.deleteMoment).not.toHaveBeenCalled();
  });

  it("removes the whole Moment on cancel when nothing was attached", async () => {
    const { result } = renderHook(() => useEntryDraft(options));
    await act(async () => {
      await result.current.ensure("journal-1");
    });
    await act(async () => {
      await result.current.discard(false);
    });
    expect(api.deleteMoment).toHaveBeenCalledWith("moment-new");
    expect(api.deleteEntry).not.toHaveBeenCalled();
  });

  it("never cleans up a Moment this session did not create", async () => {
    const existing = {
      id: "moment-1",
      entry: { id: "entry-1" },
    } as MomentResponse;
    const { result } = renderHook(() =>
      useEntryDraft({ ...options, moment: existing }),
    );
    await act(async () => {
      await result.current.ensure("journal-1");
      await result.current.discard(false);
    });
    expect(api.deleteMoment).not.toHaveBeenCalled();
    expect(api.deleteEntry).not.toHaveBeenCalled();
  });

  it("refuses a recovered identity when the entry already exists", async () => {
    // A local draft records the Moment it belongs to. Recovering one for a
    // SAVED entry hands back that entry's own Moment id, and owning it would
    // let Cancel delete real writing.
    const existing = {
      id: "moment-1",
      entry: { id: "entry-1" },
    } as MomentResponse;
    const { result } = renderHook(() =>
      useEntryDraft({
        ...options,
        moment: existing,
        initialIdentity: { momentId: "moment-1", entryId: "entry-1" },
      }),
    );
    expect(result.current.draft).toBeNull();
    await act(async () => {
      await result.current.discard(false);
    });
    expect(api.deleteMoment).not.toHaveBeenCalled();
    expect(api.deleteEntry).not.toHaveBeenCalled();
  });

  it("owns a recovered identity for a new entry, and cleans it up", async () => {
    const { result } = renderHook(() =>
      useEntryDraft({
        ...options,
        initialIdentity: { momentId: "moment-9", entryId: "entry-9" },
      }),
    );
    let identity: unknown;
    await act(async () => {
      identity = await result.current.ensure("journal-1");
    });
    // No second Moment: the recovered one already owns the media.
    expect(identity).toEqual({ momentId: "moment-9", entryId: "entry-9" });
    expect(api.createMoment).not.toHaveBeenCalled();
    await act(async () => {
      await result.current.discard(false);
    });
    expect(api.deleteMoment).toHaveBeenCalledWith("moment-9");
  });

  it("forgets the draft after a successful save so cancel cannot delete it", async () => {
    const { result } = renderHook(() => useEntryDraft(options));
    await act(async () => {
      await result.current.ensure("journal-1");
    });
    act(() => result.current.adopt());
    await act(async () => {
      await result.current.discard(false);
    });
    expect(api.deleteMoment).not.toHaveBeenCalled();
  });

  it("survives a failed cleanup without throwing", async () => {
    vi.mocked(api.deleteMoment).mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => useEntryDraft(options));
    await act(async () => {
      await result.current.ensure("journal-1");
    });
    await act(async () => {
      await expect(result.current.discard(false)).resolves.toBeUndefined();
    });
  });
});
