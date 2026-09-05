import { ChevronRight } from "lucide-react";
import type { PromptResponse } from "../../api/generated/types.gen";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { categoryLabel, promptMetaParts } from "./promptDisplay";

/**
 * One prompt in the browser list (docs/features/prompts.md). A quiet structured
 * card — category badge, the prompt itself, a meta line, and the surface's
 * select action. The action label differs by surface ("Write" on the library
 * page, "Insert" in the editor picker) but nothing else does, so both surfaces
 * render this component.
 *
 * `usageCount` is the current writer's number of Moments linked to this prompt.
 */
export function PromptCard({
  prompt,
  actionLabel,
  onSelect,
  usageCount,
}: {
  prompt: PromptResponse;
  actionLabel: string;
  onSelect: (prompt: PromptResponse) => void;
  usageCount?: number;
}) {
  const meta = promptMetaParts(prompt);
  const written = typeof usageCount === "number" && usageCount > 0;
  return (
    <article className="jv-prompt-card">
      <div className="jv-prompt-card__head">
        <Badge variant="outline">{categoryLabel(prompt.category)}</Badge>
        {written && (
          <span className="jv-prompt-card__usage jv-caption">
            Written {usageCount} {usageCount === 1 ? "time" : "times"}
          </span>
        )}
      </div>
      <p className="jv-prompt-card__text jv-body">{prompt.text}</p>
      <div className="jv-prompt-card__foot">
        <p className="jv-meta jv-prompt-card__meta">{meta.join(" · ")}</p>
        <Button
          variant="ghost"
          size="sm"
          className="jv-prompt-card__action"
          aria-label={`${actionLabel}: ${prompt.text}`}
          onClick={() => onSelect(prompt)}
        >
          {actionLabel}
          <ChevronRight aria-hidden="true" size={15} />
        </Button>
      </div>
    </article>
  );
}
