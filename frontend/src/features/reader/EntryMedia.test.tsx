import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client/api";
import type {
  MomentMediaResponse,
  MomentResponse,
} from "../../api/generated/types.gen";
import { createAppQueryClient } from "../../app/queryClient";
import { EntryMedia } from "./EntryMedia";
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
}: {
  moment: MomentResponse;
  excludePaths?: ReadonlySet<string>;
}) {
  const media = useMomentMedia(node.id, (node.media_count ?? 0) > 0);
  return <EntryMedia moment={node} media={media} excludePaths={excludePaths} />;
}

function renderMedia(node: MomentResponse, excludePaths?: ReadonlySet<string>) {
  const client = createAppQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  return render(
    <QueryClientProvider client={client}>
      <Harness moment={node} excludePaths={excludePaths} />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("EntryMedia", () => {
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
});
