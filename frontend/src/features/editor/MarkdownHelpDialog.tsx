import { AppAdaptiveDialog } from "../../components/journiv/AppAdaptiveDialog";

type MarkdownHelpDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/**
 * A quiet reference for the markdown input shortcuts the writing surface
 * understands (markdownShortcuts.ts). It is informational only — no settings,
 * nothing to save — so it uses the shared adaptive overlay (Drawer on compact,
 * Dialog otherwise) rather than a bespoke surface, and carries no footer.
 */
const SHORTCUTS: ReadonlyArray<{ syntax: string; meaning: string }> = [
  { syntax: "# ", meaning: "Heading (## and ### for smaller headings)" },
  { syntax: "- ", meaning: "Bulleted list (* also works)" },
  { syntax: "1. ", meaning: "Numbered list (start with 1.)" },
  { syntax: "> ", meaning: "Quote" },
  { syntax: "**bold**", meaning: "Bold (__bold__ also works)" },
  { syntax: "*italic*", meaning: "Italic (_italic_ also works)" },
  { syntax: "~~strike~~", meaning: "Strikethrough" },
  { syntax: "[text](https://…)", meaning: "Link" },
];

export function MarkdownHelpDialog({
  open,
  onOpenChange,
}: MarkdownHelpDialogProps) {
  return (
    <AppAdaptiveDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Markdown shortcuts"
      description="Type these while writing and Journiv formats the text for you. Undo once to get the characters back."
      size="sm"
    >
      <dl className="jv-markdown-help">
        {SHORTCUTS.map((item) => (
          <div className="jv-markdown-help__row" key={item.syntax}>
            <dt>
              <code>{item.syntax}</code>
            </dt>
            <dd>{item.meaning}</dd>
          </div>
        ))}
      </dl>
    </AppAdaptiveDialog>
  );
}
