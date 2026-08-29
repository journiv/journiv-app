import "fake-indexeddb/auto";
import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { QuillDelta } from "../../api/generated/types.gen";
import { createAppQueryClient } from "../../app/queryClient";
import type { DurableDraftDelta } from "./draftCanonical";
import { draftRepository, type EditorDraftV1 } from "./draftRepository";
import {
  type DraftRecoveryState,
  useDraftRecovery,
  type UseDraftRecoveryOptions,
} from "./useDraftRecovery";

vi.mock("../../api/client/api", () => ({
  api: { momentMedia: vi.fn().mockResolvedValue([]) },
}));

const durable = (text: string) =>
  ({ ops: [{ insert: text }] }) as unknown as DurableDraftDelta;

const record = (over: Partial<EditorDraftV1>): EditorDraftV1 => ({
  key: "user-a:entry:entry-1",
  userId: "user-a",
  entryId: "entry-1",
  journalId: "journal-1",
  title: "",
  contentDelta: durable("Belongs to A\n"),
  modifiedAt: "2026-08-24T11:00:00Z",
  dirty: true,
  ...over,
});

const serverContent = { ops: [{ insert: "On the server\n" }] } as QuillDelta;

function setup(initial: UseDraftRecoveryOptions) {
  const seen: { current: DraftRecoveryState | null } = { current: null };
  let options = initial;

  function Probe() {
    seen.current = useDraftRecovery(options).state;
    return null;
  }

  const client = createAppQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  const view = render(
    <QueryClientProvider client={client}>
      <Probe />
    </QueryClientProvider>,
  );
  return {
    seen,
    rerender: (next: Partial<UseDraftRecoveryOptions>) => {
      options = { ...options, ...next };
      view.rerender(
        <QueryClientProvider client={client}>
          <Probe />
        </QueryClientProvider>,
      );
    },
  };
}

const base: UseDraftRecoveryOptions = {
  key: "user-a:entry:entry-1",
  momentId: "moment-1",
  serverContent,
  serverTitle: "",
  serverJournalId: "journal-1",
  serverUpdatedAt: "2026-08-24T08:30:00Z",
  serverLoaded: true,
};

describe("useDraftRecovery and the signed-in identity", () => {
  it("offers a draft that belongs to the current user", async () => {
    await draftRepository.write(record({}));
    const { seen } = setup(base);

    await waitFor(() => expect(seen.current?.phase).toBe("offer"));
  });

  it("never applies a result for one user after the identity becomes another", async () => {
    await draftRepository.write(record({}));
    await draftRepository.write(
      record({
        key: "user-b:entry:entry-1",
        userId: "user-b",
        contentDelta: durable("Belongs to B\n"),
      }),
    );

    // Hold user A's read open, so it can land *after* the identity changes —
    // the exact race a bare "checked" flag would get wrong.
    let releaseA: (value: EditorDraftV1 | null) => void = () => {};
    const read = vi.spyOn(draftRepository, "read").mockImplementationOnce(
      () =>
        new Promise<EditorDraftV1 | null>((resolve) => {
          releaseA = resolve;
        }),
    );

    const { seen, rerender } = setup(base);
    expect(seen.current?.phase).toBe("checking");

    // The account changes before A's read comes back.
    read.mockRestore();
    rerender({ key: "user-b:entry:entry-1" });

    await act(async () => {
      releaseA(record({}));
      await Promise.resolve();
    });

    await waitFor(() => expect(seen.current?.phase).toBe("offer"));
    const offered = seen.current;
    if (offered?.phase !== "offer") throw new Error("expected an offer");
    // B's draft, never A's — and A's writing never appeared even for a frame.
    expect(offered.draft.userId).toBe("user-b");
    expect(JSON.stringify(offered.content)).toContain("Belongs to B");
    expect(JSON.stringify(offered.content)).not.toContain("Belongs to A");
  });

  it("stays on checking rather than showing a stale answer while the key changes", async () => {
    await draftRepository.write(record({}));
    const { seen, rerender } = setup(base);
    await waitFor(() => expect(seen.current?.phase).toBe("offer"));

    // The moment the identity changes, the previous answer stops applying.
    rerender({ key: "user-b:entry:entry-1" });
    expect(seen.current?.phase).toBe("checking");
  });

  it("offers nothing when the new user has no draft", async () => {
    await draftRepository.write(record({}));
    const { seen, rerender } = setup(base);
    await waitFor(() => expect(seen.current?.phase).toBe("offer"));

    rerender({ key: "user-c:entry:entry-1" });
    await waitFor(() => expect(seen.current?.phase).toBe("clear"));
  });
});
