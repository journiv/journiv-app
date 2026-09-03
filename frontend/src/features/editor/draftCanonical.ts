import type { QuillDelta } from "../../api/generated/types.gen";
import {
  inlineMediaRef,
  INLINE_MEDIA_KINDS,
  type InlineMediaKind,
  UPLOAD_PLACEHOLDER_KEY,
} from "./deltaProfile";

/**
 * The boundary between what the editor holds and what a local draft may store.
 *
 * A live editor document carries SIGNED media URLs, not media ids. The backend
 * stores `{ insert: { image: "<uuid>" } }` but hydrates on read, so the client
 * always receives `/api/v1/media/<uuid>/signed?uid=..&exp=..&sig=..` — a
 * user-scoped, expiring credential. docs/known-gaps.md forbids persisting one.
 *
 * So a draft stores the DURABLE form — the bare media UUID, which is exactly
 * what the database itself holds — and recovery resolves those ids back to
 * fresh signed URLs against the Moment's current media.
 *
 *   live Delta (signed URLs) --canonicalizeDeltaForDraft--> durable Delta (uuids)
 *   durable Delta (uuids) -----rehydrateDraftDelta--------> live Delta (fresh URLs)
 *
 * This module owns that translation and nothing else. It knows about media URL
 * shape; it knows nothing about IndexedDB, React or the network. The draft
 * repository is the mirror image: it persists a `DurableDraftDelta` and has no
 * idea media signing exists. Keep it that way — the day Journiv changes how it
 * signs media, this file is the only one that should need to change.
 */

/**
 * A document whose media embeds are bare media UUIDs.
 *
 * Branded so it cannot be confused with a `QuillDelta`. A durable Delta is a
 * PERSISTENCE format: its embed sources have no leading `/`, so it deliberately
 * fails `isSafeInlineMediaSource` and therefore `isEditableDocumentDelta`. It
 * must never be handed to `QuillSurface` or sent to the API — rehydrate first.
 */
export type DurableDraftDelta = QuillDelta & {
  readonly __durableDraftDelta: unique symbol;
};

/** The media id shape the backend uses (`_MEDIA_ID_PATTERN` in media_signing.py). */
const MEDIA_ID =
  "[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}";
const MEDIA_ID_ONLY = new RegExp(`^${MEDIA_ID}$`);
/**
 * Journiv serves every inline attachment from this one path — including media
 * backed by Immich, which is proxied rather than linked
 * (`signed_url_for_journiv` is the only builder `attach_signed_urls` uses). So
 * one pattern covers every source the editor can hold; there is no Immich case
 * to handle on the client.
 */
const MEDIA_PATH = new RegExp(`^/api/v1/media/(${MEDIA_ID})(?:/|\\?|$)`, "i");

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * The durable media id behind a live embed source, or null when there is none.
 *
 * Purely syntactic — it cannot ask the server anything, because canonicalizing
 * runs inside the draft debounce and that path must never touch the network.
 * Whether the id is one this user may actually read is settled later, at
 * rehydration, against the Moment's own media list.
 */
export function durableMediaId(source: string): string | null {
  return MEDIA_PATH.exec(source)?.[1]?.toLowerCase() ?? null;
}

function isDurableMediaId(value: unknown): value is string {
  return typeof value === "string" && MEDIA_ID_ONLY.test(value);
}

/** The durable media id carried by this op, or null if it is not a media embed. */
function durableRefOf(
  operation: unknown,
): { kind: InlineMediaKind; id: string } | null {
  if (!isRecord(operation) || !isRecord(operation.insert)) return null;
  const keys = Object.keys(operation.insert);
  if (keys.length !== 1) return null;
  const kind = keys[0] as InlineMediaKind;
  if (!INLINE_MEDIA_KINDS.includes(kind)) return null;
  const value = operation.insert[kind];
  return isDurableMediaId(value) ? { kind, id: value } : null;
}

export type CanonicalizeResult = {
  delta: DurableDraftDelta;
  /**
   * In-flight upload placeholders left out on purpose.
   *
   * A placeholder is TRANSIENT: it stands for bytes still travelling, and there
   * is no durable id to keep. docs/known-gaps.md is explicit that an upload
   * interrupted by a reload is lost and must be reattached, and that no fake
   * completed embed may be synthesised. So omitting it is correct — but it is
   * not invisible. The count is carried so the editor can say plainly that an
   * upload will need attaching again.
   */
  omittedTransientUploads: number;
  /**
   * Durable content Journiv could not represent in a draft.
   *
   * A media embed whose source yields no id, or an embed kind this build does
   * not understand. Unlike a transient upload, this is real content the entry
   * already holds, and dropping it would make the draft a lossy copy of the
   * writing it claims to protect. A non-zero count means the draft is NOT safe
   * to store: the caller must refuse the write rather than persist a document
   * that would silently lose this content on recovery — and would then ask the
   * backend to delete the media on the next save.
   */
  unsupportedEmbeds: number;
};

/**
 * Reduce a live editor document to the form a draft may store.
 *
 * Three outcomes, kept apart on purpose, because they mean different things to
 * the person writing:
 *
 * - **known durable content** — text, Gate-1 formatting, and media that resolves
 *   to a durable id — is persisted;
 * - **known transient content** — an in-flight upload placeholder — is omitted
 *   deliberately and counted, so the reattach limitation can be stated;
 * - **unknown or unrepresentable durable content** is counted separately and
 *   makes the whole result unsafe to store.
 *
 * The invariant this exists to protect: `Saved locally` may only be shown when
 * every piece of durable content Journiv claims to support has actually been
 * represented in the draft.
 */
export function canonicalizeDeltaForDraft(
  delta: QuillDelta,
): CanonicalizeResult {
  const ops: Record<string, unknown>[] = [];
  let omittedTransientUploads = 0;
  let unsupportedEmbeds = 0;

  /**
   * Merge into the previous op when both are plain text carrying the same
   * attributes. Quill already emits documents in this shape, but dropping a
   * media embed can leave two text ops adjacent — and two spellings of one
   * document would make identical writing compare as different.
   */
  const push = (operation: Record<string, unknown>) => {
    const previous = ops.at(-1);
    if (
      previous &&
      typeof previous.insert === "string" &&
      typeof operation.insert === "string" &&
      JSON.stringify(previous.attributes ?? null) ===
        JSON.stringify(operation.attributes ?? null)
    ) {
      previous.insert += operation.insert;
      return;
    }
    ops.push({ ...operation });
  };

  for (const operation of (delta.ops ?? []) as Record<string, unknown>[]) {
    // Already durable: canonicalizing a canonical document is a no-op, which
    // keeps equality comparisons and re-saves stable.
    if (durableRefOf(operation)) {
      push(operation);
      continue;
    }
    if (typeof operation.insert === "string") {
      push(operation);
      continue;
    }
    // A transient upload placeholder. Known, expected, and deliberately not
    // stored — there is nothing durable to store. Counted so the reattach
    // limitation can be stated rather than discovered.
    if (
      isRecord(operation.insert) &&
      UPLOAD_PLACEHOLDER_KEY in operation.insert
    ) {
      omittedTransientUploads += 1;
      continue;
    }

    const ref = inlineMediaRef(operation);
    if (!ref) {
      // An embed kind this build does not understand. Only TEXT passes through
      // unconditionally; everything else must prove itself, or client-only
      // state reaches storage.
      unsupportedEmbeds += 1;
      continue;
    }
    const id = durableMediaId(ref.source);
    if (!id) {
      // Real media the entry holds, with no durable id to keep — a legacy or
      // imported source the backend never mapped. Persisting the URL is exactly
      // what docs/known-gaps.md forbids, and persisting the document without it
      // would be a lossy copy. Neither is acceptable, so the draft is unsafe.
      unsupportedEmbeds += 1;
      continue;
    }
    push({ insert: { [ref.kind]: id } });
  }

  return {
    delta: { ops } as unknown as DurableDraftDelta,
    omittedTransientUploads,
    unsupportedEmbeds,
  };
}

/** Whether a stored value is shaped like a durable draft document. */
export function isDurableDraftDelta(
  value: unknown,
): value is DurableDraftDelta {
  if (!isRecord(value) || !Array.isArray(value.ops)) return false;
  return value.ops.every((operation) => {
    if (!isRecord(operation)) return false;
    if (typeof operation.insert === "string") return true;
    return durableRefOf(operation) !== null;
  });
}

/** Durable media ids referenced by a draft, in document order, deduplicated. */
export function draftMediaIds(delta: DurableDraftDelta): string[] {
  const seen = new Set<string>();
  for (const operation of delta.ops ?? []) {
    const ref = durableRefOf(operation);
    if (ref) seen.add(ref.id);
  }
  return [...seen];
}

export type RehydrateResult = {
  delta: QuillDelta;
  /**
   * Media the server no longer has, or that is not on this Moment. Dropped
   * rather than kept: an unresolvable reference saved back through Done would
   * be stored verbatim as permanent journal content
   * (`_extract_media_id_from_source` returns None and `transform_delta_media`
   * then leaves the value unchanged), which is silent corruption. Dropping is
   * destructive but visible, and the count is always shown.
   */
  unresolvedMediaCount: number;
};

/**
 * Resolve a stored draft back into a document the editor can mount.
 *
 * `signedUrlById` comes from the Moment's own media (`GET /moments/{id}/media`),
 * so this is also where authorisation is settled: an id the server does not
 * list for this Moment is not resolved, whatever the draft claims.
 */
export function rehydrateDraftDelta(
  delta: DurableDraftDelta,
  signedUrlById: ReadonlyMap<string, string | null | undefined>,
): RehydrateResult {
  const ops: unknown[] = [];
  let unresolvedMediaCount = 0;

  for (const operation of delta.ops ?? []) {
    const ref = durableRefOf(operation);
    if (!ref) {
      ops.push(operation);
      continue;
    }
    const source = signedUrlById.get(ref.id);
    if (!source) {
      unresolvedMediaCount += 1;
      continue;
    }
    ops.push({ insert: { [ref.kind]: source } });
  }

  return { delta: { ops } as QuillDelta, unresolvedMediaCount };
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

/**
 * Stable serialisation of a document for comparison.
 *
 * Canonical first, so signature rotation cannot make an unchanged draft look
 * different — otherwise every reload past the signed-URL lifetime would offer
 * to recover a draft identical to what is already on screen.
 *
 * Deliberately NOT `deltasEqual` from deltaProfile: that routes through
 * `isQuillDocumentDelta`, the text-only Gate-1 guard, and THROWS on any media
 * embed.
 */
export function draftComparisonKey(delta: QuillDelta): string {
  return JSON.stringify(sortObject(canonicalizeDeltaForDraft(delta).delta));
}

/** True when two documents are the same writing, ignoring URL signatures. */
export function draftContentEquals(left: QuillDelta, right: QuillDelta) {
  return draftComparisonKey(left) === draftComparisonKey(right);
}

/**
 * The writing in a draft, as plain text.
 *
 * Used where the editor cannot be opened but the words must still be visible —
 * a draft whose attachments cannot be re-signed because the server is
 * unreachable. Showing the writing is what makes "your work is safe" a
 * statement the reader can check rather than a promise they have to trust.
 */
export function draftPlainText(delta: DurableDraftDelta): string {
  let text = "";
  for (const operation of delta.ops ?? []) {
    if (typeof operation.insert === "string") text += operation.insert;
  }
  return text.trim();
}
