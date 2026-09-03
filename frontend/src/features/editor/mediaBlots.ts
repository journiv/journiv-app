import Quill from "quill";

/**
 * Journiv media blots.
 *
 * Quill ships a `video` format that renders an <iframe> — it is built for
 * YouTube embeds, not for self-hosted files behind signed URLs. Journiv needs a
 * real <video> element, and Quill has no audio format at all.
 *
 * These blots deliberately keep the STANDARD Delta keys (`video`, `audio`), so
 * the persisted document stays byte-compatible with flutter_quill's
 * BlockEmbed.video / BlockEmbed.audio. Nothing here changes the wire format; it
 * only changes how the DOM is produced. See docs/features/reader.md.
 *
 * Registration happens once at module load. Import this module before any Quill
 * instance is constructed.
 */

// biome-ignore lint/suspicious/noExplicitAny: Quill's blot registry is untyped.
type AnyBlot = any;

const BlockEmbed: AnyBlot = Quill.import("blots/block/embed");

/** Shared setup so a media element can never behave like an editable control. */
function prepare(node: HTMLElement, source: string, className: string) {
  node.setAttribute("src", source);
  node.setAttribute("controls", "true");
  node.setAttribute("preload", "metadata");
  node.setAttribute("contenteditable", "false");
  node.classList.add(className);
  return node;
}

class VideoBlot extends BlockEmbed {
  static blotName = "video";
  static tagName = "video";

  static create(value: unknown): HTMLElement {
    // No autoplay, ever: a journal must not start making noise when opened.
    // biome-ignore lint/complexity/noThisInStatic: Quill's documented blot subclassing pattern — the base class builds the element.
    return prepare(super.create(value), String(value ?? ""), "jv-prose__video");
  }

  static value(node: HTMLElement): string {
    return node.getAttribute("src") ?? "";
  }
}

class AudioBlot extends BlockEmbed {
  static blotName = "audio";
  static tagName = "audio";

  static create(value: unknown): HTMLElement {
    // biome-ignore lint/complexity/noThisInStatic: Quill blot pattern; see above.
    return prepare(super.create(value), String(value ?? ""), "jv-prose__audio");
  }

  static value(node: HTMLElement): string {
    return node.getAttribute("src") ?? "";
  }
}

let registered = false;

/** Idempotent: repeated imports (and test re-imports) must not re-register. */
export function registerJournivMediaBlots() {
  if (registered) return;
  registered = true;
  // `true` suppresses Quill's overwrite warning for the built-in video format.
  Quill.register(VideoBlot, true);
  Quill.register(AudioBlot, true);
}

registerJournivMediaBlots();
