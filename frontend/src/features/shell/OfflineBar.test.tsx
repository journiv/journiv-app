import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { queryKeys } from "../../api/query/keys";
import { OfflineBar } from "./OfflineBar";

describe("OfflineBar", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("refreshes the relative last-sync time while it remains mounted", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-17T12:00:00Z"));
    const queryClient = new QueryClient();
    queryClient.setQueryData(queryKeys.journals, []);

    render(
      <QueryClientProvider client={queryClient}>
        <OfflineBar />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("status").textContent).toContain(
      "less than a minute ago",
    );
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(screen.getByRole("status").textContent).toContain("1 minute ago");
  });
});
