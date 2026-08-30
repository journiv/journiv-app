import { sessionStore } from "../../api/auth/session";
import type { MomentMediaResponse } from "../../api/generated/types.gen";

/**
 * Multipart media upload, deliberately isolated from the generated Fetch client.
 *
 * `fetch` cannot report upload progress and its abort story is coarser than we
 * want for a large video on a phone, so this one endpoint uses XMLHttpRequest.
 * Nothing else in the application changes transport, and no Axios is
 * introduced. If a future platform gives `fetch` real upload progress, only
 * this file needs to change.
 */

export type UploadErrorKind =
  | "unsupported-type"
  | "too-large"
  | "invalid"
  | "unauthorized"
  | "moment-missing"
  | "network"
  | "server"
  | "aborted";

export class MediaUploadError extends Error {
  readonly kind: UploadErrorKind;
  constructor(kind: UploadErrorKind, message: string) {
    super(message);
    this.name = "MediaUploadError";
    this.kind = kind;
  }
}

/** Human messages. The backend's own text is never shown to the reader. */
const MESSAGES: Record<UploadErrorKind, string> = {
  "unsupported-type": "That file type isn’t supported.",
  "too-large": "That file is too large to upload.",
  invalid: "That file couldn’t be read.",
  unauthorized: "Your session expired. Sign in and try again.",
  "moment-missing": "This moment is no longer available.",
  network: "Upload failed. Check your connection and try again.",
  server: "Upload failed. Try again in a moment.",
  aborted: "Upload cancelled.",
};

function kindForStatus(status: number): UploadErrorKind {
  if (status === 413) return "too-large";
  if (status === 415) return "unsupported-type";
  if (status === 400 || status === 422) return "invalid";
  if (status === 401 || status === 403) return "unauthorized";
  if (status === 404) return "moment-missing";
  if (status === 0) return "network";
  return "server";
}

export function uploadErrorMessage(error: unknown): string {
  if (error instanceof MediaUploadError) return MESSAGES[error.kind];
  return MESSAGES.server;
}

/**
 * Accepted media formats, grouped by kind.
 *
 * `GET /media/formats` declares no response model in the OpenAPI document
 * (`200: unknown`), so the shape is validated here rather than trusted. If the
 * backend ever gains a schema, delete this and use the generated type.
 */
export type SupportedMediaFormats = {
  images: string[];
  videos: string[];
  audio: string[];
};

export function parseSupportedFormats(
  value: unknown,
): SupportedMediaFormats | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const list = (key: string) =>
    Array.isArray(record[key])
      ? (record[key] as unknown[]).filter(
          (item): item is string =>
            typeof item === "string" && item.startsWith("."),
        )
      : [];
  const formats = {
    images: list("images"),
    videos: list("videos"),
    audio: list("audio"),
  };
  const total =
    formats.images.length + formats.videos.length + formats.audio.length;
  return total > 0 ? formats : null;
}

export type UploadHandle = {
  promise: Promise<MomentMediaResponse>;
  /** User-initiated cancellation; resolves as an `aborted` error, not a failure. */
  abort: () => void;
};

const UPLOAD_TIMEOUT_MS = 60_000;

export function uploadMedia({
  file,
  momentId,
  altText,
  onProgress,
}: {
  file: File;
  momentId: string;
  altText?: string;
  /** 0..1, or undefined when the browser cannot report real progress. */
  onProgress?: (fraction: number | undefined) => void;
}): UploadHandle {
  const request = new XMLHttpRequest();
  let aborted = false;

  const promise = new Promise<MomentMediaResponse>((resolve, reject) => {
    const body = new FormData();
    body.append("file", file);
    body.append("moment_id", momentId);
    if (altText) body.append("alt_text", altText);

    request.open("POST", "/api/v1/media/upload");
    request.timeout = UPLOAD_TIMEOUT_MS;
    const session = sessionStore.read();
    if (session) {
      request.setRequestHeader(
        "Authorization",
        `Bearer ${session.accessToken}`,
      );
    }

    request.upload.addEventListener("progress", (event) => {
      // Never invent a percentage: report undefined when length is unknown.
      onProgress?.(
        event.lengthComputable ? event.loaded / event.total : undefined,
      );
    });

    request.addEventListener("load", () => {
      if (request.status >= 200 && request.status < 300) {
        try {
          resolve(JSON.parse(request.responseText) as MomentMediaResponse);
        } catch {
          reject(new MediaUploadError("server", "Malformed upload response"));
        }
        return;
      }
      reject(
        new MediaUploadError(kindForStatus(request.status), "Upload failed"),
      );
    });
    request.addEventListener("error", () =>
      reject(new MediaUploadError("network", "Upload failed")),
    );
    request.addEventListener("timeout", () =>
      reject(new MediaUploadError("network", "Upload timed out")),
    );
    request.addEventListener("abort", () =>
      reject(new MediaUploadError("aborted", "Upload cancelled")),
    );

    request.send(body);
  });

  return {
    promise,
    abort: () => {
      if (aborted) return;
      aborted = true;
      request.abort();
    },
  };
}

/**
 * Runs uploads with a small concurrency limit.
 *
 * Selecting twenty photos must not open twenty simultaneous connections — on a
 * phone that is slower than doing them a few at a time, and it starves the rest
 * of the app. Two is enough to keep the pipe busy without that.
 */
export async function runWithConcurrency<T>(
  tasks: Array<() => Promise<T>>,
  limit = 2,
): Promise<void> {
  let next = 0;
  const workers = Array.from(
    { length: Math.min(limit, tasks.length) },
    async () => {
      while (next < tasks.length) {
        const index = next;
        next += 1;
        // A single upload failure must not leave later selections unstarted.
        // Individual tasks surface their own failures to the attachment state.
        await tasks[index]().catch(() => undefined);
      }
    },
  );
  await Promise.all(workers);
}
