import { Check, PencilLine, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { Spinner } from "../../components/ui/spinner";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverTitle,
  PopoverTrigger,
} from "../../components/ui/popover";
import { localDraftFailureMessage } from "./DraftRecovery";
import type { DraftStatus } from "./useLocalDraft";

type SaveStatusProps = {
  /** A save to the journal is in flight. */
  saving: boolean;
  /** The form holds edits that are not in the journal yet. */
  dirty: boolean;
  /** This entry already exists on the server, so "not dirty" means "in sync". */
  hasMoment: boolean;
  /** The local-device copy's state (docs/features/editor.md — Local drafts). */
  localStatus: DraftStatus;
};

type Tone = "saving" | "danger" | "unsaved" | "saved" | "idle";

type StatusView = {
  tone: Tone;
  /** The glanceable word beside the icon. */
  label: string;
  /** The sentence shown in the popover and given to assistive technology. */
  detail: string;
  icon: ReactNode;
};

function describe({
  saving,
  dirty,
  hasMoment,
  localStatus,
}: SaveStatusProps): StatusView {
  if (saving) {
    return {
      tone: "saving",
      label: "Saving…",
      detail: "Saving this entry to your journal.",
      icon: <Spinner aria-hidden="true" className="size-3.5" />,
    };
  }

  const failure = localDraftFailureMessage(localStatus);
  if (failure) {
    return {
      tone: "danger",
      label: "Not saved",
      detail: failure,
      icon: <TriangleAlert aria-hidden="true" size={14} />,
    };
  }

  if (dirty) {
    const detail =
      localStatus === "saved"
        ? "Saved on this device, not in your journal yet. Press Done to save it."
        : localStatus === "saving"
          ? "Keeping a copy on this device… Press Done to save it to your journal."
          : "Saved on this device as you write. Press Done to save it to your journal.";
    return {
      tone: "unsaved",
      label: "Unsaved",
      detail,
      icon: <PencilLine aria-hidden="true" size={14} />,
    };
  }

  if (hasMoment) {
    return {
      tone: "saved",
      label: "Saved",
      detail: "Every change here is saved to your journal.",
      icon: <Check aria-hidden="true" size={14} />,
    };
  }

  return {
    tone: "idle",
    label: "No changes",
    detail:
      "Nothing to save yet. Press Done to add this entry to your journal.",
    icon: <Check aria-hidden="true" size={14} />,
  };
}

/**
 * The single save indicator in the editor's PageBar, at every width.
 *
 * It folds together what used to be two separate elements: the bare
 * "Unsaved changes" / "No changes" text in the bar (hidden on compact), and the
 * "Saved on this device as you write…" line below the header. The glanceable
 * state is an icon plus one word; the full explanation is one tap away in the
 * popover, and is also the button's accessible name so nothing is lost when the
 * popover is closed or a screen reader is in use. Storage failures still get a
 * loud in-flow alert from `LocalDraftStatus` — this control is the calm case.
 */
export function SaveStatus(props: SaveStatusProps) {
  const view = describe(props);

  return (
    <Popover>
      <PopoverTrigger
        render={
          <button
            type="button"
            className="jv-save-status"
            data-tone={view.tone}
            aria-label={`${view.label}. ${view.detail}`}
          />
        }
      >
        {view.icon}
        {/* The word is dropped on the one-pane layout, where the PageBar has no
            room for it beside the journal selector; the icon plus the button's
            aria-label still carry the state. */}
        <span className="jv-save-status__word" aria-hidden="true">
          {view.label}
        </span>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={8}
        className="jv-save-status__detail"
      >
        <PopoverTitle className="jv-section-title">{view.label}</PopoverTitle>
        <PopoverDescription className="jv-meta">
          {view.detail}
        </PopoverDescription>
      </PopoverContent>
    </Popover>
  );
}
