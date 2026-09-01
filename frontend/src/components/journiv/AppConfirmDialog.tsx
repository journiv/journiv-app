import type { ReactNode } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../ui/alert-dialog";
import { Button } from "../ui/button";
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from "../ui/drawer";
import { Spinner } from "../ui/spinner";
import { useCompactViewport } from "../../lib/useCompactViewport";
import { guardDismissal } from "./overlayDismissal";

export interface AppConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  /** A failure notice or one short clarifying line. Anything needing a form
   *  input belongs in `AppAdaptiveDialog` instead. */
  children?: ReactNode;
  confirmLabel: string;
  /** Defaults to "Cancel". */
  cancelLabel?: string;
  destructive?: boolean;
  /** Disables both actions and shows a spinner on the confirm. */
  pending?: boolean;
  onConfirm: () => void | Promise<void>;
}

/**
 * A simple yes/no confirmation, presented as the viewport requires
 * (DESIGN.md §9, "Adaptive overlays"):
 *
 *     <= 860px   Drawer (confirmation sheet)
 *     >  860px   AlertDialog (centred)
 *
 * **The two branches do not have identical semantics, and this does not
 * pretend they do.** Above 860px the surface is a real `alertdialog`. Below it
 * the Drawer exposes `role="dialog"` — Base UI's Drawer reads its role from the
 * shared dialog store and never becomes an `alertdialog`. Forcing the role by
 * hand would claim assertive-announcement behaviour the primitive does not
 * implement, which serves a screen-reader user worse than an honest `dialog`.
 * What *does* hold on both branches is the behaviour DESIGN.md §17 asks for:
 * an accessible name from the title, a description, a real focus trap, an
 * inert background, and focus returned to the trigger on close.
 *
 * `onConfirm` may return a promise; it is awaited. This component never closes
 * itself on confirm — the caller closes on success, so a failed mutation can
 * keep the surface open and show its error. Domain deletion logic stays with
 * the caller.
 *
 * Not for typed or multi-step destructive flows (a title to type back, an
 * acknowledgement, an "Archive instead" alternative) — those are
 * `AppAdaptiveDialog`.
 */
export function AppConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  confirmLabel,
  cancelLabel = "Cancel",
  destructive = false,
  pending = false,
  onConfirm,
}: AppConfirmDialogProps) {
  const compact = useCompactViewport();

  // A confirmation must not be dismissible while its mutation is in flight —
  // closing mid-delete would strand the user with no feedback.
  const handleOpenChange = guardDismissal(onOpenChange, !pending);

  async function confirm() {
    try {
      await onConfirm();
    } catch {
      // The caller owns mutation error state and presentation. Keeping this
      // rejection local prevents an unhandled promise without closing.
    }
  }

  const confirmContent = (
    <>
      {pending && <Spinner data-icon="inline-start" aria-hidden="true" />}
      {confirmLabel}
    </>
  );
  // `danger` is Journiv's destructive treatment: tinted, never filled, so a
  // destructive confirm never reads as the surface's primary action (§6).
  const confirmVariant = destructive ? "danger" : "primary";
  const body = children != null && (
    <div className="jv-overlay__body">{children}</div>
  );

  if (compact) {
    return (
      <Drawer
        open={open}
        onOpenChange={handleOpenChange}
        disablePointerDismissal={pending}
        showSwipeHandle={!pending}
      >
        <DrawerContent className="jv-overlay jv-overlay--sheet">
          {/* Stock base-vega centres a sheet header (its own
              `group-data-[swipe-axis=y]:text-center`); only the padding is
              overridden, since .jv-overlay--sheet already pads the surface. */}
          <DrawerHeader className="p-0">
            <DrawerTitle>{title}</DrawerTitle>
            {description != null && (
              <DrawerDescription>{description}</DrawerDescription>
            )}
          </DrawerHeader>
          {body}
          {/* Confirm on top — it is what the sheet is asking about — with
              cancel under the resting thumb. */}
          <div className="jv-overlay__footer jv-overlay__footer--sheet">
            <Button
              variant={confirmVariant}
              disabled={pending}
              onClick={() => {
                void confirm();
              }}
            >
              {confirmContent}
            </Button>
            <Button
              variant="ghost"
              disabled={pending}
              onClick={() => onOpenChange(false)}
            >
              {cancelLabel}
            </Button>
          </div>
        </DrawerContent>
      </Drawer>
    );
  }

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent className="jv-overlay jv-overlay--dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {description != null && (
            <AlertDialogDescription>{description}</AlertDialogDescription>
          )}
        </AlertDialogHeader>
        {body}
        <div className="jv-overlay__footer">
          <AlertDialogCancel variant="ghost" disabled={pending}>
            {cancelLabel}
          </AlertDialogCancel>
          <AlertDialogAction
            variant={confirmVariant}
            disabled={pending}
            onClick={() => {
              void confirm();
            }}
          >
            {confirmContent}
          </AlertDialogAction>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  );
}
