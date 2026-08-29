import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import {
  MediaUploadError,
  parseSupportedFormats,
  runWithConcurrency,
  uploadErrorMessage,
  uploadMedia,
} from "./mediaUpload";

type Listener = (event: Partial<ProgressEvent>) => void;

class FakeXhr {
  static instances: FakeXhr[] = [];
  status = 0;
  responseText = "";
  body: FormData | null = null;
  headers: Record<string, string> = {};
  method = "";
  url = "";
  private listeners: Record<string, Listener[]> = {};
  upload = {
    listeners: {} as Record<string, Listener[]>,
    addEventListener(type: string, listener: Listener) {
      if (!this.listeners[type]) this.listeners[type] = [];
      this.listeners[type].push(listener);
    },
    emit(type: string, event: Partial<ProgressEvent>) {
      for (const listener of this.listeners[type] ?? []) listener(event);
    },
  };

  constructor() {
    FakeXhr.instances.push(this);
  }
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value;
  }
  addEventListener(type: string, listener: Listener) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(listener);
  }
  send(body: FormData) {
    this.body = body;
  }
  abort() {
    this.emit("abort", {});
  }
  emit(type: string, event: Partial<ProgressEvent> = {}) {
    for (const listener of this.listeners[type] ?? []) listener(event);
  }
}

beforeEach(() => {
  FakeXhr.instances = [];
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
  sessionStore.write({ version: 1, accessToken: "tok", refreshToken: "ref" });
});
afterEach(() => {
  vi.unstubAllGlobals();
  sessionStore.clear();
});

describe("uploadMedia", () => {
  it("posts multipart with the moment id and the bearer token", async () => {
    const file = new File(["x"], "photo.jpg", { type: "image/jpeg" });
    const handle = uploadMedia({
      file,
      momentId: "moment-1",
      altText: "A photo",
    });
    const xhr = FakeXhr.instances[0];

    expect(xhr.method).toBe("POST");
    expect(xhr.url).toBe("/api/v1/media/upload");
    expect(xhr.headers.Authorization).toBe("Bearer tok");
    expect(xhr.body?.get("moment_id")).toBe("moment-1");
    expect(xhr.body?.get("alt_text")).toBe("A photo");
    expect(xhr.body?.get("file")).toBe(file);

    xhr.status = 201;
    xhr.responseText = JSON.stringify({
      id: "media-1",
      upload_status: "pending",
    });
    xhr.emit("load");
    await expect(handle.promise).resolves.toMatchObject({ id: "media-1" });
  });

  it("reports real progress and never invents a percentage", () => {
    const seen: Array<number | undefined> = [];
    uploadMedia({
      file: new File(["x"], "a.jpg"),
      momentId: "m",
      onProgress: (fraction) => seen.push(fraction),
    });
    const xhr = FakeXhr.instances[0];
    xhr.upload.emit("progress", {
      lengthComputable: true,
      loaded: 25,
      total: 100,
    });
    xhr.upload.emit("progress", {
      lengthComputable: false,
      loaded: 0,
      total: 0,
    });
    expect(seen).toEqual([0.25, undefined]);
  });

  it.each([
    [413, "too-large"],
    [415, "unsupported-type"],
    [400, "invalid"],
    [401, "unauthorized"],
    [404, "moment-missing"],
    [500, "server"],
  ])("maps HTTP %i to a human message", async (status, kind) => {
    const handle = uploadMedia({
      file: new File(["x"], "a.jpg"),
      momentId: "m",
    });
    const xhr = FakeXhr.instances[0];
    xhr.status = status;
    xhr.emit("load");
    await expect(handle.promise).rejects.toMatchObject({ kind });
    await handle.promise.catch((error) => {
      // Never surfaces raw backend text.
      expect(uploadErrorMessage(error)).not.toContain("HTTP");
      expect(uploadErrorMessage(error).length).toBeGreaterThan(0);
    });
  });

  it("distinguishes a user abort from a network failure", async () => {
    const handle = uploadMedia({
      file: new File(["x"], "a.jpg"),
      momentId: "m",
    });
    handle.abort();
    await expect(handle.promise).rejects.toMatchObject({ kind: "aborted" });
    expect(uploadErrorMessage(new MediaUploadError("aborted", ""))).toBe(
      "Upload cancelled.",
    );
  });
});

describe("runWithConcurrency", () => {
  it("never exceeds the limit and still runs every task", async () => {
    let active = 0;
    let peak = 0;
    const order: number[] = [];
    const tasks = Array.from({ length: 7 }, (_, index) => async () => {
      active += 1;
      peak = Math.max(peak, active);
      await Promise.resolve();
      order.push(index);
      active -= 1;
    });

    await runWithConcurrency(tasks, 2);
    expect(peak).toBeLessThanOrEqual(2);
    expect(order).toHaveLength(7);
  });
});

describe("parseSupportedFormats", () => {
  it("reads the backend's grouped extension list", () => {
    const parsed = parseSupportedFormats({
      images: [".jpg", ".png"],
      videos: [".mp4"],
      audio: [".m4a"],
    });
    expect(parsed).toEqual({
      images: [".jpg", ".png"],
      videos: [".mp4"],
      audio: [".m4a"],
    });
  });

  it("rejects anything that is not a list of extensions", () => {
    // The endpoint declares no response schema, so the shape is never trusted.
    expect(parseSupportedFormats(null)).toBeNull();
    expect(parseSupportedFormats({ images: "jpg" })).toBeNull();
    expect(parseSupportedFormats({ images: ["jpg", 3] })).toBeNull();
    expect(parseSupportedFormats({})).toBeNull();
  });
});
