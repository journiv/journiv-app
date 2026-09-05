import { Sparkles, X } from "lucide-react";
import { IconButton } from "../../components/ui/icon-button";
import "./prompt-banner.css";

/**
 * The prompt-context strip shared by the editor and Reader
 * (docs/features/prompts.md). The editor may remove the link; the Reader only
 * names its saved source.
 */
export function PromptBanner({
  text,
  onRemove,
  readOnly = false,
}: {
  text: string;
  onRemove?: () => void;
  /** The Reader names the source without offering an edit control. */
  readOnly?: boolean;
}) {
  const label = readOnly ? "Written from a prompt:" : "Prompt";
  const ariaLabel = readOnly
    ? "Written from a prompt"
    : "Writing from a prompt";

  return (
    <aside className="jv-prompt-banner" aria-label={ariaLabel}>
      <Sparkles
        className="jv-prompt-banner__icon"
        aria-hidden="true"
        size={15}
      />
      <div className="jv-prompt-banner__body">
        <span className="jv-prompt-banner__label jv-caption">{label}</span>
        <p className="jv-prompt-banner__text jv-body">{text}</p>
      </div>
      {onRemove && !readOnly && (
        <IconButton
          label="Remove prompt"
          size="sm"
          className="jv-prompt-banner__remove"
          onClick={onRemove}
        >
          <X aria-hidden="true" size={15} />
        </IconButton>
      )}
    </aside>
  );
}
