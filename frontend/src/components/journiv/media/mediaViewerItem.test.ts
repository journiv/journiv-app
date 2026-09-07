import { describe, expect, it } from "vitest";
import type {
  MediaLibraryItem,
  MomentMediaResponse,
} from "../../../api/generated/types.gen";
import {
  libraryMediaToViewerItems,
  momentMediaToViewerItems,
} from "./mediaViewerItem";

const moment = (o: Partial<MomentMediaResponse>): MomentMediaResponse =>
  ({
    id: "m1",
    created_at: "2026-01-01T00:00:00Z",
    media_type: "image",
    mime_type: "image/jpeg",
    upload_status: "completed",
    signed_url: "/api/v1/media/m1/signed?sig=a",
    moment_id: "mom",
    ...o,
  }) as MomentMediaResponse;

describe("momentMediaToViewerItems", () => {
  it("keeps ready images and videos, in order, and drops audio and unknown", () => {
    const items = momentMediaToViewerItems([
      moment({ id: "img", media_type: "image" }),
      moment({ id: "aud", media_type: "audio" }),
      moment({
        id: "vid",
        media_type: "video",
        mime_type: "video/mp4",
        signed_url: "/api/v1/media/vid/signed?sig=b",
      }),
      moment({ id: "weird", media_type: "unknown" }),
    ]);
    expect(items.map((i) => i.id)).toEqual(["img", "vid"]);
    expect(items[0].kind).toBe("image");
    expect(items[1].kind).toBe("video");
  });

  it("excludes media that is not ready to show", () => {
    const items = momentMediaToViewerItems([
      moment({ id: "pending", upload_status: "pending" }),
      moment({ id: "processing", upload_status: "processing" }),
      moment({ id: "failed", upload_status: "failed" }),
      moment({ id: "noUrl", signed_url: null }),
      moment({ id: "ready" }),
      moment({ id: "legacy", upload_status: undefined }),
    ]);
    expect(items.map((i) => i.id)).toEqual(["ready", "legacy"]);
  });

  it("carries alt, filename and dimensions through", () => {
    const [item] = momentMediaToViewerItems([
      moment({
        id: "x",
        alt_text: "a lake",
        original_filename: "lake.jpg",
        width: 1600,
        height: 900,
      }),
    ]);
    expect(item).toMatchObject({
      alt: "a lake",
      filename: "lake.jpg",
      width: 1600,
      height: 900,
      src: "/api/v1/media/m1/signed?sig=a",
    });
  });

  it("returns an empty array for no items", () => {
    expect(momentMediaToViewerItems(undefined)).toEqual([]);
  });
});

describe("libraryMediaToViewerItems", () => {
  it("maps ready library items and has no filename", () => {
    const lib = [
      {
        id: "L1",
        moment_id: "mom",
        media_type: "image",
        mime_type: "image/png",
        upload_status: "completed",
        signed_url: "/api/v1/media/L1/signed?sig=z",
        alt_text: "x",
        width: 10,
        height: 20,
      },
      {
        id: "L2",
        moment_id: "mom",
        media_type: "video",
        mime_type: "video/mp4",
        upload_status: "processing",
        signed_url: null,
      },
    ] as MediaLibraryItem[];
    const items = libraryMediaToViewerItems(lib);
    expect(items.map((i) => i.id)).toEqual(["L1"]);
    expect(items[0]).toMatchObject({
      kind: "image",
      src: "/api/v1/media/L1/signed?sig=z",
      filename: undefined,
    });
  });
});
