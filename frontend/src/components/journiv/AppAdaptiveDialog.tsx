import type { ReactNode, Ref } from "react";
import { cx } from "../../lib/cx";
import { useCompactViewport } from "../../lib/useCompactViewport";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from "../ui/drawer";
import { guardDismissal } from "./overlayDismissal";

export type AppDialogSize = "sm" | "md" | "lg";

/**
 * Whether the first field of a form in an adaptive overlay should take focus
 * when the overlay opens.
 *
 * In the centred dialog, yes: the pointer is already there, nothing moves, and
 * it saves a click. In the sheet, no. The sheet opens from a tap, so focusing a
 * text input happens inside the user gesture and summons the on-screen
 * keyboard, which eats roughly a third of an already short viewport before the
 * user has decided they want to type — and on a long form it pushes the surface
 * out from under them (DESIGN.md §9, §17).
 *
 * This lives here rather than in feature code on purpose. §9 forbids feature
 * code from asking how wide the window is; asking the adaptive-overlay module
 * "should this field autofocus?" keeps the rule and its one media query in the
 * same place as the component that owns the presentation switch.
 */
export function useOverlayAutoFocus(): boolean {
  return !useCompactViewport();
}

/** Regular-presentation width only — the sheet always spans the viewport.
 *  The `sm:` half is not redundant: `DialogContent` ships `sm:max-w-md`, and
 *  tailwind-merge only replaces a class within the same variant, so a bare
 *  `max-w-2xl` would still be overridden above 640px. */
const SIZE_CLASS: Record<AppDialogSize, string> = {
  sm: "max-w-sm sm:max-w-sm",
  md: "max-w-md sm:max-w-md",
  lg: "max-w-2xl sm:max-w-2xl",
};

export interface AppAdaptiveDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  /** Optional controls that belong with the fixed header, such as source tabs. */
  headerExtra?: ReactNode;
  /** Keeps the accessible name while hiding the title visually. */
  titleVisuallyHidden?: boolean;
  children: ReactNode;
  /** The action row. Exactly one primary action (DESIGN.md §6). */
  footer?: ReactNode;
  /** Regular-presentation width. There is deliberately no `full`. */
  size?: AppDialogSize;
  /** When false, Escape, outside press and swipe cannot close the surface.
   *  The caller still owns dirty state, discard prompts and cleanup. */
  dismissible?: boolean;
  /** Lets a virtualized child observe the shared body scroll owner without
   *  introducing a nested scrolling region. */
  bodyRef?: Ref<HTMLDivElement>;
}

/**
 * A form or other substantial modal workflow, presented as the viewport
 * requires (DESIGN.md §9, "Adaptive overlays"):
 *
 *     <= 860px   Drawer (bottom sheet)
 *     >  860px   Dialog (centred)
 *
 * Only the chosen branch is mounted — never both with one hidden, which would
 * duplicate every control, accessible name and `useId()` inside the overlay.
 * Crossing 860px therefore remounts the primitive, so state that must survive
 * (form values, drafts) belongs in the caller, above this component.
 *
 * This is not the place for a simple yes/no question — use `AppConfirmDialog`.
 * It *is* the place for a destructive flow that needs typed confirmation, an
 * acknowledgement, or an alternative action.
 */
export function AppAdaptiveDialog({
  open,
  onOpenChange,
  title,
  description,
  headerExtra,
  titleVisuallyHidden = false,
  children,
  footer,
  size = "md",
  dismissible = true,
  bodyRef,
}: AppAdaptiveDialogProps) {
  const compact = useCompactViewport();
  const handleOpenChange = guardDismissal(onOpenChange, dismissible);

  // Built once and slotted into whichever branch renders, so the two branches
  // cannot drift. Only the title/description differ — they are different
  // primitives and must be.
  const body = (
    <div ref={bodyRef} className="jv-overlay__body">
      {children}
    </div>
  );
  const titleClass = titleVisuallyHidden ? "sr-only" : undefined;

  if (compact) {
    return (
      <Drawer
        open={open}
        onOpenChange={handleOpenChange}
        disablePointerDismissal={!dismissible}
        showSwipeHandle={dismissible}
      >
        <DrawerContent className="jv-overlay jv-overlay--sheet">
          {/* Stock base-vega centres a sheet header (its own
              `group-data-[swipe-axis=y]:text-center`); only the padding is
              overridden, since .jv-overlay--sheet already pads the surface. */}
          <DrawerHeader className="p-0">
            <DrawerTitle className={titleClass}>{title}</DrawerTitle>
            {description != null && (
              <DrawerDescription>{description}</DrawerDescription>
            )}
            {headerExtra}
          </DrawerHeader>
          {body}
          {footer != null && (
            <div className="jv-overlay__footer jv-overlay__footer--sheet">
              {footer}
            </div>
          )}
        </DrawerContent>
      </Drawer>
    );
  }

  return (
    <Dialog
      open={open}
      onOpenChange={handleOpenChange}
      disablePointerDismissal={!dismissible}
    >
      <DialogContent
        className={cx("jv-overlay jv-overlay--dialog", SIZE_CLASS[size])}
        showCloseButton={dismissible}
      >
        <DialogHeader>
          <DialogTitle className={titleClass}>{title}</DialogTitle>
          {description != null && (
            <DialogDescription>{description}</DialogDescription>
          )}
          {headerExtra}
        </DialogHeader>
        {body}
        {footer != null && <div className="jv-overlay__footer">{footer}</div>}
      </DialogContent>
    </Dialog>
  );
}
