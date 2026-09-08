import {
  Bold,
  CircleHelp,
  Ellipsis,
  Heading1,
  Heading2,
  Heading3,
  ImagePlus,
  IndentDecrease,
  IndentIncrease,
  Italic,
  Link,
  List,
  ListChecks,
  ListOrdered,
  Quote,
  Redo2,
  Sparkles,
  Strikethrough,
  Trash2,
  Underline,
  Undo2,
  Unlink,
} from "lucide-react";
import { type PointerEvent, type RefObject, useRef, useState } from "react";
import { Button } from "../../components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import { IconButton } from "../../components/ui/icon-button";
import { Input } from "../../components/ui/input";
import { useCompactViewport } from "../../lib/useCompactViewport";
import {
  Popover,
  PopoverContent,
  PopoverTitle,
  PopoverTrigger,
} from "../../components/ui/popover";
import { MAX_LIST_INDENT } from "./deltaProfile";
import { validateLinkUrl } from "./linkPolicy";
import { MarkdownHelpDialog } from "./MarkdownHelpDialog";
import {
  type MomentDetailsPanelProps,
  MomentDetailsPopover,
} from "./MomentDetailsPopover";
import type {
  EditorState,
  InlineFormat,
  LineFormat,
  LineFormatValue,
  QuillSurfaceHandle,
} from "./QuillSurface";
import { toolbarPlan, useElementWidth } from "./toolbarFit";

type EditorToolbarProps = {
  /**
   * The writing surface, by reference.
   *
   * A ref rather than the handle itself: `QuillSurface` publishes its handle
   * during commit, so a parent that read `ref.current` while rendering would
   * pass `null` on the first render and depend on some later re-render to
   * correct it. The toolbar only ever needs the handle inside an event, which
   * is exactly when a ref is safe to read.
   */
  editor: RefObject<QuillSurfaceHandle | null>;
  state: EditorState;
  disabled?: boolean;
  /** Omit to hide the insert group entirely (for example in a read-only host). */
  onAddMedia?: () => void;
  onRemoveMedia?: () => void;
  /** Metadata editing (mood, location, weather, people, tags). Omit to hide. */
  details?: MomentDetailsPanelProps;
  /**
   * Opens the prompt picker. Passed only while the entry is still empty — the
   * "Write from a prompt" affordance is an empty-state control that leads the
   * insert group and withdraws once the writer types, adds media, or picks a
   * prompt (docs/features/prompts.md).
   */
  onPickPrompt?: () => void;
};

/** Named for what is being removed, never a bare "Delete". */
const REMOVE_LABELS = {
  image: "Remove photo",
  video: "Remove video",
  audio: "Remove audio",
} as const;

const keepEditorSelection = (event: PointerEvent<HTMLButtonElement>) => {
  event.preventDefault();
};

export function EditorToolbar({
  editor,
  state,
  disabled = false,
  onAddMedia,
  onRemoveMedia,
  details,
  onPickPrompt,
}: EditorToolbarProps) {
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkValue, setLinkValue] = useState("");
  const [linkError, setLinkError] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);
  const barRef = useRef<HTMLDivElement>(null);
  const linkActive = typeof state.formats.link === "string";
  const listValue = state.formats.list;
  const checklistActive = listValue === "checked" || listValue === "unchecked";
  const onListLine = typeof listValue === "string";
  // At the compact width the bar is one horizontally scrolling row (the standard
  // mobile pattern) — nothing collapses. At the regular width it measures its
  // own container and gives up groups to the More popover worst-earned first
  // (toolbarFit.ts, docs/features/editor.md).
  const compact = useCompactViewport();
  const { onBar, needsMore } = toolbarPlan(useElementWidth(barRef), {
    onListLine,
    scrollable: compact,
    hasPromptCta: Boolean(onPickPrompt),
  });
  const indentLevel =
    typeof state.formats.indent === "number" ? state.formats.indent : 0;

  const toggleInline = (name: InlineFormat) =>
    editor.current?.toggleInline(name);
  const toggleLine = (name: LineFormat, value: LineFormatValue) =>
    editor.current?.toggleLine(name, value);

  const openLink = () => {
    const context = editor.current?.getLinkContext();
    if (!context?.canApply) return;
    setLinkValue(context.href || "https://");
    setLinkError("");
    setLinkOpen(true);
  };

  const applyLink = () => {
    const safeUrl = validateLinkUrl(linkValue);
    if (!safeUrl) {
      setLinkError("Use an http, https, or mailto link.");
      return;
    }
    if (editor.current?.setLink(safeUrl)) setLinkOpen(false);
    else setLinkError("Select text before applying a link.");
  };

  const removeLink = () => {
    if (editor.current?.setLink(false)) setLinkOpen(false);
  };

  /* The controls that move.
   *
   * Each of these is rendered in exactly ONE place per width — inline on the
   * bar when it fits, inside the More popover when it does not. They are never
   * rendered twice with one copy hidden: two controls with the same accessible
   * name is a trap for assistive technology and for tests alike. */
  const emphasisControls = (
    <>
      <ToolbarButton
        label="Underline"
        pressed={state.formats.underline === true}
        disabled={disabled}
        onClick={() => toggleInline("underline")}
      >
        <Underline aria-hidden="true" size={16} />
      </ToolbarButton>
      <ToolbarButton
        label="Strike"
        pressed={state.formats.strike === true}
        disabled={disabled}
        onClick={() => toggleInline("strike")}
      >
        <Strikethrough aria-hidden="true" size={16} />
      </ToolbarButton>
    </>
  );

  const headingControls = ([1, 2, 3] as const).map((level) => {
    const Icon = level === 1 ? Heading1 : level === 2 ? Heading2 : Heading3;
    return (
      <ToolbarButton
        key={level}
        label={`Heading ${level}`}
        pressed={state.formats.header === level}
        disabled={disabled}
        onClick={() => toggleLine("header", level)}
      >
        <Icon aria-hidden="true" size={16} />
      </ToolbarButton>
    );
  });

  const orderedListControl = (
    <ToolbarButton
      label="Ordered list"
      pressed={state.formats.list === "ordered"}
      disabled={disabled}
      onClick={() => toggleLine("list", "ordered")}
    >
      <ListOrdered aria-hidden="true" size={16} />
    </ToolbarButton>
  );

  /* Only while the caret is on a list line — nesting is a list-only modifier. */
  const nestingControls = onListLine ? (
    <>
      <ToolbarButton
        label="Outdent list item"
        disabled={disabled || indentLevel === 0}
        onClick={() => editor.current?.indent(-1)}
      >
        <IndentDecrease aria-hidden="true" size={16} />
      </ToolbarButton>
      <ToolbarButton
        label="Indent list item"
        disabled={disabled || indentLevel >= MAX_LIST_INDENT}
        onClick={() => editor.current?.indent(1)}
      >
        <IndentIncrease aria-hidden="true" size={16} />
      </ToolbarButton>
    </>
  ) : null;

  const blockquoteControl = (
    <ToolbarButton
      label="Blockquote"
      pressed={state.formats.blockquote === true}
      disabled={disabled}
      onClick={() => toggleLine("blockquote", true)}
    >
      <Quote aria-hidden="true" size={16} />
    </ToolbarButton>
  );

  const historyControls = (
    <>
      <ToolbarButton
        label="Undo"
        disabled={disabled}
        onClick={() => editor.current?.undo()}
      >
        <Undo2 aria-hidden="true" size={16} />
      </ToolbarButton>
      <ToolbarButton
        label="Redo"
        disabled={disabled}
        onClick={() => editor.current?.redo()}
      >
        <Redo2 aria-hidden="true" size={16} />
      </ToolbarButton>
    </>
  );

  const helpControl = (
    <ToolbarButton label="Markdown shortcuts" onClick={() => setHelpOpen(true)}>
      <CircleHelp aria-hidden="true" size={16} />
    </ToolbarButton>
  );

  return (
    <>
      {/* Outer band: full-width chrome under PageBar at regular width, docked
          above the on-screen keyboard at compact (editor.css). The measured row
          is the inner element — it is what `toolbarFit` sizes against, and it
          carries `role="toolbar"` so the band chrome is not in the a11y tree. */}
      <div className="jv-toolbar">
        <div
          className="jv-toolbar__inner"
          ref={barRef}
          role="toolbar"
          aria-label="Editor actions"
        >
          {(onAddMedia ||
            details ||
            onPickPrompt ||
            (state.selectedMedia && onRemoveMedia)) && (
            <>
              {/* Insert group — leads the bar (docs/features/editor.md): add
                media, then Moment details, then — only while the entry is still
                empty — Write from a prompt. Weather, people and tags will join
                this group rather than the formatting controls. */}
              {/* biome-ignore lint/a11y/useSemanticElements: role="group" within role="toolbar" is the ARIA toolbar pattern; <fieldset> is a form construct and wrong here. */}
              <span
                className="jv-toolbar__group"
                role="group"
                aria-label="Insert"
              >
                {onAddMedia && (
                  <ToolbarButton
                    label="Add photo, video or audio"
                    disabled={disabled}
                    onClick={onAddMedia}
                  >
                    <ImagePlus aria-hidden="true" size={16} />
                  </ToolbarButton>
                )}
                {details && (
                  <MomentDetailsPopover {...details} disabled={disabled} />
                )}
                {onPickPrompt && (
                  <ToolbarButton
                    label="Write from a prompt"
                    disabled={disabled}
                    onClick={onPickPrompt}
                  >
                    <Sparkles aria-hidden="true" size={16} />
                  </ToolbarButton>
                )}
                {state.selectedMedia && onRemoveMedia && (
                  <ToolbarButton
                    label={REMOVE_LABELS[state.selectedMedia]}
                    disabled={disabled}
                    onClick={onRemoveMedia}
                  >
                    <Trash2 aria-hidden="true" size={16} />
                  </ToolbarButton>
                )}
              </span>
              <span className="jv-toolbar__divider" aria-hidden="true" />
            </>
          )}
          <ToolbarButton
            label="Bold"
            pressed={state.formats.bold === true}
            disabled={disabled}
            onClick={() => toggleInline("bold")}
          >
            <Bold aria-hidden="true" size={16} />
          </ToolbarButton>
          <ToolbarButton
            label="Italic"
            pressed={state.formats.italic === true}
            disabled={disabled}
            onClick={() => toggleInline("italic")}
          >
            <Italic aria-hidden="true" size={16} />
          </ToolbarButton>
          {onBar.has("emphasis") && emphasisControls}
          <span className="jv-toolbar__divider" aria-hidden="true" />
          {onBar.has("headings") && headingControls}
          <ToolbarButton
            label="Bullet list"
            pressed={state.formats.list === "bullet"}
            disabled={disabled}
            onClick={() => toggleLine("list", "bullet")}
          >
            <List aria-hidden="true" size={16} />
          </ToolbarButton>
          {onBar.has("ordered") && orderedListControl}
          <ToolbarButton
            label="Checklist"
            pressed={checklistActive}
            disabled={disabled}
            onClick={() => toggleLine("list", "unchecked")}
          >
            <ListChecks aria-hidden="true" size={16} />
          </ToolbarButton>
          {onBar.has("nesting") && nestingControls}
          {onBar.has("blockquote") && blockquoteControl}
          <span className="jv-toolbar__divider" aria-hidden="true" />
          <ToolbarButton
            label={linkActive ? "Edit link" : "Add link"}
            pressed={linkActive}
            disabled={disabled || (!linkActive && state.selectionLength === 0)}
            onClick={openLink}
          >
            <Link aria-hidden="true" size={16} />
          </ToolbarButton>
          {onBar.has("history") && historyControls}
          <span className="jv-toolbar__divider" aria-hidden="true" />
          {onBar.has("reference") && helpControl}
          {needsMore && (
            /* Everything the bar could not hold, in the order it would have had. */
            <Popover>
              <PopoverTrigger
                render={<IconButton label="More actions" />}
                disabled={disabled}
                /* Same as the formatting buttons: opening this must not take the
                 writer's selection with it. */
                onPointerDown={keepEditorSelection}
              >
                <Ellipsis aria-hidden="true" size={16} />
              </PopoverTrigger>
              <PopoverContent
                align="end"
                sideOffset={8}
                className="jv-toolbar__more"
              >
                <PopoverTitle className="jv-section-title">
                  More actions
                </PopoverTitle>
                {/* biome-ignore lint/a11y/useSemanticElements: role="toolbar" is the ARIA pattern for a row of formatting controls; <fieldset> is a form construct and wrong here. */}
                <div
                  className="jv-toolbar__more-controls"
                  role="toolbar"
                  aria-label="More actions"
                >
                  {!onBar.has("nesting") && nestingControls}
                  {!onBar.has("headings") && headingControls}
                  {!onBar.has("history") && historyControls}
                  {!onBar.has("ordered") && orderedListControl}
                  {!onBar.has("blockquote") && blockquoteControl}
                  {!onBar.has("emphasis") && emphasisControls}
                  {!onBar.has("reference") && helpControl}
                </div>
              </PopoverContent>
            </Popover>
          )}
        </div>
      </div>

      <MarkdownHelpDialog open={helpOpen} onOpenChange={setHelpOpen} />

      <Dialog open={linkOpen} onOpenChange={setLinkOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add or edit link</DialogTitle>
            <DialogDescription>
              Link the selected text using http, https, or mailto.
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              applyLink();
            }}
          >
            <label htmlFor="editor-link-url">Link URL</label>
            <Input
              id="editor-link-url"
              value={linkValue}
              onChange={(event) => {
                setLinkValue(event.target.value);
                setLinkError("");
              }}
              autoCapitalize="none"
              autoCorrect="off"
              inputMode="url"
            />
            {linkError && (
              <p className="text-sm text-destructive" role="alert">
                {linkError}
              </p>
            )}
            <div className="jv-dialog__actions">
              {linkActive && (
                <Button type="button" variant="ghost" onClick={removeLink}>
                  <Unlink aria-hidden="true" size={17} />
                  Remove
                </Button>
              )}
              <DialogClose render={<Button variant="ghost" />}>
                Cancel
              </DialogClose>
              <Button type="submit" variant="default">
                Apply
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

function ToolbarButton({
  label,
  pressed,
  disabled,
  onClick,
  children,
}: {
  label: string;
  pressed?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <IconButton
      label={label}
      aria-pressed={pressed}
      disabled={disabled}
      /* Critical: keeps the editor selection when the toolbar is pressed. */
      onPointerDown={keepEditorSelection}
      onClick={onClick}
    >
      {children}
    </IconButton>
  );
}
