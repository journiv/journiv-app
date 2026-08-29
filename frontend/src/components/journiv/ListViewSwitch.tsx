import { Link, useSearch } from "@tanstack/react-router";
import { CalendarDays, Images, List } from "lucide-react";
import type { ReactNode } from "react";
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
    icon: <List aria-hidden="true" size={15} />,
  },
  {
    mode: "calendar",
    label: "Calendar view",
    icon: <CalendarDays aria-hidden="true" size={15} />,
  },
  {
    mode: "media",
    label: "Media view",
    icon: <Images aria-hidden="true" size={15} />,
  },
];

/**
 * Switches the list pane between the Timeline, the Calendar and the Media grid.
 *
 * It only ever changes the `view` search param, so it stays on whatever route
 * is current — a moment open in the reader stays open while the left pane
 * changes, exactly like Day One. Styled as a segmented control (raised surface
 * for the active option, no shadow — DESIGN.md §5), it carries the selected
 * state with colour, a rail and `aria-current`.
 */
export function ListViewSwitch({ className }: { className?: string }) {
  const { view } = useSearch({ strict: false }) as {
    view?: "calendar" | "media";
  };
  const current: ViewMode = view ?? "list";
  return (
    <nav className={cx("jv-view-switch", className)} aria-label="List view">
      {OPTIONS.map((option) => {
        const selected = option.mode === current;
        return (
          <Link
            key={option.mode}
            to="."
            search={(prev: ListViewSearch) => ({
              ...prev,
              view: option.mode === "list" ? undefined : option.mode,
              // The selected day only makes sense inside the calendar.
              date: option.mode === "calendar" ? prev.date : undefined,
            })}
            replace
            aria-current={selected ? "page" : undefined}
            aria-label={option.label}
            title={option.label}
            className={cx("jv-view-switch__option", selected && "is-selected")}
          >
            {option.icon}
          </Link>
        );
      })}
    </nav>
  );
}
