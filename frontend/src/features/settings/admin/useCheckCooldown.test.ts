import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useCheckCooldown } from "./useCheckCooldown";

afterEach(() => {
  vi.useRealTimers();
});

describe("useCheckCooldown", () => {
  it("measures the countdown from begin(), not from mount", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useCheckCooldown());
    expect(result.current.seconds).toBe(0);

    // The screen sat open for five minutes before the rate limit came back.
    act(() => {
      vi.advanceTimersByTime(5 * 60_000);
    });
    act(() => {
      result.current.begin(120);
    });

    // 120s exactly — not 120 plus the stale five minutes since mount.
    expect(result.current.seconds).toBe(120);
  });

  it("ticks down every second and clears itself when the window elapses", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useCheckCooldown());

    act(() => {
      result.current.begin(3);
    });
    expect(result.current.seconds).toBe(3);

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(result.current.seconds).toBe(1);

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.seconds).toBe(0);
  });

  it("clear() ends the cooldown immediately", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useCheckCooldown());

    act(() => {
      result.current.begin(60);
    });
    expect(result.current.seconds).toBe(60);

    act(() => {
      result.current.clear();
    });
    expect(result.current.seconds).toBe(0);
  });
});
