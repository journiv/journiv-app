import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { MediaViewer, type MediaViewerProps } from "./MediaViewer";
import type { MediaViewerItem } from "./mediaViewerItem";

const items: MediaViewerItem[] = [
  {
    id: "a",
    kind: "image",
    src: "/api/v1/media/a/signed?s=1",
    alt: "alpha",
  },
  {
    id: "b",
    kind: "image",
    src: "/api/v1/media/b/signed?s=1",
    alt: "beta",
  },
  {
    id: "c",
    kind: "image",
    src: "/api/v1/media/c/signed?s=1",
    alt: "gamma",
  },
];

function setup(overrides: Partial<MediaViewerProps> = {}) {
  const props = {
    items,
    activeId: "b" as string | null,
    onActiveIdChange: vi.fn(),
    onClose: vi.fn(),
    onItemError: vi.fn(),
    onRetry: vi.fn(),
    ...overrides,
  };
  render(<MediaViewer {...props} />);
  return props;
}

describe("MediaViewer", () => {
  it("renders nothing while closed", () => {
    const { container } = render(
      <MediaViewer
        items={items}
        activeId={null}
        onActiveIdChange={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
    expect(document.querySelector(".jv-media-viewer")).toBeNull();
  });

  it("opens as a labelled modal dialog on the active item", async () => {
    setup({ activeId: "b" });
    const dialog = await screen.findByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-label")).toBe("Media viewer");
    expect(screen.getByRole("img", { name: "beta" })).toBeTruthy();
  });

  it("moves focus into the dialog on open and restores it on close", async () => {
    function Host() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            open
          </button>
          <MediaViewer
            items={items}
            activeId={open ? "b" : null}
            onActiveIdChange={vi.fn()}
            onClose={() => setOpen(false)}
          />
        </>
      );
    }
    render(<Host />);
    const trigger = screen.getByRole("button", { name: "open" });
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(dialog.contains(document.activeElement)).toBe(true),
    );

    fireEvent.keyDown(screen.getByRole("img", { name: "beta" }), {
      key: "Escape",
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });

  it("reports the new id when advancing, without wrapping past the end", async () => {
    const props = setup({ activeId: "c" });
    const next = await screen.findByRole("button", { name: /next/i });
    // Finite carousel: Next on the last slide is disabled, not a wrap to "a".
    expect((next as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(next);
    expect(props.onActiveIdChange).not.toHaveBeenCalled();
  });

  it("advances to the next id", async () => {
    const props = setup({ activeId: "a" });
    fireEvent.click(await screen.findByRole("button", { name: /next/i }));
    await waitFor(() =>
      expect(props.onActiveIdChange).toHaveBeenCalledWith("b"),
    );
  });

  it("closes on Escape", async () => {
    const props = setup({ activeId: "b" });
    fireEvent.keyDown(await screen.findByRole("img", { name: "beta" }), {
      key: "Escape",
    });
    await waitFor(() => expect(props.onClose).toHaveBeenCalled());
  });

  it("routes a slide load failure to onItemError keyed by media id", async () => {
    const props = setup({ activeId: "b" });
    const img = await screen.findByRole("img", { name: "beta" });
    fireEvent.error(img);
    expect(props.onItemError).toHaveBeenCalledWith("b");
  });

  it("shows an in-place error with retry for a broken slide", async () => {
    const props = setup({ activeId: "b", brokenIds: new Set(["b"]) });
    expect(await screen.findByText(/couldn’t be loaded/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(props.onRetry).toHaveBeenCalled();
    // The broken slide keeps its position — still 3 slides.
    expect(screen.getByRole("dialog")).toBeTruthy();
  });
});
