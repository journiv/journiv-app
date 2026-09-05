import { Shuffle, Sparkles } from "lucide-react";
import type { PromptResponse } from "../../api/generated/types.gen";
import { Button } from "../../components/ui/button";
import { promptMetaParts } from "./promptDisplay";

/**
 * The "Prompt of the day" hero at the top of the browser (docs/features/prompts.md).
 *
 * `GET /prompts/daily` returns a fresh prompt each day and 204 once the writer
 * has already started an entry from it — which arrives as `prompt = null`, and
 * the card then becomes a small "done for today" note that still offers a
 * random prompt. Shuffle swaps the shown prompt for a random one without
 * touching the daily rotation.
 *
 * It is a plain bordered block, not a `Card`: the hero is the first thing in
 * the scroll owner (the Library body, or the dialog body), and a `Card`'s ring
 * shadow is clipped by that container's top edge. A border draws on the
 * border-box and cannot be clipped.
 */
export function DailyPromptCard({
  prompt,
  shuffledPrompt,
  actionLabel,
  onSelect,
  onShuffle,
  shuffling,
  shuffleUnavailable,
}: {
  /** Today's prompt, or `null` when the day's prompt is already answered. */
  prompt: PromptResponse | null;
  /** A random prompt the writer shuffled to, shown instead of `prompt`. */
  shuffledPrompt: PromptResponse | null;
  actionLabel: string;
  onSelect: (prompt: PromptResponse) => void;
  onShuffle: () => void;
  shuffling: boolean;
  /** The random endpoint reported no prompts available. */
  shuffleUnavailable: boolean;
}) {
  const shown = shuffledPrompt ?? prompt;
  const isShuffled = shuffledPrompt != null;

  return (
    <section className="jv-prompt-daily" aria-label="Prompt of the day">
      <p className="jv-prompt-daily__eyebrow jv-label">
        <Sparkles aria-hidden="true" size={14} />
        {isShuffled ? "A prompt to try" : "Prompt of the day"}
      </p>

      {shown ? (
        <>
          <p className="jv-prompt-daily__text">{shown.text}</p>
          <p className="jv-meta">{promptMetaParts(shown).join(" · ")}</p>
        </>
      ) : (
        <p className="jv-prompt-daily__text jv-prompt-daily__text--muted">
          {shuffleUnavailable
            ? "There are no active prompts right now. Check back later."
            : "You’ve started an entry from today’s prompt. A new one arrives tomorrow."}
        </p>
      )}

      <div className="jv-prompt-daily__actions">
        {shown && (
          <Button variant="default" onClick={() => onSelect(shown)}>
            {actionLabel}
          </Button>
        )}
        <Button
          variant="ghost"
          onClick={onShuffle}
          disabled={shuffling || shuffleUnavailable}
        >
          <Shuffle aria-hidden="true" size={15} />
          {shown ? "Shuffle" : "Try another prompt"}
        </Button>
      </div>

      {shuffleUnavailable && (
        <p className="jv-caption" role="status">
          No prompts are available to shuffle to right now.
        </p>
      )}
    </section>
  );
}
