import Quill, { Delta, type Range } from "quill";
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react";
import type { QuillDelta } from "../../api/generated/types.gen";
import type { InlineMediaKind } from "./deltaProfile";
import {
  findPlaceholderIndex,
  type PlaceholderState,
  releaseAllPlaceholders,
  setPlaceholderState as setPlaceholderStateDom,
  UPLOAD_BLOT_NAME,
} from "./uploadPlaceholder";
import {
  cloneDelta,
  INLINE_MEDIA_KINDS,
  isQuillDocumentDelta,
  isReaderDocumentDelta,
  JOURNIV_DELTA_FORMATS,
  stripUploadPlaceholders,
} from "./deltaProfile";
import "./mediaBlots";
import "quill/dist/quill.core.css";
import "./quill-adapter.css";

export interface QuillSurfaceHandle {
  getContents(): QuillDelta;
  /** Caret position, captured before anything that can steal focus. */
  getSelectionIndex(): number;
  /** Inserts a pending-upload placeholder on its own line. */
  insertPlaceholder(index: number, uploadId: string): void;
  /** Swaps a placeholder for durable media. False when it is no longer there. */
  replacePlaceholder(
    uploadId: string,
    kind: InlineMediaKind,
    source: string,
  ): boolean;
  removePlaceholder(uploadId: string): boolean;
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
  setLink(value: string | false): boolean;
  undo(): void;
  redo(): void;
}

export type InlineFormat = "bold" | "italic" | "underline" | "strike";
export type LineFormat = "header" | "list" | "blockquote";
export type LineFormatValue = 1 | 2 | 3 | "bullet" | "ordered" | true;

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
    caretRangeFromPoint?: (x: number, y: number) => Range | null;
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

/** The media kind at a document position, if the op there is a media embed. */
function mediaKindAt(quill: Quill, index?: number): InlineMediaKind | null {
  if (typeof index !== "number") return null;
  for (const candidate of [index, index - 1]) {
    if (candidate < 0) continue;
    const [op] = quill.getContents(candidate, 1).ops ?? [];
    const insert = op?.insert;
    if (!insert || typeof insert === "string") continue;
    const kind = Object.keys(insert)[0] as InlineMediaKind;
    if ((INLINE_MEDIA_KINDS as readonly string[]).includes(kind)) return kind;
  }
  return null;
}

export const QuillSurface = forwardRef<QuillSurfaceHandle, QuillSurfaceProps>(
  function QuillSurface(
    {
      initialContent,
      editorId,
      onUserChange,
      onStateChange,
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
    const initialContentRef = useRef(cloneDelta(initialContent));
    const initialReadOnlyRef = useRef(readOnly);
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
    const initialAriaLabelRef = useRef(
      ariaLabel ?? (readOnly ? "Entry content" : "Entry body"),
    );
    const filesRef = useRef(onFiles);
    filesRef.current = onFiles;
    const userChangeRef = useRef(onUserChange);
    const stateChangeRef = useRef(onStateChange);
    userChangeRef.current = onUserChange;
    stateChangeRef.current = onStateChange;

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
          // mid-upload still yields a valid saveable Delta.
          const stripped = stripUploadPlaceholders(
            contents as unknown as QuillDelta,
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
            const active = quill.getFormat(range)[name] === value;
            quill.formatLine(
              range.index,
              Math.max(range.length, 1),
              name,
              active ? false : value,
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
        readOnly: initialReadOnlyRef.current,
      });
      quillRef.current = quill;
      quill.root.dataset.editorIdentity = editorId;
      quill.root.setAttribute("aria-label", initialAriaLabelRef.current);
      quill.root.setAttribute(
        "spellcheck",
        initialReadOnlyRef.current ? "false" : "true",
      );
      if (initialReadOnlyRef.current) {
        quill.root.setAttribute("tabindex", "-1");
      } else {
        quill.root.setAttribute("role", "textbox");
        quill.root.setAttribute("aria-multiline", "true");
      }
      const initialDelta = new Delta(
        (initialContentRef.current.ops ?? []).map((operation) => ({
          insert: operation.insert,
          ...(operation.attributes ? { attributes: operation.attributes } : {}),
        })),
      );
      quill.setContents(initialDelta, "silent");
      // Belt and braces: loading a document is not something to undo.
      quill.history.clear();

      const getWordCount = () => {
        const text = quill.getText().trim();
        return text ? text.split(/\s+/u).length : 0;
      };
      const emitState = (range: Range | null) => {
        if (range) lastRangeRef.current = range;
        const activeRange = range ?? lastRangeRef.current;
        stateChangeRef.current?.({
          formats: activeRange ? quill.getFormat(activeRange) : {},
          focused: range !== null,
          selectionLength: activeRange?.length ?? 0,
          wordCount: getWordCount(),
          selectedMedia: mediaKindAt(quill, activeRange?.index),
        });
      };
      emitStateRef.current = emitState;

      const handleTextChange = (
        _delta: Delta,
        _oldContents: Delta,
        source: string,
      ) => {
        if (source === "user") userChangeRef.current?.();
        emitState(quill.getSelection());
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

      return () => {
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
      quillRef.current?.enable(!readOnly);
    }, [readOnly]);

    return (
      <div
        className={[
          "jv-prose",
          initialReadOnlyRef.current
            ? "jv-prose--reader"
            : "jv-editor__surface",
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
