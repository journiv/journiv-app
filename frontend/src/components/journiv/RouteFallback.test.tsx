import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  DetailPaneFallback,
  ListPaneFallback,
  WorkspacePaneFallback,
} from "./RouteFallback";

/**
 * These render the fallback components in isolation — no router, no
 * Suspense, no chunk timing — because their contract is pure geometry
 * (DESIGN.md "Navigation loading"): the right pane element, the right class,
 * an accessible label, and never the old centred spinner. Whether a real
 * navigation actually shows one of these before its chunk resolves is a
 * bundler/network timing question, out of reach for Vitest+JSDOM; that is
 * covered separately in Playwright (e2e/README.md).
 */
describe("route fallbacks", () => {
  it("ListPaneFallback owns the list pane element with no spinner", () => {
    render(<ListPaneFallback label="Loading journals…" />);
    const status = screen.getByRole("status", { name: "Loading journals…" });
    expect(status.tagName).toBe("SECTION");
    expect(status.classList.contains("jv-shell__list")).toBe(true);
    expect(status.querySelector(".jv-spin")).toBeNull();
  });

  it("DetailPaneFallback never re-declares a pane element", () => {
    render(<DetailPaneFallback label="Loading entry…" />);
    const status = screen.getByRole("status", { name: "Loading entry…" });
    expect(status.classList.contains("jv-route-detail")).toBe(true);
    expect(status.classList.contains("jv-shell__page")).toBe(false);
    expect(status.querySelector(".jv-shell__page")).toBeNull();
    expect(status.querySelector(".jv-spin")).toBeNull();
  });

  it("WorkspacePaneFallback carries the span-two geometry with no spinner", () => {
    render(<WorkspacePaneFallback label="Loading Tags…" />);
    const status = screen.getByRole("status", { name: "Loading Tags…" });
    expect(status.tagName).toBe("SECTION");
    expect(status.classList.contains("jv-route-workspace")).toBe(true);
    expect(status.classList.contains("jv-library")).toBe(false);
    expect(status.querySelector(".jv-spin")).toBeNull();
  });

  it("marks every fallback root so the pane-enter animation skips it", () => {
    // `ListPaneFallback` borrows `.jv-shell__list` for its grid placement, and
    // journiv.css animates that class — without the marker the same screen
    // would fade in twice, once as the placeholder and once as the real pane
    // (DESIGN.md "Navigation loading").
    for (const element of [
      <ListPaneFallback key="l" label="Loading journals…" />,
      <DetailPaneFallback key="d" label="Loading entry…" />,
      <WorkspacePaneFallback key="w" label="Loading Tags…" />,
    ]) {
      const { container, unmount } = render(element);
      expect(
        container.firstElementChild?.classList.contains("jv-route-fallback"),
      ).toBe(true);
      unmount();
    }
  });

  it("never renders the old visible 'Loading X…' status-view text", () => {
    render(<WorkspacePaneFallback label="Loading Tags…" />);
    // The label is accessible-only (aria-label), not visible copy — the
    // geometry itself communicates arrival (DESIGN.md "Navigation loading").
    expect(screen.queryByText("Loading Tags…")).toBeNull();
  });
});
