import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client/api";
import { useQuickLogMoment } from "./useQuickLogMoment";

vi.mock("../../api/client/api", () => ({
  api: {
    createMoment: vi.fn(),
    deleteMoment: vi.fn(),
  },
}));

const createMoment = vi.mocked(api.createMoment);
const deleteMoment = vi.mocked(api.deleteMoment);

const args = {
  loggedAtUtc: "2026-09-05T09:00:00.000Z",
  loggedTimezone: "Europe/London",
};

beforeEach(() => {
  vi.clearAllMocks();
  createMoment.mockResolvedValue({ id: "m-new" } as never);
  deleteMoment.mockResolvedValue(undefined as never);
});

describe("useQuickLogMoment", () => {
  it("creates the moment once and reuses it across concurrent ensure calls", async () => {
    const { result } = renderHook(() => useQuickLogMoment(args));

    let ids: string[] = [];
    await act(async () => {
      ids = await Promise.all([
        result.current.ensure(),
        result.current.ensure(),
        result.current.ensure(),
      ]);
    });

    expect(ids).toEqual(["m-new", "m-new", "m-new"]);
    expect(createMoment).toHaveBeenCalledTimes(1);
    expect(createMoment).toHaveBeenCalledWith({
      logged_at_utc: args.loggedAtUtc,
      logged_timezone: args.loggedTimezone,
    });
    await waitFor(() => expect(result.current.momentId).toBe("m-new"));
  });

  it("deletes the row on discard when no media was kept", async () => {
    const { result } = renderHook(() => useQuickLogMoment(args));
    await act(async () => {
      await result.current.ensure();
    });

    await act(async () => {
      await result.current.discard(false);
    });

    expect(deleteMoment).toHaveBeenCalledWith("m-new");
    expect(result.current.momentId).toBeNull();
  });

  it("keeps the row on discard when media should be kept", async () => {
    const { result } = renderHook(() => useQuickLogMoment(args));
    await act(async () => {
      await result.current.ensure();
    });

    await act(async () => {
      await result.current.discard(true);
    });

    expect(deleteMoment).not.toHaveBeenCalled();
  });

  it("cleans up a moment that finishes creating after discard was requested", async () => {
    let resolveCreate: (value: { id: string }) => void = () => {};
    createMoment.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveCreate = resolve;
      }) as never,
    );
    const { result } = renderHook(() => useQuickLogMoment(args));

    let ensurePromise: Promise<string> = Promise.resolve("");
    act(() => {
      ensurePromise = result.current.ensure();
    });
    await act(async () => {
      await result.current.discard(false);
    });

    await act(async () => {
      resolveCreate({ id: "m-late" });
      await ensurePromise;
    });

    expect(deleteMoment).toHaveBeenCalledWith("m-late");
    expect(result.current.momentId).toBeNull();
  });

  it("adopt stops owning the row so a later discard is a no-op", async () => {
    const { result } = renderHook(() => useQuickLogMoment(args));
    await act(async () => {
      await result.current.ensure();
    });

    act(() => result.current.adopt());
    await act(async () => {
      await result.current.discard(false);
    });

    expect(deleteMoment).not.toHaveBeenCalled();
  });

  it("never touches the server when an existing momentId is supplied", async () => {
    const { result } = renderHook(() =>
      useQuickLogMoment({ ...args, momentId: "m-existing" }),
    );

    await act(async () => {
      expect(await result.current.ensure()).toBe("m-existing");
      await result.current.discard(false);
    });

    expect(createMoment).not.toHaveBeenCalled();
    expect(deleteMoment).not.toHaveBeenCalled();
  });
});
