/**
 * What the API said, including the status code.
 *
 * The generated client throws the parsed response BODY on a failed request, so
 * by the time an error reaches a caller the status is gone — and "the Moment is
 * gone" and "the network is gone" become the same value. They are not the same
 * decision: dropping a draft's server identity because the Moment 404s is
 * correct, and doing it because a phone lost signal orphans a Moment nobody
 * will ever finalise.
 *
 * So `configureApiClient` wraps every failure in this. `status` is the HTTP
 * status, or `undefined` when the request never got an answer at all.
 */
export class ApiError extends Error {
  /** HTTP status, or undefined when the request never reached a response. */
  readonly status?: number;
  /** The parsed error body, exactly as the API sent it. */
  readonly body: unknown;

  constructor(
    message: string,
    options: { status?: number; body?: unknown; cause?: unknown } = {},
  ) {
    super(message, { cause: options.cause });
    this.name = "ApiError";
    this.status = options.status;
    this.body = options.body;
  }
}

/** `detail` is FastAPI's error field; anything else falls back to the status. */
function messageFor(body: unknown, status?: number): string {
  if (typeof body === "string" && body.trim()) return body;
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return status ? `Request failed with status ${status}` : "Request failed";
}

/** Wraps whatever the generated client threw, keeping the response status. */
export function toApiError(caught: unknown, response?: Response): ApiError {
  if (caught instanceof ApiError) return caught;
  const status = response?.status;
  return new ApiError(messageFor(caught, status), {
    status,
    body: caught,
    cause: caught,
  });
}

/**
 * A definite "this does not exist" from the server.
 *
 * Deliberately narrow: a thrown value with no status is NOT a 404. Every caller
 * of this is about to act on the absence of something, and "I could not ask"
 * must never be mistaken for "I asked and it is gone".
 */
export function isNotFound(caught: unknown): boolean {
  return caught instanceof ApiError && caught.status === 404;
}

/** The entry moved underneath this edit; see DESIGN.md §14, "Concurrent edits". */
export function isConflict(caught: unknown): boolean {
  return caught instanceof ApiError && caught.status === 409;
}
