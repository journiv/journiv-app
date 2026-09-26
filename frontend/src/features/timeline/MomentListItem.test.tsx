import { fireEvent, render } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { MomentResponse } from "../../api/generated/types.gen";
import { MomentListItem } from "./MomentListItem";

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    className,
  }: {
    children: ReactNode;
    className: string;
  }) => (
    <a className={className} href="/moment">
      {children}
    </a>
  ),
}));
vi.mock("../../components/journiv/MomentMeta", () => ({
  MomentMeta: () => null,
}));

const moment = (
  media: { media_type: string; signed_thumbnail_url?: string | null }[],
) =>
  ({
    id: "m1",
    user_id: "u1",
    logged_at_utc: "2026-08-17T18:04:00Z",
    logged_date_tz: "2026-08-17",
    logged_timezone: "America/Los_Angeles",
    is_pinned: false,
    note: "A quick thought.",
    mood_activity: [],
    tags: [],
    people: [],
    media_count: media.length,
    media: media.map((item, index) => ({ id: `x${index}`, ...item })),
  }) as unknown as MomentResponse;

const draw = (value: MomentResponse) =>
  render(<MomentListItem moment={value} selected={false} search="" />)
    .container;

describe("MomentListItem attachment tile", () => {
  it.each(["video", "image", "unknown"])(
    "still shows a placeholder tile for a %s without a thumbnail",
    (media_type) => {
      const view = draw(moment([{ media_type, signed_thumbnail_url: null }]));
      const tile = view.querySelector(".jv-moment__media");
      expect(tile?.classList.contains("jv-moment__media--placeholder")).toBe(
        true,
      );
      expect(tile?.querySelector("svg")).not.toBeNull();
      expect(tile?.querySelector("img")).toBeNull();
    },
  );

  it("shows an audio tile when the only attachment is a voice note", () => {
    const view = draw(
      moment([{ media_type: "audio", signed_thumbnail_url: null }]),
    );
    const tile = view.querySelector(".jv-moment__media");
    expect(tile?.classList.contains("jv-moment__media--placeholder")).toBe(
      true,
    );
    expect(tile?.querySelector("svg")).not.toBeNull();
    expect(tile?.querySelector("img")).toBeNull();
    expect(tile?.querySelector(".jv-moment__media-count")).toBeNull();
  });

  it("keeps showing the picture, and says there is audio too", () => {
    const view = draw(
      moment([
        { media_type: "audio", signed_thumbnail_url: null },
        { media_type: "image", signed_thumbnail_url: "https://sig/a.jpg" },
      ]),
    );
    const tile = view.querySelector(".jv-moment__media");
    expect(tile?.querySelector("img")?.getAttribute("src")).toBe(
      "https://sig/a.jpg",
    );
    expect(tile?.querySelector(".jv-moment__media-audio")).not.toBeNull();
    expect(tile?.querySelector(".jv-moment__media-count")?.textContent).toBe(
      "+1",
    );
  });

  it("adds no audio mark to a picture-only tile, and no tile without media", () => {
    const pictures = draw(
      moment([
        { media_type: "image", signed_thumbnail_url: "https://sig/a.jpg" },
      ]),
    );
    expect(pictures.querySelector(".jv-moment__media img")).not.toBeNull();
    expect(pictures.querySelector(".jv-moment__media-audio")).toBeNull();
    expect(draw(moment([])).querySelector(".jv-moment__media")).toBeNull();
  });

  it("falls back to the placeholder when the thumbnail fails to load", () => {
    const view = draw(
      moment([
        { media_type: "video", signed_thumbnail_url: "https://sig/gone.jpg" },
      ]),
    );
    const img = view.querySelector(".jv-moment__media img");
    expect(img).not.toBeNull();
    fireEvent.error(img as Element);
    const tile = view.querySelector(".jv-moment__media");
    expect(tile?.querySelector("img")).toBeNull();
    expect(tile?.querySelector("svg")).not.toBeNull();
    expect(tile?.classList.contains("jv-moment__media--placeholder")).toBe(
      true,
    );
  });

  it("keeps the audio mark and count on a picture that fails to load", () => {
    const view = draw(
      moment([
        { media_type: "audio", signed_thumbnail_url: null },
        { media_type: "image", signed_thumbnail_url: "https://sig/gone.jpg" },
      ]),
    );
    fireEvent.error(view.querySelector(".jv-moment__media img") as Element);
    const tile = view.querySelector(".jv-moment__media");
    expect(tile?.querySelector("img")).toBeNull();
    expect(tile?.querySelector(".jv-moment__media-audio")).not.toBeNull();
    expect(tile?.querySelector(".jv-moment__media-count")?.textContent).toBe(
      "+1",
    );
  });
});
