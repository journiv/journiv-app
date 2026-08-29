import Quill from "quill";
import type { InlineMediaKind } from "./deltaProfile";

/**
 * Temporary in-editor representation of a file that is still uploading.
 *
 * The Delta value carries ONLY an upload id. The local object URL, the file
 * name and the live status live in a side registry keyed by that id, so a
 * `blob:` URL can never reach a document — not through `getContents()`, not
 * through a draft, not through a save. See DESIGN.md §14.
 *
 * The id is also how an upload that finishes later decides whether it still has
 * somewhere to go: if the placeholder is gone (removed, or undone while the
 * upload was in flight) the completion must NOT reinsert the media.
 */

export const UPLOAD_BLOT_NAME = "journiv-upload";

export type PlaceholderState = "uploading" | "processing" | "failed";

type PlaceholderPreview = {
  kind: InlineMediaKind;
  fileName: string;
  /** Local object URL for image previews; undefined for video and audio. */
  objectUrl?: string;
};

const previews = new Map<string, PlaceholderPreview>();

export function registerPlaceholder(
  uploadId: string,
  preview: PlaceholderPreview,
) {
  previews.set(uploadId, preview);
}

/**
 * Object URLs are released when the editing session ends rather than the moment
 * a placeholder disappears, because Quill re-creates the blot from its Delta
 * value on undo and would otherwise render a dead preview. One URL per attached
 * file per session is a bounded cost; leaking across sessions is not.
 */
export function releaseAllPlaceholders() {
  for (const preview of previews.values()) {
    if (preview.objectUrl) URL.revokeObjectURL(preview.objectUrl);
  }
  previews.clear();
}

export function placeholderPreview(uploadId: string) {
  return previews.get(uploadId);
}

const NOUNS: Record<InlineMediaKind, string> = {
  image: "photo",
  video: "video",
  audio: "audio",
};

function build(node: HTMLElement, uploadId: string) {
  const preview = previews.get(uploadId);
  node.setAttribute("contenteditable", "false");
  node.dataset.uploadId = uploadId;
  node.classList.add("jv-upload");
  node.replaceChildren();

  if (preview?.objectUrl) {
    const image = document.createElement("img");
    image.className = "jv-upload__preview";
    image.src = preview.objectUrl;
    image.alt = "";
    node.appendChild(image);
  }

  const status = document.createElement("span");
  status.className = "jv-upload__status";
  const noun = preview ? NOUNS[preview.kind] : "file";
  status.textContent = `Uploading ${noun}…`;
  node.appendChild(status);

  // Announced politely so a long upload does not chatter at a screen reader.
  node.setAttribute("role", "status");
  node.setAttribute("aria-live", "polite");
  node.setAttribute("aria-label", `Uploading ${noun}`);
  return node;
}

// biome-ignore lint/suspicious/noExplicitAny: Quill's blot registry is untyped.
type AnyBlot = any;
const Embed: AnyBlot = Quill.import("blots/embed");

class UploadPlaceholderBlot extends Embed {
  static blotName = UPLOAD_BLOT_NAME;
  static tagName = "span";
  static className = "jv-upload-blot";

  static create(value: unknown): HTMLElement {
    const uploadId = String((value as { uploadId?: string })?.uploadId ?? "");
    // biome-ignore lint/complexity/noThisInStatic: Quill blot subclassing pattern.
    return build(super.create(value) as HTMLElement, uploadId);
  }

  /** Only the id is ever serialized. */
  static value(node: HTMLElement): { uploadId: string } {
    return { uploadId: node.dataset.uploadId ?? "" };
  }
}

let registered = false;
export function registerUploadPlaceholderBlot() {
  if (registered) return;
  registered = true;
  Quill.register(UploadPlaceholderBlot, true);
}

registerUploadPlaceholderBlot();

/** Live status update, written straight to the DOM so the Delta never churns. */
export function setPlaceholderState(
  root: HTMLElement,
  uploadId: string,
  state: PlaceholderState,
  progress?: number,
) {
  // Scanned rather than selector-escaped: CSS.escape is not available in every
  // runtime we test in, and the id set is small.
  const node = [...root.querySelectorAll<HTMLElement>("[data-upload-id]")].find(
    (candidate) => candidate.dataset.uploadId === uploadId,
  );
  const status = node?.querySelector<HTMLElement>(".jv-upload__status");
  if (!node || !status) return;
  const noun = NOUNS[previews.get(uploadId)?.kind ?? "image"];

  node.dataset.state = state;
  if (state === "failed") {
    status.textContent = `Couldn’t upload this ${noun}`;
    node.setAttribute("aria-label", `Upload failed for ${noun}`);
    return;
  }
  if (state === "processing") {
    status.textContent = "Processing…";
    node.setAttribute("aria-label", `Processing ${noun}`);
    return;
  }
  // Only show a percentage when the browser actually reported one.
  status.textContent =
    typeof progress === "number"
      ? `Uploading ${noun}… ${Math.round(progress * 100)}%`
      : `Uploading ${noun}…`;
}

/**
 * Index of a placeholder in the live document, or -1 when it is gone.
 *
 * This is the race check: an upload that completes after its placeholder was
 * removed or undone must not resurrect the media.
 */
export function findPlaceholderIndex(quill: Quill, uploadId: string): number {
  let index = 0;
  for (const op of quill.getContents().ops ?? []) {
    const insert = op.insert as Record<string, unknown> | string;
    if (typeof insert === "string") {
      index += insert.length;
      continue;
    }
    const value = insert?.[UPLOAD_BLOT_NAME] as
      | { uploadId?: string }
      | undefined;
    if (value?.uploadId === uploadId) return index;
    index += 1;
  }
  return -1;
}
