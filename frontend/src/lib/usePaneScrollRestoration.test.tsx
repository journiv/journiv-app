import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { usePaneScrollRestoration } from "./usePaneScrollRestoration";

function Pane({ paneKey }: { paneKey: string }) {
  const ref = usePaneScrollRestoration<HTMLDivElement>(paneKey);
  return (
    <div ref={ref} data-testid="pane">
      content
    </div>
  );
}

/**
 * JSDOM has no layout: `scrollTop` is a plain settable number that never
 * clamps and never fires a `scroll` event of its own. A real browser does
 * both, and that pair is the whole hazard this hook has to survive — the
 * clamp destroys the target, and the event it fires would write the clamped
 * value back over the saved one. `ClampingPane` stands the browser behaviour
 * in so the regression is reachable from Vitest.
 *
 * The scheduled dispatch matters as much as the clamp: a browser fires
 * `scroll` at the next rendering step, never synchronously inside the
 * assignment. Dispatching it inline would let an implementation that attaches
 * its listener *after* its first restore miss the clamp entirely and pass a
 * test it should fail.
 */
function ClampingPane({
  paneKey,
  maxScroll,
  isLoading = true,
}: {
  paneKey: string;
  maxScroll: { current: number };
  isLoading?: boolean;
}) {
  const ref = usePaneScrollRestoration<HTMLDivElement>(paneKey, isLoading);
  return (
    <div
      data-testid="pane"
      ref={(el) => {
        ref.current = el;
        if (!el) return;
        if (Object.getOwnPropertyDescriptor(el, "scrollTop")) return;
        let value = 0;
        Object.defineProperty(el, "scrollTop", {
          configurable: true,
          get: () => value,
          set: (next: number) => {
            const clamped = Math.max(0, Math.min(next, maxScroll.current));
            if (clamped === value) return;
            value = clamped;
            setTimeout(() => el.dispatchEvent(new Event("scroll")), 0);
          },
        });
      }}
    >
      content
    </div>
  );
}

describe("usePaneScrollRestoration", () => {
  it("restores a pane's scroll position across an unmount/remount with the same key", () => {
    const first = render(<Pane paneKey="pane-a" />);
    fireEvent.scroll(first.getByTestId("pane"), {
      target: { scrollTop: 240 },
    });
    first.unmount();

    const second = render(<Pane paneKey="pane-a" />);
    expect(second.getByTestId("pane").scrollTop).toBe(240);
  });

  it("never leaks one pane's position onto a different key", () => {
    const first = render(<Pane paneKey="pane-b" />);
    fireEvent.scroll(first.getByTestId("pane"), {
      target: { scrollTop: 500 },
    });
    first.unmount();

    const other = render(<Pane paneKey="pane-c" />);
    expect(other.getByTestId("pane").scrollTop).toBe(0);
  });

  it("keeps the saved offset when the remounted pane is still too short, and lands on it once content arrives", async () => {
    const first = render(<Pane paneKey="pane-d" />);
    fireEvent.scroll(first.getByTestId("pane"), {
      target: { scrollTop: 800 },
    });
    first.unmount();

    // Remount onto a skeleton: the browser clamps the restore and fires a
    // scroll event for the clamp. If that event were recorded, 800 would be
    // replaced by 120 and the position would be lost for good.
    const maxScroll = { current: 120 };
    const second = render(
      <ClampingPane paneKey="pane-d" maxScroll={maxScroll} />,
    );
    const pane = second.getByTestId("pane");
    expect(pane.scrollTop).toBe(120);
    // Let the clamp's scroll event land before the content grows, so the test
    // exercises the ordering a browser actually produces.
    await waitFor(() => expect(pane.scrollTop).toBe(120));

    // The query resolves and real rows replace the skeleton.
    maxScroll.current = 2000;
    pane.appendChild(document.createElement("p"));
    await waitFor(() => expect(pane.scrollTop).toBe(800));
  });

  it("keeps restoring when rows arrive after the former fixed deadline", async () => {
    vi.useFakeTimers();
    try {
      const first = render(<Pane paneKey="pane-delayed" />);
      fireEvent.scroll(first.getByTestId("pane"), {
        target: { scrollTop: 800 },
      });
      first.unmount();

      const maxScroll = { current: 120 };
      const second = render(
        <ClampingPane paneKey="pane-delayed" maxScroll={maxScroll} />,
      );
      const pane = second.getByTestId("pane");

      act(() => vi.advanceTimersByTime(1001));
      maxScroll.current = 2000;
      await act(async () => {
        pane.appendChild(document.createElement("p"));
      });

      expect(pane.scrollTop).toBe(800);
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops after loading completes when the saved offset is no longer reachable", async () => {
    const first = render(<Pane paneKey="pane-shorter" />);
    fireEvent.scroll(first.getByTestId("pane"), {
      target: { scrollTop: 800 },
    });
    first.unmount();

    const maxScroll = { current: 120 };
    const second = render(
      <ClampingPane paneKey="pane-shorter" maxScroll={maxScroll} />,
    );
    const pane = second.getByTestId("pane");
    second.rerender(
      <ClampingPane
        paneKey="pane-shorter"
        maxScroll={maxScroll}
        isLoading={false}
      />,
    );

    maxScroll.current = 2000;
    pane.appendChild(document.createElement("p"));
    await waitFor(() => expect(pane.scrollTop).toBe(120));

    fireEvent.scroll(pane, { target: { scrollTop: 80 } });
    second.unmount();
    const third = render(<Pane paneKey="pane-shorter" />);
    expect(third.getByTestId("pane").scrollTop).toBe(80);
  });

  it("stops restoring once the reader scrolls for themselves", async () => {
    const first = render(<Pane paneKey="pane-e" />);
    fireEvent.scroll(first.getByTestId("pane"), {
      target: { scrollTop: 800 },
    });
    first.unmount();

    const maxScroll = { current: 120 };
    const second = render(
      <ClampingPane paneKey="pane-e" maxScroll={maxScroll} />,
    );
    const pane = second.getByTestId("pane");
    fireEvent.wheel(pane);

    maxScroll.current = 2000;
    pane.appendChild(document.createElement("p"));
    // Still where the reader left it — restoration does not yank them back.
    await waitFor(() => expect(pane.scrollTop).toBe(120));
  });
});
