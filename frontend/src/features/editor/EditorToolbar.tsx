import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import {
  Bold,
  CircleHelp,
  Heading1,
  Heading2,
  Heading3,
  Italic,
  Link,
  List,
  ListOrdered,
  Quote,
  ImagePlus,
  Redo2,
  Trash2,
  Strikethrough,
  Underline,
  Undo2,
  Unlink,
} from "lucide-react";
import { useState, type PointerEvent } from "react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { IconButton } from "../../components/ui/icon-button";
import type {
  EditorState,
  InlineFormat,
  LineFormat,
  LineFormatValue,
  QuillSurfaceHandle,
} from "./QuillSurface";
import { validateLinkUrl } from "./linkPolicy";
import { MarkdownHelpDialog } from "./MarkdownHelpDialog";
import {
  MomentDetailsPopover,
  type MomentDetailsPanelProps,
} from "./MomentDetailsPopover";

type EditorToolbarProps = {
  editor: QuillSurfaceHandle | null;
  state: EditorState;
  disabled?: boolean;
  /** Omit to hide the insert group entirely (for example in a read-only host). */
  onAddMedia?: () => void;
  onRemoveMedia?: () => void;
  /** Metadata editing (mood, location, weather, people, tags). Omit to hide. */
  details?: MomentDetailsPanelProps;
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
}: EditorToolbarProps) {
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkValue, setLinkValue] = useState("");
  const [linkError, setLinkError] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);
  const linkActive = typeof state.formats.link === "string";

  const toggleInline = (name: InlineFormat) => editor?.toggleInline(name);
  const toggleLine = (name: LineFormat, value: LineFormatValue) =>
    editor?.toggleLine(name, value);

  const openLink = () => {
    const context = editor?.getLinkContext();
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
    if (editor?.setLink(safeUrl)) setLinkOpen(false);
    else setLinkError("Select text before applying a link.");
  };

  const removeLink = () => {
    if (editor?.setLink(false)) setLinkOpen(false);
  };

  return (
    <>
      <div className="jv-toolbar" role="toolbar" aria-label="Editor actions">
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
        <span className="jv-toolbar__divider" aria-hidden="true" />
        {([1, 2, 3] as const).map((level) => {
          const Icon =
            level === 1 ? Heading1 : level === 2 ? Heading2 : Heading3;
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
        })}
        <ToolbarButton
          label="Bullet list"
          pressed={state.formats.list === "bullet"}
          disabled={disabled}
          onClick={() => toggleLine("list", "bullet")}
        >
          <List aria-hidden="true" size={16} />
        </ToolbarButton>
        <ToolbarButton
          label="Ordered list"
          pressed={state.formats.list === "ordered"}
          disabled={disabled}
          onClick={() => toggleLine("list", "ordered")}
        >
          <ListOrdered aria-hidden="true" size={16} />
        </ToolbarButton>
        <ToolbarButton
          label="Blockquote"
          pressed={state.formats.blockquote === true}
          disabled={disabled}
          onClick={() => toggleLine("blockquote", true)}
        >
          <Quote aria-hidden="true" size={16} />
        </ToolbarButton>
        <span className="jv-toolbar__divider" aria-hidden="true" />
        <ToolbarButton
          label={linkActive ? "Edit link" : "Add link"}
          pressed={linkActive}
          disabled={disabled || (!linkActive && state.selectionLength === 0)}
          onClick={openLink}
        >
          <Link aria-hidden="true" size={16} />
        </ToolbarButton>
        <ToolbarButton
          label="Undo"
          disabled={disabled}
          onClick={() => editor?.undo()}
        >
          <Undo2 aria-hidden="true" size={16} />
        </ToolbarButton>
        <ToolbarButton
          label="Redo"
          disabled={disabled}
          onClick={() => editor?.redo()}
        >
          <Redo2 aria-hidden="true" size={16} />
        </ToolbarButton>
        {(onAddMedia || details || (state.selectedMedia && onRemoveMedia)) && (
          <>
            <span className="jv-toolbar__divider" aria-hidden="true" />
            {/* Insert group. Weather, people and tags will join this group
                rather than being appended to the formatting controls. */}
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
          </>
        )}
        <span className="jv-toolbar__divider" aria-hidden="true" />
        <ToolbarButton
          label="Markdown shortcuts"
          onClick={() => setHelpOpen(true)}
        >
          <CircleHelp aria-hidden="true" size={16} />
        </ToolbarButton>
        <span className="jv-toolbar__count">
          {state.wordCount} {state.wordCount === 1 ? "word" : "words"}
        </span>
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
