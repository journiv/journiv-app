import Quill, { Delta, type Range } from "quill";
import "quill/dist/quill.core.css";
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react";
import type { QuillDelta } from "../../api/generated/types.gen";
import { mediaPath } from "../../lib/mediaUrl";
import {
  cloneDelta,
  INLINE_MEDIA_KINDS,
  inlineMediaPaths,
  isQuillDocumentDelta,
  isReaderDocumentDelta,
  JOURNIV_DELTA_FORMATS,
  MAX_LIST_INDENT,
  stripOrphanIndent,
  stripUploadPlaceholders,
  type InlineMediaKind,
} from "./deltaProfile";
import { durableMediaId } from "./draftCanonical";
import { installMarkdownShortcuts } from "./markdownShortcuts";
import "./mediaBlots";
import "./quill-adapter.css";
import {
  findPlaceholderIndex,
  type PlaceholderState,
  releaseAllPlaceholders,
  setPlaceholderState as setPlaceholderStateDom,
  UPLOAD_BLOT_NAME,
} from "./uploadPlaceholder";

export interface QuillSurfaceHandle {
  getContents(): QuillDelta;
  /** Caret position, captured before anything that can steal focus. */
  getSelectionIndex(): number;
  /** Inserts a pending-upload placeholder on its own line. */
  insertPlaceholder(index: number, uploadId: string): void;
  /**
   * Prepends the prompt text as a heading-3 line at the top of the document
   * and moves the caret after it. Used when a writer picks a prompt from the
   * in-editor picker (docs/features/prompts.md).
   */
  seedPromptHeading(text: string): void;
  /**
   * Inserts a durable media embed at the caret, on its own line. Used to place
   * media that is already attached to the Moment (the editor's attached-media
   * gallery, docs/features/editor.md) into the prose — the source is a signed
   * `/api/v1/media/<id>/signed?…` URL the backend maps back to the id on save,
   * so no new media record is created.
   */
  insertMedia(kind: InlineMediaKind, source: string): void;
  /** Swaps a placeholder for durable media. False when it is no longer there. */
  replacePlaceholder(
    uploadId: string,
    kind: InlineMediaKind,
    source: string,
  ): boolean;
  removePlaceholder(uploadId: string): boolean;
  /**
   * Removes the embed whose signed-URL source resolves to this media id, and
   * returns the index it stood at. Used for Remove — and for a device-upload
   * retry, which reinserts a placeholder at that same index — on an
   * attachment that already swapped its placeholder for a real embed, where
   * there is no placeholder left to find by upload id. Null when no such
   * embed is in the document (already removed, or never placed).
   */
  removeEmbedForMediaId(mediaId: string): number | null;
  /**
   * Forgets undo history. Called after a save, because the backend deletes
   * media that a save removed from the document — an undo afterwards would
   * restore a reference to a file that no longer exists.
   */
  clearHistory(): void;
  /** Document index nearest a screen point, for drop placement. */
  getIndexFromPoint(clientX: number, clientY: number): number;
  /** Media embed under the cursor, for contextual actions. */
  getSelectedMedia(): { kind: InlineMediaKind; index: number } | null;
  removeSelectedMedia(): boolean;
  hasPlaceholder(uploadId: string): boolean;
  setPlaceholderState(
    uploadId: string,
    state: PlaceholderState,
    progress?: number,
  ): void;
  getLinkContext(): LinkContext;
  focus(): void;
  hasFocus(): boolean;
  isComposing(): boolean;
  toggleInline(name: InlineFormat): void;
  toggleLine(name: LineFormat, value: LineFormatValue): void;
  /**
   * Nudges the nesting level of the current list line by one step, clamped to
   * 0…MAX_LIST_INDENT. A no-op when the caret is not on a list line.
   */
  indent(direction: 1 | -1): void;
  setLink(value: string | false): boolean;
  undo(): void;
  redo(): void;
}

export type InlineFormat = "bold" | "italic" | "underline" | "strike";
export type LineFormat = "header" | "list" | "blockquote";
export type LineFormatValue =
  | 1
  | 2
  | 3
  | "bullet"
  | "ordered"
  | "checked"
  | "unchecked"
  | true;

/** Transient class + lifetime for the "just added from the tray" ring
 *  (styled in editor.css, honoured-down by prefers-reduced-motion there). */
const MEDIA_FLASH_CLASS = "jv-prose__media-flash";
const MEDIA_FLASH_MS = 1200;

/**
 * How often the word count may be recomputed while someone is typing.
 *
 * Counting words means reading the whole document, so the count is deliberately
 * decoupled from the keystroke rate: a change arms this interval, everything
 * typed inside it is coalesced, and the recount happens once at the end. Typing
 * continuously therefore costs two recounts a second instead of one per key,
 * and the count still settles within one interval of the last keystroke.
 */
export const WORD_COUNT_INTERVAL_MS = 500;

export type EditorState = {
  formats: Record<string, unknown>;
  focused: boolean;
  selectionLength: number;
  wordCount: number;
  /** Set when the cursor is on an inline media embed. */
  selectedMedia: InlineMediaKind | null;
};

export type LinkContext = {
  href: string;
  selectedText: string;
  canApply: boolean;
};

type QuillSurfaceProps = {
  initialContent: QuillDelta;
  editorId: string;
  onUserChange?: () => void;
  onStateChange?: (state: EditorState) => void;
  /**
   * The document's inline media, as stable `/api/v1/media/<id>/signed` paths in
   * document order, whenever it changes. The editor uses this to hide media
   * from its attached-media gallery the moment it is placed inline
   * (docs/features/editor.md).
   */
  onInlineMediaChange?: (paths: string[]) => void;
  placeholder?: string;
  readOnly?: boolean;
  ariaLabel?: string;
  className?: string;
  /** Files dropped on, or pasted into, the writing surface. */
  onFiles?: (files: File[], index: number) => void;
  /**
   * Format allowlist. Defaults to the Gate-1 editor profile. The reader widens
   * it to include inline images; nothing that can be saved may widen it.
   */
  formats?: readonly string[];
};

/**
 * Document index nearest a screen point.
 *
 * `caretRangeFromPoint` is WebKit/Blink; `caretPositionFromPoint` is the
 * standard. Neither is universal, so the caller supplies a fallback.
 */
function indexFromPoint(
  quill: Quill,
  clientX: number,
  clientY: number,
  fallback: number,
): number {
  const point = document as Document & {
    caretRangeFromPoint?: (x: number, y: number) => globalThis.Range | null;
    caretPositionFromPoint?: (
      x: number,
      y: number,
    ) => { offsetNode: Node; offset: number } | null;
  };
  let node: Node | null = null;
  let offset = 0;
  const range = point.caretRangeFromPoint?.(clientX, clientY);
  if (range) {
    node = range.startContainer;
    offset = range.startOffset;
  } else {
    const position = point.caretPositionFromPoint?.(clientX, clientY);
    if (position) {
      node = position.offsetNode;
      offset = position.offset;
    }
  }
  if (!node || !quill.root.contains(node)) return fallback;
  try {
    const blot = Quill.find(node, true);
    if (!blot) return fallback;
    return quill.getIndex(blot as never) + offset;
  } catch {
    return fallback;
  }
}

/**
 * The media kind at a document position, if the blot there is a media embed.
 *
 * Read off the blot rather than out of a Delta: this runs on every keystroke,
 * and `getContents(index, 1)` slices the whole document to look at one op —
 * O(document) work to answer a question about one position. Walking to the blot
 * costs the same as Quill's own selection bookkeeping and allocates nothing.
 */
function mediaKindAt(quill: Quill, index?: number): InlineMediaKind | null {
  if (typeof index !== "number") return null;
  // A selected embed reads as a one-character range; a collapsed caret sitting
  // just after one counts too, which is where Backspace lands.
  for (const candidate of [index, index - 1]) {
    if (candidate < 0) continue;
    const [leaf] = quill.getLeaf(candidate);
    const kind = (leaf as { statics?: { blotName?: string } } | null)?.statics
      ?.blotName;
    if (kind && (INLINE_MEDIA_KINDS as readonly string[]).includes(kind))
      return kind as InlineMediaKind;
  }
  return null;
}

/** Whether two `getFormat()` results describe the same active formatting.
 *  Quill returns an array when a range spans conflicting values. */
function sameFormatValue(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (!Array.isArray(left) || !Array.isArray(right)) return false;
  return (
    left.length === right.length &&
    left.every((value, index) => value === right[index])
  );
}

function sameEditorState(
  left: EditorState | null,
  right: EditorState,
): boolean {
  if (
    left === null ||
    left.focused !== right.focused ||
    left.selectionLength !== right.selectionLength ||
    left.wordCount !== right.wordCount ||
    left.selectedMedia !== right.selectedMedia
  )
    return false;
  const names = Object.keys(left.formats);
  return (
    names.length === Object.keys(right.formats).length &&
    names.every((name) =>
      sameFormatValue(left.formats[name], right.formats[name]),
    )
  );
}

/**
 * Whether a change could have altered which media the document holds.
 *
 * Only an embed insert or a deletion can. Ordinary typing cannot, so it never
 * pays for the full document read `inlineMediaPaths` needs.
 */
function mayChangeInlineMedia(delta: Delta): boolean {
  return (delta.ops ?? []).some(
    (operation) =>
      operation.delete != null ||
      (operation.insert != null && typeof operation.insert !== "string"),
  );
}

export const QuillSurface = forwardRef<QuillSurfaceHandle, QuillSurfaceProps>(
  function QuillSurface(
    {
      initialContent,
      editorId,
      onUserChange,
      onStateChange,
      onInlineMediaChange,
      placeholder,
      readOnly = false,
      ariaLabel,
      className,
      formats,
      onFiles,
    },
    forwardedRef,
  ) {
    const hostRef = useRef<HTMLDivElement>(null);
    const quillRef = useRef<Quill | null>(null);
    const lastRangeRef = useRef<Range | null>(null);
    const linkRangeRef = useRef<Range | null>(null);
    const composingRef = useRef(false);
    const emitStateRef = useRef<((range: Range | null) => void) | null>(null);
    // Content changes alone must not discard unsaved edits, but a deliberate
    // surface reinitialization (new entry or placeholder) must use its latest
    // content rather than the component's mount-time value. Held by reference
    // and copied only where it is read — deep-cloning it on every render meant
    // a full JSON round-trip of the document on every keystroke.
    const initialContentRef = useRef(initialContent);
    initialContentRef.current = initialContent;
    const readOnlyRef = useRef(readOnly);
    readOnlyRef.current = readOnly;
    const ariaLabelRef = useRef(ariaLabel);
    ariaLabelRef.current = ariaLabel;
    const initialFormatsRef = useRef(formats ?? JOURNIV_DELTA_FORMATS);
    // A surface validates against its own profile. A text-only surface must
    // still refuse embeds; one configured with media formats accepts them.
    const validateRef = useRef(
      initialFormatsRef.current.some((format) =>
        (INLINE_MEDIA_KINDS as readonly string[]).includes(format),
      )
        ? isReaderDocumentDelta
        : isQuillDocumentDelta,
    );
    const filesRef = useRef(onFiles);
    filesRef.current = onFiles;
    const userChangeRef = useRef(onUserChange);
    const stateChangeRef = useRef(onStateChange);
    const inlineMediaChangeRef = useRef(onInlineMediaChange);
    userChangeRef.current = onUserChange;
    stateChangeRef.current = onStateChange;
    inlineMediaChangeRef.current = onInlineMediaChange;

    const withSelection = useCallback(
      (
        command: (quill: Quill, range: Range) => void,
        preferredRange?: Range | null,
      ): boolean => {
        const quill = quillRef.current;
        const range =
          preferredRange ?? quill?.getSelection() ?? lastRangeRef.current;
        if (!quill || !range || composingRef.current) return false;
        command(quill, range);
        lastRangeRef.current = range;
        quill.setSelection(range, "silent");
        quill.focus({ preventScroll: true });
        emitStateRef.current?.(range);
        return true;
      },
      [],
    );

    useImperativeHandle(
      forwardedRef,
      () => ({
        getContents: () => {
          const contents = quillRef.current?.getContents();
          if (!contents) throw new Error("Editor is not ready");
          // A pending upload placeholder is client-only state and must never
          // leave the editor. Strip before validating, so a document that is
          // mid-upload still yields a valid saveable Delta. `stripOrphanIndent`
          // then drops any `indent` left on a line whose `list` was removed
          // (e.g. a nested bullet turned into a heading) — an orphan indent is
          // outside the Gate-1 profile and would fail the guard below.
          const stripped = stripOrphanIndent(
            stripUploadPlaceholders(contents as unknown as QuillDelta),
          );
          if (!validateRef.current(stripped))
            throw new Error("Editor returned an invalid document Delta");
          return cloneDelta(stripped);
        },
        getSelectionIndex: () => {
          const quill = quillRef.current;
          const range = quill?.getSelection() ?? lastRangeRef.current;
          return range?.index ?? quill?.getLength() ?? 0;
        },
        insertPlaceholder: (index, uploadId) => {
          const quill = quillRef.current;
          if (!quill) return;
          // Media reads better on its own line, so break the paragraph first
          // when the caret is mid-sentence.
          let at = Math.min(Math.max(index, 0), quill.getLength());
          if (at > 0 && quill.getText(at - 1, 1) !== "\n") {
            quill.insertText(at, "\n", "user");
            at += 1;
          }
          quill.insertEmbed(at, UPLOAD_BLOT_NAME, { uploadId }, "user");
          // Caret lands after the placeholder so writing continues below it.
          quill.setSelection(at + 1, 0, "silent");
        },
        seedPromptHeading: (text) => {
          const quill = quillRef.current;
          if (!quill) return;
          const trimmed = text.trim();
          if (!trimmed) return;
          // No leading retain: the ops apply at index 0, so the heading lands
          // above whatever is already written. "user" source so the editor
          // marks the body dirty and the local draft is kept.
          quill.updateContents(
            new Delta().insert(trimmed).insert("\n", { header: 3 }),
            "user",
          );
          quill.setSelection(trimmed.length + 1, 0, "silent");
          quill.focus();
        },
        insertMedia: (kind, source) => {
          const quill = quillRef.current;
          if (!quill) return;
          const range = quill.getSelection() ?? lastRangeRef.current;
          // Media reads better on its own line, so break the paragraph first
          // when the caret is mid-sentence. "user" source so the editor marks
          // the body dirty and the local draft is kept — the same path an
          // upload takes when it swaps its placeholder for a durable embed.
          let at = Math.min(
            Math.max(range?.index ?? quill.getLength(), 0),
            quill.getLength(),
          );
          if (at > 0 && quill.getText(at - 1, 1) !== "\n") {
            quill.insertText(at, "\n", "user");
            at += 1;
          }
          quill.insertEmbed(at, kind, source, "user");
          // A block embed (video/audio) placed at the very end of the document
          // leaves it without the trailing newline the document guard requires;
          // an inline image keeps its paragraph's. Restore it only when needed.
          const lastInsert = quill.getContents().ops?.at(-1)?.insert;
          if (typeof lastInsert !== "string" || !lastInsert.endsWith("\n")) {
            quill.insertText(quill.getLength(), "\n", "user");
          }
          quill.setSelection(at + 1, 0, "silent");
          quill.focus();
          // Make the result unmistakable: bring the new embed into view and
          // ring it briefly. Without this, "Add to entry" can land a photo
          // off-screen and feel like it did nothing.
          const placed = [
            ...quill.root.querySelectorAll("img, video, audio"),
          ].find((element) => element.getAttribute("src") === source);
          if (placed instanceof HTMLElement) {
            placed.scrollIntoView({ block: "center" });
            placed.classList.add(MEDIA_FLASH_CLASS);
            window.setTimeout(
              () => placed.classList.remove(MEDIA_FLASH_CLASS),
              MEDIA_FLASH_MS,
            );
          }
        },
        replacePlaceholder: (uploadId, kind, source) => {
          const quill = quillRef.current;
          if (!quill) return false;
          const index = findPlaceholderIndex(quill, uploadId);
          if (index < 0) return false;
          // One atomic operation, so undo treats the swap as a single step.
          quill.updateContents(
            new Delta()
              .retain(index)
              .delete(1)
              .insert({ [kind]: source }),
            "user",
          );
          return true;
        },
        removePlaceholder: (uploadId) => {
          const quill = quillRef.current;
          if (!quill) return false;
          const index = findPlaceholderIndex(quill, uploadId);
          if (index < 0) return false;
          quill.deleteText(index, 1, "user");
          return true;
        },
        removeEmbedForMediaId: (mediaId) => {
          const quill = quillRef.current;
          if (!quill) return null;
          const normalizedMediaId = mediaId.toLowerCase();
          let index = 0;
          for (const op of quill.getContents().ops ?? []) {
            const insert = op.insert as Record<string, unknown> | string;
            if (typeof insert === "string") {
              index += insert.length;
              continue;
            }
            const keys = Object.keys(insert);
            const kind = keys[0];
            const source = insert[kind];
            if (
              keys.length === 1 &&
              (INLINE_MEDIA_KINDS as readonly string[]).includes(kind) &&
              typeof source === "string" &&
              durableMediaId(mediaPath(source)) === normalizedMediaId
            ) {
              quill.deleteText(index, 1, "user");
              return index;
            }
            index += 1;
          }
          return null;
        },
        clearHistory: () => quillRef.current?.history.clear(),
        getIndexFromPoint: (clientX, clientY) => {
          const quill = quillRef.current;
          if (!quill) return 0;
          const fallback =
            (quill.getSelection() ?? lastRangeRef.current)?.index ??
            quill.getLength();
          return indexFromPoint(quill, clientX, clientY, fallback);
        },
        getSelectedMedia: () => {
          const quill = quillRef.current;
          const range = quill?.getSelection() ?? lastRangeRef.current;
          if (!quill || !range) return null;
          // A selected embed reads as a one-character range; a collapsed caret
          // sitting just after one counts too, which is where Backspace lands.
          for (const candidate of [range.index, range.index - 1]) {
            if (candidate < 0) continue;
            const [op] = quill.getContents(candidate, 1).ops ?? [];
            const insert = op?.insert;
            if (!insert || typeof insert === "string") continue;
            const kind = Object.keys(insert)[0] as InlineMediaKind;
            if ((INLINE_MEDIA_KINDS as readonly string[]).includes(kind))
              return { kind, index: candidate };
          }
          return null;
        },
        removeSelectedMedia: () => {
          const quill = quillRef.current;
          if (!quill) return false;
          const range = quill.getSelection() ?? lastRangeRef.current;
          if (!range) return false;
          for (const candidate of [range.index, range.index - 1]) {
            if (candidate < 0) continue;
            const [op] = quill.getContents(candidate, 1).ops ?? [];
            const insert = op?.insert;
            if (!insert || typeof insert === "string") continue;
            const kind = Object.keys(insert)[0];
            if (!(INLINE_MEDIA_KINDS as readonly string[]).includes(kind))
              continue;
            quill.deleteText(candidate, 1, "user");
            quill.setSelection(candidate, 0, "silent");
            return true;
          }
          return false;
        },
        hasPlaceholder: (uploadId) =>
          quillRef.current
            ? findPlaceholderIndex(quillRef.current, uploadId) >= 0
            : false,
        setPlaceholderState: (uploadId, state, progress) => {
          const quill = quillRef.current;
          if (quill)
            setPlaceholderStateDom(quill.root, uploadId, state, progress);
        },
        getLinkContext: () => {
          const quill = quillRef.current;
          let range = quill?.getSelection() ?? lastRangeRef.current;
          if (!quill || !range)
            return { href: "", selectedText: "", canApply: false };
          const href = quill.getFormat(range).link;
          if (range.length === 0 && typeof href === "string") {
            let start = range.index;
            let end = range.index;
            while (start > 0 && quill.getFormat(start - 1, 1).link === href)
              start -= 1;
            while (
              end < quill.getLength() - 1 &&
              quill.getFormat(end, 1).link === href
            )
              end += 1;
            range = { index: start, length: end - start };
            lastRangeRef.current = range;
          }
          linkRangeRef.current = range;
          return {
            href: typeof href === "string" ? href : "",
            selectedText: range.length > 0 ? quill.getText(range) : "",
            canApply: range.length > 0 || typeof href === "string",
          };
        },
        focus: () => quillRef.current?.focus({ preventScroll: true }),
        hasFocus: () => quillRef.current?.hasFocus() ?? false,
        isComposing: () => composingRef.current,
        toggleInline: (name) => {
          withSelection((quill, range) => {
            const active = quill.getFormat(range)[name] === true;
            if (range.length > 0)
              quill.formatText(
                range.index,
                range.length,
                name,
                !active,
                "user",
              );
            else quill.format(name, !active, "user");
          });
        },
        toggleLine: (name, value) => {
          withSelection((quill, range) => {
            const length = Math.max(range.length, 1);
            const current = quill.getFormat(range)[name];
            // The single Checklist control owns both task states, so pressing it
            // on a `checked` line must also read as active and turn the list
            // off, not silently flip the line to `unchecked`.
            const isChecklistToggle =
              name === "list" && (value === "checked" || value === "unchecked");
            const active = isChecklistToggle
              ? current === "checked" || current === "unchecked"
              : current === value;
            quill.formatLine(
              range.index,
              length,
              name,
              active ? false : value,
              "user",
            );
            // Removing the list also removes its nesting: an orphan `indent` is
            // not a valid Journiv line and would leave the row visually inset.
            if (name === "list" && active) {
              quill.formatLine(range.index, length, "indent", false, "user");
            }
          });
        },
        indent: (direction) => {
          withSelection((quill, range) => {
            if (quill.getFormat(range).list == null) return;
            const currentIndent = Number(quill.getFormat(range).indent) || 0;
            const nextIndent = Math.min(
              MAX_LIST_INDENT,
              Math.max(0, currentIndent + direction),
            );
            if (nextIndent === currentIndent) return;
            quill.formatLine(
              range.index,
              Math.max(range.length, 1),
              "indent",
              nextIndent || false,
              "user",
            );
          });
        },
        setLink: (value) => {
          const applied = withSelection((quill, range) => {
            if (range.length > 0)
              quill.formatText(
                range.index,
                range.length,
                "link",
                value,
                "user",
              );
            else quill.format("link", value, "user");
          }, linkRangeRef.current);
          if (applied) linkRangeRef.current = null;
          return applied;
        },
        undo: () => {
          const quill = quillRef.current;
          if (!quill || composingRef.current) return;
          quill.history.undo();
          quill.focus({ preventScroll: true });
          emitStateRef.current?.(quill.getSelection());
        },
        redo: () => {
          const quill = quillRef.current;
          if (!quill || composingRef.current) return;
          quill.history.redo();
          quill.focus({ preventScroll: true });
          emitStateRef.current?.(quill.getSelection());
        },
      }),
      [withSelection],
    );

    useEffect(() => {
      const host = hostRef.current;
      if (!host) return;
      const quill = new Quill(host, {
        formats: [...initialFormatsRef.current],
        modules: {
          toolbar: false,
          // Quill ships an `uploader` module that intercepts dropped and pasted
          // image files and inlines them as base64 data URLs. That would bloat
          // the document, bypass Journiv's media pipeline entirely, and persist
          // a payload no backup could map back to a file. Journiv owns this
          // flow, so the built-in is disabled outright.
          uploader: { handler: () => undefined },
          // Only the writer's own edits are undoable. Quill records `silent`
          // and `api` changes by default, which made Ctrl+Z able to revert the
          // initial document load and leave the entry empty.
          history: { userOnly: true },
        },
        placeholder,
        readOnly: readOnlyRef.current,
      });
      quillRef.current = quill;
      quill.root.dataset.editorIdentity = editorId;
      quill.root.setAttribute(
        "aria-label",
        ariaLabelRef.current ??
          (readOnlyRef.current ? "Entry content" : "Entry body"),
      );
      quill.root.setAttribute(
        "spellcheck",
        readOnlyRef.current ? "false" : "true",
      );
      if (readOnlyRef.current) {
        quill.root.setAttribute("tabindex", "-1");
      } else {
        quill.root.setAttribute("role", "textbox");
        quill.root.setAttribute("aria-multiline", "true");
      }
      // Cloned here, once per surface, so Quill can never mutate the caller's
      // document (a query cache entry, or a recovered draft record).
      const initialDelta = new Delta(
        (cloneDelta(initialContentRef.current).ops ?? []).map((operation) => ({
          insert: operation.insert,
          ...(operation.attributes ? { attributes: operation.attributes } : {}),
        })),
      );
      quill.setContents(initialDelta, "silent");
      // Belt and braces: loading a document is not something to undo.
      quill.history.clear();

      // Nudge the current list line's nesting by one step, clamped to
      // 0…MAX_LIST_INDENT. `indent` is a Journiv list-only modifier, so this is
      // the single place keyboard indenting is allowed to write it.
      const applyListIndent = (index: number, direction: 1 | -1) => {
        const [line, offset] = quill.getLine(index);
        if (!line) return;
        const lineStart = index - offset;
        const format = quill.getFormat(
          lineStart,
          Math.max(line.length() - 1, 1),
        );
        if (format.list == null) return;
        const current = Number(format.indent) || 0;
        const next = Math.min(
          MAX_LIST_INDENT,
          Math.max(0, current + direction),
        );
        if (next === current) return;
        quill.history.cutoff();
        quill.formatLine(lineStart, 1, "indent", next || false, "user");
        quill.history.cutoff();
      };

      // Quill's built-in "list autofill" binding turns
      // `1.`/`2.`/`- `/`* `/`[ ] `/`[x] ` into a list on space. Journiv narrows
      // the ordered trigger to a bare `1.` (Quill renumbers the rest itself) and
      // reads the leading whitespace the marker was typed after as a nesting
      // level, so `\t- ` / `  - ` start an indented item. `[ ] ` / `[x] ` map to
      // the task-list values. Headings and quotes stay with markdownShortcuts.ts.
      for (const binding of quill.keyboard.bindings[" "] ?? []) {
        if (
          !(binding.prefix instanceof RegExp) ||
          !binding.prefix.source.includes("\\[x\\]")
        )
          continue;
        binding.prefix = /^\s*?(1\.|-|\*|\[ ?\]|\[x\])$/;
        binding.handler = (range, context) => {
          if (quill.scroll.query("list") == null) return true;
          const prefix: string = context.prefix ?? "";
          const [line, offset] = quill.getLine(range.index);
          if (!line || offset > prefix.length) return true;
          const leading = prefix.match(/^\s*/u)?.[0] ?? "";
          const marker = prefix.slice(leading.length);
          const value =
            marker === "-" || marker === "*"
              ? "bullet"
              : marker === "[x]"
                ? "checked"
                : marker === "[]" || marker === "[ ]"
                  ? "unchecked"
                  : "ordered";
          const tabs = (leading.match(/\t/gu) ?? []).length;
          const spaces = leading.length - tabs;
          const indent = Math.min(
            MAX_LIST_INDENT,
            tabs + Math.floor(spaces / 2),
          );
          const lineFormats: Record<string, unknown> = { list: value };
          if (indent > 0) lineFormats.indent = indent;
          quill.insertText(range.index, " ", "user");
          quill.history.cutoff();
          quill.updateContents(
            new Delta()
              .retain(range.index - offset)
              .delete(prefix.length + 1)
              .retain(line.length() - 2 - offset)
              .retain(1, lineFormats),
            "user",
          );
          quill.history.cutoff();
          quill.setSelection(range.index - prefix.length, "silent");
          return false;
        };
      }

      // Tab / Shift+Tab nest and un-nest a list line (capped at
      // MAX_LIST_INDENT). Quill only offers these bindings when the line
      // already carries `blockquote`, `indent` or `list`; on a non-list line
      // Journiv swallows the key rather than letting the fallback insert a
      // literal tab or push an `indent` a blockquote may not carry.
      for (const binding of quill.keyboard.bindings.Tab ?? []) {
        const formats = Array.isArray(binding.format) ? binding.format : [];
        if (!formats.includes("indent") || !formats.includes("list")) continue;
        const direction: 1 | -1 = binding.shiftKey ? -1 : 1;
        binding.handler = (range) => {
          applyListIndent(range.index, direction);
          return false;
        };
      }

      const countWords = () => {
        const text = quill.getText().trim();
        return text ? text.split(/\s+/u).length : 0;
      };

      /**
       * Editor state is a render input, so it is only handed out when it has
       * actually changed. Typing a letter into a paragraph moves the caret but
       * changes no format, no selection length and no selected embed — without
       * this, every keystroke re-rendered the whole editor page for a value
       * identical to the one already on screen.
       */
      let lastState: EditorState | null = null;
      // Read by `emitState`, refreshed on the interval below. Never counted
      // inline: that walks the whole document.
      let wordCount = countWords();

      const emitState = (range: Range | null) => {
        if (range) lastRangeRef.current = range;
        const activeRange = range ?? lastRangeRef.current;
        const next: EditorState = {
          formats: activeRange ? quill.getFormat(activeRange) : {},
          focused: range !== null,
          selectionLength: activeRange?.length ?? 0,
          wordCount,
          selectedMedia: mediaKindAt(quill, activeRange?.index),
        };
        if (sameEditorState(lastState, next)) return;
        lastState = next;
        stateChangeRef.current?.(next);
      };
      emitStateRef.current = emitState;

      let wordCountTimer: number | null = null;
      /** Recount once at the end of the current interval, coalescing every
       *  change made inside it (see WORD_COUNT_INTERVAL_MS). */
      const scheduleWordCount = () => {
        if (wordCountTimer !== null) return;
        wordCountTimer = window.setTimeout(() => {
          wordCountTimer = null;
          const next = countWords();
          if (next === wordCount) return;
          wordCount = next;
          emitState(quill.getSelection());
        }, WORD_COUNT_INTERVAL_MS);
      };

      // The gallery only needs telling when the set of inline media changes;
      // the paths themselves are compared so an unrelated edit near an embed
      // does not hand the host a fresh array to re-key on.
      let lastMediaPaths: string[] | null = null;
      const emitInlineMedia = () => {
        const paths = inlineMediaPaths(
          quill.getContents() as unknown as QuillDelta,
        );
        if (
          lastMediaPaths !== null &&
          lastMediaPaths.length === paths.length &&
          paths.every((path, index) => path === lastMediaPaths?.[index])
        )
          return;
        lastMediaPaths = paths;
        inlineMediaChangeRef.current?.(paths);
      };
      // The starting document may already carry inline media (an existing
      // entry), so report it once before any edit.
      emitInlineMedia();

      const handleTextChange = (
        delta: Delta,
        _oldContents: Delta,
        source: string,
      ) => {
        if (source === "user") userChangeRef.current?.();
        scheduleWordCount();
        emitState(quill.getSelection());
        if (mayChangeInlineMedia(delta)) emitInlineMedia();
      };
      const handleSelectionChange = (range: Range | null) => {
        emitState(range);
      };
      const handleCompositionStart = () => {
        composingRef.current = true;
      };
      const handleCompositionEnd = () => {
        composingRef.current = false;
        emitState(quill.getSelection());
      };
      /**
       * Paste sanitiser.
       *
       * `image` is in the editor's format allowlist, so without this a paste of
       * arbitrary HTML could drop `{image: "https://tracker.example.com/x.png"}`
       * straight into a journal entry — an external request every time the
       * entry is opened, and a reference no backup could ever restore. Only
       * Journiv's own media survives a paste; everything else is discarded.
       */
      quill.clipboard.addMatcher("IMG", (node, _delta) => {
        const source = (node as HTMLImageElement).getAttribute("src") ?? "";
        try {
          const url = new URL(source, window.location.origin);
          const isOwnMedia =
            url.origin === window.location.origin &&
            url.pathname.startsWith("/api/v1/media/");
          if (isOwnMedia) {
            // Store it relative, matching what the API hydrates.
            return new Delta().insert({
              image: `${url.pathname}${url.search}`,
            });
          }
        } catch {
          /* not a usable URL */
        }
        return new Delta();
      });

      const filesFrom = (list: FileList | null | undefined) =>
        [...(list ?? [])].filter((file) => file.size > 0);

      const handleDragOver = (event: DragEvent) => {
        if (!filesRef.current || !event.dataTransfer?.types.includes("Files"))
          return;
        event.preventDefault();
        quill.root.classList.add("is-drop-target");
      };
      const handleDragLeave = () =>
        quill.root.classList.remove("is-drop-target");
      const handleDrop = (event: DragEvent) => {
        quill.root.classList.remove("is-drop-target");
        const files = filesFrom(event.dataTransfer?.files);
        if (!filesRef.current || !files.length) return;
        // Without this the browser navigates away to the dropped file.
        event.preventDefault();
        const fallback =
          (quill.getSelection() ?? lastRangeRef.current)?.index ??
          quill.getLength();
        filesRef.current(
          files,
          indexFromPoint(quill, event.clientX, event.clientY, fallback),
        );
      };
      const handlePaste = (event: ClipboardEvent) => {
        const files = filesFrom(event.clipboardData?.files);
        if (!filesRef.current || !files.length) return;
        // Only intercept when actual files are on the clipboard; ordinary text
        // and formatting paste must keep working.
        event.preventDefault();
        const index =
          (quill.getSelection() ?? lastRangeRef.current)?.index ??
          quill.getLength();
        filesRef.current(files, index);
      };

      quill.root.addEventListener("dragover", handleDragOver);
      quill.root.addEventListener("dragleave", handleDragLeave);
      quill.root.addEventListener("drop", handleDrop);
      quill.root.addEventListener("paste", handlePaste);

      quill.on("text-change", handleTextChange);
      quill.on("selection-change", handleSelectionChange);
      quill.root.addEventListener("compositionstart", handleCompositionStart);
      quill.root.addEventListener("compositionend", handleCompositionEnd);
      emitState(null);

      // Markdown input shortcuts are a writing-surface affordance only; the
      // read-only reader must never rewrite what it renders. The rewrite is a
      // "user" change, so it re-enters handleTextChange like any edit —
      // marking the body dirty and refreshing toolbar state.
      const teardownMarkdown = installMarkdownShortcuts(quill, {
        isEnabled: () => !readOnlyRef.current,
        isComposing: () => composingRef.current,
        onApplied: (caretIndex) => emitState({ index: caretIndex, length: 0 }),
      });

      return () => {
        teardownMarkdown();
        if (wordCountTimer !== null) window.clearTimeout(wordCountTimer);
        quill.off("text-change", handleTextChange);
        quill.off("selection-change", handleSelectionChange);
        quill.root.removeEventListener(
          "compositionstart",
          handleCompositionStart,
        );
        quill.root.removeEventListener("compositionend", handleCompositionEnd);
        quill.root.removeEventListener("dragover", handleDragOver);
        quill.root.removeEventListener("dragleave", handleDragLeave);
        quill.root.removeEventListener("drop", handleDrop);
        quill.root.removeEventListener("paste", handlePaste);
        quillRef.current = null;
        emitStateRef.current = null;
        lastRangeRef.current = null;
        linkRangeRef.current = null;
        composingRef.current = false;
        // Local previews belong to this editing session only.
        releaseAllPlaceholders();
        host.replaceChildren();
      };
    }, [editorId, placeholder]);

    useEffect(() => {
      const root = quillRef.current?.root;
      if (!root) return;
      quillRef.current?.enable(!readOnly);
      root.setAttribute("aria-readonly", String(readOnly));
      root.setAttribute(
        "aria-label",
        ariaLabel ?? (readOnly ? "Entry content" : "Entry body"),
      );
      root.setAttribute("spellcheck", readOnly ? "false" : "true");
      if (readOnly) {
        root.setAttribute("tabindex", "-1");
        root.removeAttribute("role");
        root.removeAttribute("aria-multiline");
      } else {
        root.removeAttribute("tabindex");
        root.setAttribute("role", "textbox");
        root.setAttribute("aria-multiline", "true");
      }
    }, [ariaLabel, readOnly]);

    return (
      <div
        className={[
          "jv-prose",
          readOnly ? "jv-prose--reader" : "jv-editor__surface",
          className,
        ]
          .filter(Boolean)
          .join(" ")}
        data-editor-id={editorId}
        ref={hostRef}
      />
    );
  },
);
