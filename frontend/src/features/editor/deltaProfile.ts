import { Delta } from "quill";
import type { QuillDelta, QuillOp } from "../../api/generated/types.gen";
import { mediaPath } from "../../lib/mediaUrl";
import { validateLinkUrl } from "./linkPolicy";

export const JOURNIV_DELTA_FORMATS = [
  "bold",
  "italic",
  "underline",
  "strike",
  "link",
  "header",
  "list",
  "blockquote",
] as const;

export const EMPTY_DELTA: QuillDelta = { ops: [{ insert: "\n" }] };

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

const INLINE_FORMATS = new Set(["bold", "italic", "underline", "strike"]);
const LINE_FORMATS = new Set(["header", "list", "blockquote"]);

function hasOnlyGate1Attributes(
  attributes: Record<string, unknown>,
  insert: string,
): boolean {
  const entries = Object.entries(attributes);
  if (
    entries.some(
      ([name]) =>
        !JOURNIV_DELTA_FORMATS.includes(
          name as (typeof JOURNIV_DELTA_FORMATS)[number],
        ),
    )
  )
    return false;

  const isLineInsert = /^\n+$/u.test(insert);
  const lineFormatCount = entries.filter(([name]) =>
    LINE_FORMATS.has(name),
  ).length;
  if (lineFormatCount > 1) return false;

  for (const [name, value] of entries) {
    if (INLINE_FORMATS.has(name)) {
      if (isLineInsert || value !== true) return false;
      continue;
    }
    if (name === "link") {
      if (
        isLineInsert ||
        typeof value !== "string" ||
        validateLinkUrl(value) !== value
      )
        return false;
      continue;
    }
    if (!LINE_FORMATS.has(name) || !isLineInsert) return false;
    if (name === "header" && value !== 1 && value !== 2 && value !== 3)
      return false;
    if (name === "list" && value !== "bullet" && value !== "ordered")
      return false;
    if (name === "blockquote" && value !== true) return false;
  }
  return true;
}

function isGate1QuillOp(value: unknown): value is QuillOp {
  if (!isRecord(value)) return false;
  const keys = Object.keys(value);
  if (keys.some((key) => key !== "insert" && key !== "attributes"))
    return false;
  const insert = value.insert;
  if (typeof insert !== "string" || insert.length === 0) return false;
  if (value.attributes === undefined || value.attributes === null) return true;
  return (
    isRecord(value.attributes) &&
    hasOnlyGate1Attributes(value.attributes, insert)
  );
}

export function isQuillDocumentDelta(value: unknown): value is QuillDelta {
  if (!isRecord(value) || !Array.isArray(value.ops) || value.ops.length === 0)
    return false;
  if (!value.ops.every(isGate1QuillOp)) return false;
  const lastInsert = value.ops.at(-1)?.insert;
  return typeof lastInsert === "string" && lastInsert.endsWith("\n");
}

/* -------------------------------------------------------------------------
 * Inline media (reader only)
 *
 * Journiv stores inline attachments as Quill embeds. VERIFIED against the live
 * API: the database holds `{ insert: { image: <media id> } }`, but the backend
 * hydrates embeds on read, so the client always receives a signed URL:
 * `{ insert: { image: "/api/v1/media/<id>/signed?uid=..&exp=..&sig=.." } }`.
 * The client therefore never resolves ids — it renders the URL it was given.
 *
 * The READER renders inline images. The EDITOR profile above is unchanged and
 * still rejects every embed, so entries containing inline media stay read-only
 * until editor attachment is built. Nothing here may widen what the editor
 * saves — a hydrated URL must never be written back in place of the id.
 * ---------------------------------------------------------------------- */

/**
 * Only same-origin relative media URLs are rendered.
 *
 * This is a private journal: fetching an absolute third-party URL found in
 * stored content would tell that third party the entry had been opened. Legacy
 * or imported documents carrying absolute URLs fall back to the plain-text
 * reader instead, which is visible rather than silent.
 */
export function isSafeInlineMediaSource(value: unknown): value is string {
  if (typeof value !== "string" || value.length <= 1) return false;
  try {
    const url = new URL(value, window.location.origin);
    const isRootRelative = value.startsWith("/");
    const isAbsolute = /^[a-z][a-z\d+.-]*:/iu.test(value);
    return (
      url.origin === window.location.origin && (isRootRelative || isAbsolute)
    );
  } catch {
    return false;
  }
}

/** Media kinds Journiv renders inline. `formula` and `divider` are not. */
export const INLINE_MEDIA_KINDS = ["image", "video", "audio"] as const;
export type InlineMediaKind = (typeof INLINE_MEDIA_KINDS)[number];

export type InlineMediaRef = { kind: InlineMediaKind; source: string };

/** The media reference carried by this op, or null if it is not an embed. */
export function inlineMediaRef(value: unknown): InlineMediaRef | null {
  if (!isRecord(value)) return null;
  const keys = Object.keys(value);
  if (keys.some((key) => key !== "insert" && key !== "attributes")) return null;
  // The API serialises `attributes: null` on embed ops. An embed carrying real
  // attributes is not something the reader understands, so it stays rejected.
  if (value.attributes !== undefined && value.attributes !== null) return null;
  const insert = value.insert;
  if (!isRecord(insert)) return null;
  const insertKeys = Object.keys(insert);
  if (insertKeys.length !== 1) return null;
  const kind = insertKeys[0] as InlineMediaKind;
  if (!INLINE_MEDIA_KINDS.includes(kind)) return null;
  const source = insert[kind];
  return isSafeInlineMediaSource(source) ? { kind, source } : null;
}

function isEmbedOp(value: unknown): boolean {
  return isRecord(value) && isRecord(value.insert);
}

/**
 * Path of each inline media item, in document order.
 *
 * Paths — not full URLs — because the signature query string differs between
 * the copy hydrated into the document and the copy returned by the media
 * endpoint, while `/api/v1/media/<id>/signed` is stable. The gallery uses this
 * to avoid showing the same item twice.
 */
export function inlineMediaPaths(delta: QuillDelta): string[] {
  const paths: string[] = [];
  for (const operation of delta.ops ?? []) {
    const ref = inlineMediaRef(operation);
    if (ref) paths.push(mediaPath(ref.source));
  }
  return paths;
}

/**
 * True when the document contains an embed the reader cannot render inline:
 * `formula`, `divider`, an embed carrying attributes we do not understand, or a
 * source that is not a safe same-origin URL.
 */
export function hasUnsupportedEmbed(delta: QuillDelta): boolean {
  return (delta.ops ?? []).some(
    (operation) => isEmbedOp(operation) && inlineMediaRef(operation) === null,
  );
}

/**
 * Reader-side document guard: Gate-1 text plus inline media embeds.
 * Deliberately separate from `isQuillDocumentDelta`, which the editor uses and
 * which still rejects every embed.
 */
export function isReaderDocumentDelta(value: unknown): value is QuillDelta {
  if (!isRecord(value) || !Array.isArray(value.ops) || value.ops.length === 0)
    return false;
  if (
    !value.ops.every(
      (operation) =>
        isGate1QuillOp(operation) || inlineMediaRef(operation) !== null,
    )
  )
    return false;
  const lastInsert = value.ops.at(-1)?.insert;
  return typeof lastInsert === "string" && lastInsert.endsWith("\n");
}

/**
 * Remove in-flight upload placeholders from a document.
 *
 * Defence in depth. The editor already refuses to save while an upload is
 * pending, but a placeholder embed must never be able to reach the server under
 * any circumstance: it carries a client-only id and, transitively, a local
 * object URL. Applied by `QuillSurface.getContents()` so every caller is safe.
 */
export function stripUploadPlaceholders(delta: QuillDelta): QuillDelta {
  const ops = (delta.ops ?? []).filter((operation) => {
    const insert = operation.insert;
    return !(isRecord(insert) && UPLOAD_PLACEHOLDER_KEY in insert);
  });
  return { ops } as QuillDelta;
}

/** Kept here, not imported, so this module stays free of Quill and DOM. */
export const UPLOAD_PLACEHOLDER_KEY = "journiv-upload";

/**
 * Documents the editor can represent: Gate-1 text plus inline media.
 *
 * An alias of the reader guard, named for the editor so both call sites read
 * honestly. The Gate-1 guard `isQuillDocumentDelta` remains the narrower
 * text-only contract and is still used where embeds must be refused.
 */
export const isEditableDocumentDelta = isReaderDocumentDelta;

export function cloneDelta(delta: QuillDelta): QuillDelta {
  return JSON.parse(JSON.stringify(delta)) as QuillDelta;
}

function sortObject(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortObject);
  if (!isRecord(value)) return value;
  return Object.fromEntries(
    Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, child]) => [key, sortObject(child)]),
  );
}

export function canonicalDeltaJson(delta: QuillDelta): string {
  if (!isQuillDocumentDelta(delta))
    throw new Error("Invalid Quill document Delta");
  const canonical = new Delta();
  for (const operation of delta.ops ?? []) {
    canonical.insert(operation.insert, operation.attributes ?? undefined);
  }
  return JSON.stringify(sortObject({ ops: canonical.ops }));
}

export function deltasEqual(left: QuillDelta, right: QuillDelta) {
  return canonicalDeltaJson(left) === canonicalDeltaJson(right);
}
