import { Link, useSearch } from "@tanstack/react-router";
import { CalendarDays, Images, List } from "lucide-react";
import type { ReactNode } from "react";
import { buttonVariants } from "../../components/ui/button";
import { ButtonGroup } from "../../components/ui/button-group";
import { cx } from "../../lib/cx";

type ViewMode = "list" | "calendar" | "media";
type ListViewSearch = Record<string, unknown> & {
  date?: string;
  view?: "calendar" | "media";
};

const OPTIONS: Array<{ mode: ViewMode; label: string; icon: ReactNode }> = [
  {
    mode: "list",
    label: "List view",
    icon: <List aria-hidden="true" />,
  },
  {
    mode: "calendar",
    label: "Calendar view",
    icon: <CalendarDays aria-hidden="true" />,
  },
  {
    mode: "media",
    label: "Media view",
    icon: <Images aria-hidden="true" />,
  },
];

/**
 * Switches the list pane between the Timeline, the Calendar and the Media grid.
 *
 * Three router `<Link>`s in a stock `ButtonGroup` — base-vega's segmented form
 * built out of the primitive whose semantics actually match. Each option only
 * ever changes the `view` search param, so it stays on whatever route is
 * current: a moment open in the reader stays open while the left pane changes,
 * exactly like Day One.
 *
 * This used to be a `ToggleGroup` with the links slotted into its items, which
 * asked one element to be a toggle button and a link at the same time. It is
 * not a distinction on paper: the rendered anchors carried `aria-pressed`,
 * which ARIA does not allow on `role="link"`, plus a stray `type="button"`,
 * and the group's roving `tabindex` took two of the three links out of the tab
 * order in exchange for arrow keys that did not drive navigation. Nothing here
 * is pressed — one of three destinations is *current*, which is `aria-current`
 * (DESIGN.md).
 */
export function ListViewSwitch({ className }: { className?: string }) {
  const { view } = useSearch({ strict: false }) as {
    view?: "calendar" | "media";
  };
  const current: ViewMode = view ?? "list";
  return (
    <ButtonGroup
      className={cx("jv-view-switch", className)}
      aria-label="List view"
    >
      {OPTIONS.map((option) => {
        const selected = option.mode === current;
        return (
          <Link
            key={option.mode}
            data-slot="button"
            className={buttonVariants({ variant: "outline", size: "icon-sm" })}
            aria-current={selected ? "page" : undefined}
            aria-label={option.label}
            title={option.label}
            to="."
            search={(prev: ListViewSearch) => ({
              ...prev,
              view: option.mode === "list" ? undefined : option.mode,
              // The selected day only makes sense inside the calendar.
              date: option.mode === "calendar" ? prev.date : undefined,
            })}
            replace
          >
            {option.icon}
          </Link>
        );
      })}
    </ButtonGroup>
  );
}
