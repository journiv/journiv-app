import { SlidersHorizontal } from "lucide-react";
import {
  MomentDetailsPanel,
  type MomentDetailsPanelProps,
} from "../../components/journiv/MomentDetailsPanel";
import { IconButton } from "../../components/ui/icon-button";
import {
  Popover,
  PopoverContent,
  PopoverTitle,
  PopoverTrigger,
} from "../../components/ui/popover";
import { ImmichSuggestedPeople } from "./immich/ImmichSuggestedPeople";

// The metadata field group itself now lives in components/journiv (a second
// consumer, Quick Log, shares it — docs/features/quicklog.md). This file keeps
// only the editor-toolbar presentation: the popover shell and the Immich
// people-suggestion strip, which stays feature-local and is injected through
// the panel's `renderPeopleSuggestions` slot.
export {
  formatWeatherSummary,
  MomentDetailsPanel,
  type MomentDetailsPanelProps,
} from "../../components/journiv/MomentDetailsPanel";

/**
 * Editing for the metadata the reader shows via `MomentMeta` and `MomentChips`:
 * mood, location, weather, people and tags. Lives in the editor toolbar's Insert
 * group as a single "Details" control (docs/features/editor.md) because five
 * separate toolbar buttons would crowd the bar.
 */
export function MomentDetailsPopover(props: MomentDetailsPanelProps) {
  const { hasImmichMedia = false, ...panelProps } = props;
  return (
    <Popover>
      {/* No onPointerDown/preventDefault here: unlike the formatting buttons,
          the metadata popover does not depend on the editor selection. */}
      <PopoverTrigger
        render={<IconButton label="Moment details" />}
        disabled={props.disabled}
      >
        <SlidersHorizontal aria-hidden="true" size={16} />
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={8} className="jv-details-popover">
        <PopoverTitle className="jv-section-title">Moment details</PopoverTitle>
        <MomentDetailsPanel
          {...panelProps}
          renderPeopleSuggestions={({
            momentId,
            selectedIds,
            busy,
            onAdd,
            onAddAll,
          }) => (
            <ImmichSuggestedPeople
              momentId={momentId}
              enabled={hasImmichMedia && Boolean(momentId)}
              selectedIds={selectedIds}
              busy={busy}
              onAdd={onAdd}
              onAddAll={onAddAll}
            />
          )}
        />
      </PopoverContent>
    </Popover>
  );
}
