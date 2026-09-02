import { Link, type LinkProps } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import { MoreHorizontal } from "lucide-react";
import { Fragment, useState } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from "../ui/drawer";
import { IconButton } from "../ui/icon-button";
import { Item, ItemContent, ItemMedia } from "../ui/item";
import { cx } from "../../lib/cx";
import { useCompactViewport } from "../../lib/useCompactViewport";

interface AppMenuActionBase {
  /** Stable key for this action within its menu. */
  id: string;
  label: string;
  /** The action's own icon. A destructive action keeps its own glyph — the
   *  destructive treatment is colour, not an icon override (DESIGN.md §17). */
  icon?: LucideIcon;
  disabled?: boolean;
  /** Draws a hairline above this action, opening a new group. */
  separatorBefore?: boolean;
}

/**
 * Every ⋯ menu in Journiv is a command list, so two kinds cover all of them:
 * one that runs a callback, and one that navigates. There is deliberately no
 * `render` or `children` escape hatch — a rendered `DropdownMenuItem` is
 * meaningless inside the compact action sheet, which is exactly the bug this
 * API exists to prevent. Add a third kind when a real menu needs one.
 */
export type AppMenuAction =
  | (AppMenuActionBase & {
      kind: "command";
      onSelect: () => void;
      destructive?: boolean;
    })
  | (AppMenuActionBase & {
      kind: "link";
      /** Passed straight to TanStack Router's `<Link>`, so routes stay typed. */
      link: LinkProps;
    });

export interface AppAdaptiveMenuProps {
  /** Accessible name for the ⋯ trigger, e.g. `${journal.title} actions`. */
  label: string;
  actions: AppMenuAction[];
  /** Regular-presentation anchoring. */
  align?: "start" | "center" | "end";
}

/**
 * An overflow / context command menu, presented as the viewport requires
 * (DESIGN.md §9, "Adaptive overlays"):
 *
 *     <= 860px   Drawer (bottom action sheet)
 *     >  860px   DropdownMenu anchored to the trigger
 *
 * The 861–1100px band gets the anchored menu: a tablet-width window has the
 * room for one, and touch capability is not what decides this — width is.
 *
 * The compact branch is a Drawer, so its rows are buttons and links in a
 * dialog, not `menuitem`s. That is deliberate: a Drawer is not a menu
 * container, and painting menu roles onto one would describe a structure the
 * surface does not have.
 */
export function AppAdaptiveMenu({
  label,
  actions,
  align = "end",
}: AppAdaptiveMenuProps) {
  const compact = useCompactViewport();
  const [open, setOpen] = useState(false);

  // An empty menu is a bug in the caller, not a surface worth opening.
  if (actions.length === 0) return null;

  const trigger = (
    <IconButton label={label}>
      <MoreHorizontal aria-hidden="true" size={16} />
    </IconButton>
  );

  if (compact) {
    return (
      <Drawer open={open} onOpenChange={setOpen} showSwipeHandle>
        <DrawerTrigger render={trigger} />
        <DrawerContent className="jv-overlay jv-overlay--sheet">
          <DrawerHeader className="p-0">
            {/* The sheet's accessible name; the ⋯ label already says what it
                is, so it does not need repeating on screen. */}
            <DrawerTitle className="sr-only">{label}</DrawerTitle>
          </DrawerHeader>
          <div className="jv-overlay__body jv-sheet-actions">
            {actions.map((action) => {
              const Icon = action.icon;
              const className = cx(
                "jv-sheet-action",
                action.separatorBefore && "jv-sheet-action--separated",
                action.kind === "command" &&
                  action.destructive &&
                  "jv-sheet-action--destructive",
              );
              const content = (
                <>
                  {Icon && (
                    <ItemMedia>
                      <Icon aria-hidden="true" />
                    </ItemMedia>
                  )}
                  <ItemContent>{action.label}</ItemContent>
                </>
              );

              if (action.kind === "link" && !action.disabled) {
                return (
                  <Item
                    key={action.id}
                    size="sm"
                    className={className}
                    render={
                      <Link {...action.link} onClick={() => setOpen(false)} />
                    }
                  >
                    {content}
                  </Item>
                );
              }
              if (action.kind === "link") {
                // Disabled: render the row inert rather than as a live link.
                return (
                  <Item
                    key={action.id}
                    size="sm"
                    className={className}
                    render={<button type="button" disabled />}
                  >
                    {content}
                  </Item>
                );
              }
              return (
                <Item
                  key={action.id}
                  size="sm"
                  className={className}
                  render={
                    <button
                      type="button"
                      disabled={action.disabled}
                      onClick={() => {
                        // Close first: most of these open a confirmation, and
                        // the sheet must be on its way out before that mounts.
                        setOpen(false);
                        action.onSelect();
                      }}
                    />
                  }
                >
                  {content}
                </Item>
              );
            })}
          </div>
        </DrawerContent>
      </Drawer>
    );
  }

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger render={trigger} />
      <DropdownMenuContent align={align}>
        {actions.map((action) => {
          const Icon = action.icon;
          const item =
            action.kind === "link" ? (
              <DropdownMenuItem
                disabled={action.disabled}
                render={<Link {...action.link} />}
              >
                {Icon && <Icon aria-hidden="true" size={15} />}
                {action.label}
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem
                disabled={action.disabled}
                variant={action.destructive ? "destructive" : "default"}
                onClick={action.onSelect}
              >
                {Icon && <Icon aria-hidden="true" size={15} />}
                {action.label}
              </DropdownMenuItem>
            );

          // A Fragment, not a wrapper element: Base UI's Menu walks its own
          // children for roving focus and typeahead, and an intervening DOM
          // node — even `display: contents` — would hide the items from it.
          return (
            <Fragment key={action.id}>
              {action.separatorBefore && <DropdownMenuSeparator />}
              {item}
            </Fragment>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
