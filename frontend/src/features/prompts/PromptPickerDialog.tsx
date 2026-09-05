import type { PromptResponse } from "../../api/generated/types.gen";
import { AppAdaptiveDialog } from "../../components/journiv/AppAdaptiveDialog";
import { Button } from "../../components/ui/button";
import { PromptBrowser } from "./PromptBrowser";

/**
 * The in-editor prompt picker (docs/features/prompts.md). Presented through
 * `AppAdaptiveDialog` — a centred dialog above 860px, a bottom sheet below —
 * so it follows the same overlay contract as every other substantial Journiv
 * surface. The body is the shared `PromptBrowser`; picking a prompt calls
 * `onSelect` and closes.
 *
 * There is no primary footer action: the choice is made per row in the list,
 * so the footer carries only Cancel.
 */
export function PromptPickerDialog({
  open,
  onOpenChange,
  onSelect,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (prompt: PromptResponse) => void;
}) {
  return (
    <AppAdaptiveDialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title="Prompts"
      description="Pick a prompt to start this entry from."
      footer={
        <Button variant="ghost" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
      }
    >
      <PromptBrowser
        variant="overlay"
        selectActionLabel="Insert"
        dailyActionLabel="Insert prompt"
        onSelectPrompt={(prompt) => {
          onSelect(prompt);
          onOpenChange(false);
        }}
      />
    </AppAdaptiveDialog>
  );
}
