/**
 * `dismissible` for the adaptive overlays (DESIGN.md, "Adaptive overlays").
 *
 * None of Base UI's `Dialog.Root`, `AlertDialog.Root` or `Drawer.Root` has a
 * `dismissible` prop — Journiv's is implemented here rather than forwarded.
 * All three share one `onOpenChange(open, eventDetails)` signature where
 * `eventDetails.reason` names what tried to close the surface and
 * `eventDetails.cancel()` stops Base UI acting on it, so one helper covers all
 * three branches.
 *
 * `dismissible={false}` turns off the *implicit* ways out — Escape, a press
 * outside, a swipe, the platform close watcher, focus leaving. It never blocks
 * an explicit Cancel/Close button, and it knows nothing about unsaved changes:
 * dirty state, discard prompts and cleanup stay with the caller.
 */

/** Close reasons that are the user leaving by implication, not by choosing to. */
const IMPLICIT_CLOSE_REASONS = new Set([
  "escape-key",
  "outside-press",
  "swipe",
  "close-watcher",
  "focus-out",
]);

/** The slice of Base UI's change-event details this helper needs. */
type CloseEventDetails = {
  reason: string;
  cancel: () => void;
};

/**
 * Wraps a caller's `onOpenChange` so implicit dismissal is suppressed when
 * `dismissible` is false. Pass the result straight to the Base UI root.
 */
export function guardDismissal(
  onOpenChange: (open: boolean) => void,
  dismissible: boolean,
) {
  return (open: boolean, eventDetails: CloseEventDetails) => {
    if (
      !dismissible &&
      !open &&
      IMPLICIT_CLOSE_REASONS.has(eventDetails.reason)
    ) {
      eventDetails.cancel();
      return;
    }
    onOpenChange(open);
  };
}
