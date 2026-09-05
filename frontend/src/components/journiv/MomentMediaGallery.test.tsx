import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client/api";
import type {
  MomentMediaResponse,
  MomentResponse,
} from "../../api/generated/types.gen";
import { createAppQueryClient } from "../../app/queryClient";
import { MomentMediaGallery } from "./MomentMediaGallery";
import { useMomentMedia } from "./useMomentMedia";

vi.mock("../../api/client/api", () => ({ api: { momentMedia: vi.fn() } }));

const moment = (mediaCount: number) =>
  ({
    id: "moment-1",
    user_id: "user-1",
    logged_at_utc: "2026-08-17T18:04:00Z",
    logged_date_tz: "2026-08-17",
    logged_timezone: "America/Los_Angeles",
    media_count: mediaCount,
    is_pinned: false,
    mood_activity: [],
    tags: [],
    people: [],
    media: [],
  }) as unknown as MomentResponse;

const image = (overrides: Partial<MomentMediaResponse> = {}) =>
  ({
    id: "media-1",
    created_at: "2026-08-17T18:05:00Z",
    media_type: "image",
    mime_type: "image/jpeg",
    upload_status: "completed",
    width: 1600,
    height: 1067,
    alt_text: "Torii gates in the rain",
    signed_url: "/api/v1/media/media-1/signed?sig=abc",
    moment_id: "moment-1",
    ...overrides,
  }) as MomentMediaResponse;

/** Exercises the real hook so query, expiry and retry behaviour are covered. */
function Harness({
  moment: node,
  excludePaths,
  renderItemAction,
  variant,
}: {
  moment: MomentResponse;
  excludePaths?: ReadonlySet<string>;
  renderItemAction?: (item: MomentMediaResponse) => ReactNode;
  variant?: "content" | "tray";
}) {
  const media = useMomentMedia(node.id, (node.media_count ?? 0) > 0);
  return (
    <MomentMediaGallery
      moment={node}
      media={media}
      variant={variant}
      excludePaths={excludePaths}
      renderItemAction={renderItemAction}
    />
  );
}

function renderMedia(
  node: MomentResponse,
  excludePaths?: ReadonlySet<string>,
  renderItemAction?: (item: MomentMediaResponse) => ReactNode,
) {
  const client = createAppQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  return render(
    <QueryClientProvider client={client}>
      <Harness
        moment={node}
        excludePaths={excludePaths}
        renderItemAction={renderItemAction}
      />
    </QueryClientProvider>,
  );
}

function renderTray(
  node: MomentResponse,
  excludePaths?: ReadonlySet<string>,
  renderItemAction?: (item: MomentMediaResponse) => ReactNode,
) {
  const client = createAppQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  return render(
    <QueryClientProvider client={client}>
      <Harness
        moment={node}
        variant="tray"
        excludePaths={excludePaths}
        renderItemAction={renderItemAction}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("MomentMediaGallery", () => {
  it("does not query at all when the Moment has no media", () => {
    const { container } = renderMedia(moment(0));
    expect(api.momentMedia).not.toHaveBeenCalled();
    expect(container.innerHTML).toBe("");
  });

  it("renders alt_text as alt text and never as visible caption text", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([image()]);
    renderMedia(moment(1));
    const img = await screen.findByAltText("Torii gates in the rain");
    expect(img.getAttribute("src")).toBe(
      "/api/v1/media/media-1/signed?sig=abc",
    );
    expect(screen.queryByText("Torii gates in the rain")).toBeNull();
  });

  it("reserves each item's own aspect-ratio box so prose cannot jump", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([image()]);
    const { container } = renderMedia(moment(1));
    await screen.findByAltText("Torii gates in the rain");
    const frame = container.querySelector(".jv-media__frame") as HTMLElement;
    expect(frame.style.aspectRatio).toBe("1600 / 1067");
  });

  it("never crops: every item keeps its own ratio, however many there are", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([
      image(),
      image({ id: "media-2", alt_text: "Second", width: 900, height: 1600 }),
    ]);
    const { container } = renderMedia(moment(2));
    await screen.findByAltText("Second");
    const frames = [
      ...container.querySelectorAll(".jv-media__frame"),
    ] as HTMLElement[];
    expect(frames.map((frame) => frame.style.aspectRatio)).toEqual([
      "1600 / 1067",
      "900 / 1600",
    ]);
    for (const img of container.querySelectorAll("img")) {
      expect(img.className).toContain("jv-media__element--contain");
    }
  });

  it("omits media that the prose already renders inline", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([
      image(),
      image({
        id: "media-2",
        alt_text: "Gallery only",
        signed_url: "/api/v1/media/media-2/signed?sig=zzz",
      }),
    ]);
    // Matched on path: the document's signature differs from the gallery's.
    renderMedia(moment(2), new Set(["/api/v1/media/media-1/signed"]));
    expect(await screen.findByAltText("Gallery only")).toBeTruthy();
    expect(screen.queryByAltText("Torii gates in the rain")).toBeNull();
  });

  it.each(["pending", "processing"] as const)(
    "shows %s media explicitly",
    async (status) => {
      vi.mocked(api.momentMedia).mockResolvedValue([
        image({ upload_status: status, signed_url: null }),
      ]);
      renderMedia(moment(1));
      expect(await screen.findByText("Processing")).toBeTruthy();
      expect(screen.queryByRole("img")).toBeNull();
    },
  );

  it("shows an explicit state for failed processing", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([
      image({ upload_status: "failed" }),
    ]);
    renderMedia(moment(1));
    expect(await screen.findByText("Photo unavailable")).toBeTruthy();
  });

  it("says so quietly and offers a retry when the media request fails", async () => {
    vi.mocked(api.momentMedia).mockRejectedValueOnce(new Error("network"));
    const { container } = renderMedia(moment(1));
    expect(await screen.findByText("Media couldn’t be loaded")).toBeTruthy();
    // Non-blocking: an inline notice, not a pane-filling error state.
    expect(container.querySelector(".jv-status")).toBeNull();

    vi.mocked(api.momentMedia).mockResolvedValue([image()]);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByAltText("Torii gates in the rain")).toBeTruthy();
  });

  it("renders nothing when the authoritative list is empty despite a stale count", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([]);
    const { container } = renderMedia(moment(2));
    await waitFor(() => expect(api.momentMedia).toHaveBeenCalled());
    // media_count is denormalised on the Moment row; the list wins. There is
    // nothing to retry, so no failure notice is shown either.
    await waitFor(() =>
      expect(container.querySelector(".jv-media__frame")).toBeNull(),
    );
    expect(screen.queryByText("Media couldn’t be loaded")).toBeNull();
  });

  it("keeps the rest of a gallery when one item permanently fails", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([
      image({ id: "good", alt_text: "Loads fine" }),
      image({ id: "bad", alt_text: "Never loads" }),
    ]);
    renderMedia(moment(2));

    fireEvent.error(await screen.findByAltText("Never loads"));
    await waitFor(() => expect(api.momentMedia).toHaveBeenCalledTimes(2));
    fireEvent.error(await screen.findByAltText("Never loads"));

    expect(await screen.findByText("Photo unavailable")).toBeTruthy();
    expect(screen.getByAltText("Loads fine")).toBeTruthy();
    // Bounded: a second failure is genuine, not retried forever.
    expect(api.momentMedia).toHaveBeenCalledTimes(2);
  });

  it("re-signs proactively when a URL has already expired", async () => {
    vi.mocked(api.momentMedia)
      .mockResolvedValueOnce([
        image({ signed_url_expires_at: Math.floor(Date.now() / 1000) - 60 }),
      ])
      .mockResolvedValue([image({ signed_url: "/fresh" })]);
    renderMedia(moment(1));
    // Driven by the expiry timestamp, not by the query staleTime.
    await waitFor(() => expect(api.momentMedia).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(
        screen.getByAltText("Torii gates in the rain").getAttribute("src"),
      ).toBe("/fresh"),
    );
  });

  it("attempts to re-sign an expired response only once", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([
      image({ signed_url_expires_at: Math.floor(Date.now() / 1000) - 60 }),
    ]);
    renderMedia(moment(1));

    await waitFor(() => expect(api.momentMedia).toHaveBeenCalledTimes(2));
    await Promise.resolve();
    await Promise.resolve();
    expect(api.momentMedia).toHaveBeenCalledTimes(2);
  });

  it("allows a new Moment its own expired-URL re-sign attempt", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([
      image({ signed_url_expires_at: Math.floor(Date.now() / 1000) - 60 }),
    ]);
    const client = createAppQueryClient();
    client.setDefaultOptions({ queries: { retry: false } });
    const first = moment(1);
    const view = render(
      <QueryClientProvider client={client}>
        <Harness moment={first} />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(api.momentMedia).toHaveBeenCalledTimes(2));
    view.rerender(
      <QueryClientProvider client={client}>
        <Harness moment={{ ...first, id: "moment-2" }} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(api.momentMedia).toHaveBeenCalledTimes(4));
  });

  it("renders a per-item action when the consumer supplies one", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([
      image(),
      image({
        id: "media-2",
        alt_text: "Second",
        signed_url: "/api/v1/media/media-2/signed?sig=zzz",
      }),
    ]);
    renderMedia(moment(2), undefined, (item) => (
      <button type="button">Add {item.id} to entry</button>
    ));
    // One control per gallery item, wired to that item.
    expect(
      await screen.findByRole("button", { name: "Add media-1 to entry" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Add media-2 to entry" }),
    ).toBeTruthy();
  });

  it("stops offering an item, and its action, once it is inline in the prose", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([
      image(),
      image({
        id: "media-2",
        alt_text: "Still attached",
        signed_url: "/api/v1/media/media-2/signed?sig=zzz",
      }),
    ]);
    // media-1 has been placed inline by the editor, so its path is excluded.
    // The gallery must drop both the item and its "Add to entry" control,
    // leaving the still-attached item untouched.
    renderMedia(
      moment(2),
      new Set(["/api/v1/media/media-1/signed"]),
      (item) => <button type="button">Add {item.id}</button>,
    );
    expect(await screen.findByAltText("Still attached")).toBeTruthy();
    expect(screen.queryByAltText("Torii gates in the rain")).toBeNull();
    expect(screen.queryByRole("button", { name: "Add media-1" })).toBeNull();
    expect(screen.getByRole("button", { name: "Add media-2" })).toBeTruthy();
  });

  it("keeps a non-previewable kind visible as a plain attachment with no action", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([
      image(),
      image({
        id: "media-x",
        media_type: "unknown",
        alt_text: "Voice memo.m4a",
        signed_url: "/api/v1/media/media-x/signed?sig=q",
      }),
    ]);
    // The consumer offers its action only for kinds it can act on.
    renderMedia(moment(2), undefined, (item) =>
      item.media_type === "image" ? (
        <button type="button">Add {item.id}</button>
      ) : null,
    );
    // The unknown item is still shown — never dropped — as an "Attachment".
    expect(await screen.findAllByText("Attachment")).toHaveLength(1);
    // ...but it gets no "Add to entry" control, and the image still does.
    expect(screen.getByRole("button", { name: "Add media-1" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add media-x" })).toBeNull();
  });
});

describe("MomentMediaGallery · tray variant", () => {
  const action = (item: MomentMediaResponse) => (
    <button type="button">Add {item.id}</button>
  );

  it("frames the media as attachments, not entry content", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([image()]);
    const { container } = renderTray(moment(1), undefined, action);

    // Panel label + hint make it read as attachments, not the entry body.
    expect(await screen.findByText("On this moment")).toBeTruthy();
    expect(screen.getByText(/aren’t in your entry yet/i)).toBeTruthy();
    // Cropped thumbnail tile, not the full-size content frame.
    const tile = await screen.findByAltText("Torii gates in the rain");
    expect(tile.closest(".jv-media__tile")).toBeTruthy();
    expect(container.querySelector(".jv-media__frame")).toBeNull();
    expect(screen.getByRole("button", { name: "Add media-1" })).toBeTruthy();
  });

  it("marks an added item instead of hiding it, and drops its action", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([
      image({ alt_text: "Kept" }),
      image({
        id: "media-2",
        alt_text: "Added already",
        signed_url: "/api/v1/media/media-2/signed?sig=z",
      }),
    ]);
    const { container } = renderTray(
      moment(2),
      new Set(["/api/v1/media/media-2/signed"]),
      action,
    );

    // Both tiles are on screen — the added one is not removed.
    expect(await screen.findByAltText("Added already")).toBeTruthy();
    expect(screen.getByAltText("Kept")).toBeTruthy();
    const addedTile = screen
      .getByAltText("Added already")
      .closest(".jv-media__tile") as HTMLElement;
    expect(addedTile.className).toContain("jv-media__tile--added");
    expect(container.querySelector(".jv-media__tile-badge")).toBeTruthy();
    // Only the not-yet-added item keeps an action.
    expect(screen.getByRole("button", { name: "Add media-1" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add media-2" })).toBeNull();
  });

  it("collapses to a summary once every attachment has been added", async () => {
    vi.mocked(api.momentMedia).mockResolvedValue([
      image(),
      image({
        id: "media-2",
        signed_url: "/api/v1/media/media-2/signed?sig=z",
      }),
    ]);
    renderTray(
      moment(2),
      new Set(["/api/v1/media/media-1/signed", "/api/v1/media/media-2/signed"]),
      action,
    );

    expect(
      await screen.findByText("2 attachments added to your entry"),
    ).toBeTruthy();
    // Grid is hidden until expanded.
    expect(screen.queryByRole("img")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show" }));
    expect(await screen.findAllByRole("img")).toHaveLength(2);
  });
});
