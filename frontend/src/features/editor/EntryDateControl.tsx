import { CalendarDays } from "lucide-react";
import { lazy, Suspense } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Popover,
  PopoverContent,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  browserTimeZone,
  formatDayLong,
  formatTimeOfDay,
  type WallTimeParts,
  wallTimePartsInZone,
  zonedWallTimeToUtcIso,
} from "@/lib/datetime";

// react-day-picker is a chunk of its own — it is only needed once the popover
// is open, and keeping it out of the editor's mount path keeps the editor light.
const Calendar = lazy(() =>
  import("@/components/ui/calendar").then((module) => ({
    default: module.Calendar,
  })),
);

/**
 * The editor's editable version of the `EntryHeader` date line (docs/features/editor.md).
 * The reader passes nothing to `EntryHeader.dateControl` and keeps a plain
 * `<p>`; only the editor mounts this.
 *
 * A new entry is created in the browser's zone; editing an existing Moment
 * keeps `loggedTimezone` and reinterprets the newly picked wall-clock in it —
 * so `onChange` always reports the zone the instant belongs to. It fires on
 * discrete actions (a day click, a committed time change), never per keystroke,
 * and there is no primary action here — the surface's primary is Done.
 */
export type EntryDateControlProps = {
  loggedAtUtc: string;
  loggedTimezone: string;
  onChange: (next: { utc: string; timezone: string }) => void | Promise<void>;
  /** A persistence attempt is in flight. */
  busy?: boolean;
  /** The editor is read-only (saving). */
  disabled?: boolean;
  /** A failed persist, shown inside the popover. */
  error?: string;
};

const pad2 = (n: number) => String(n).padStart(2, "0");

// The caption's month/year dropdowns need an explicit range. Left to itself
// react-day-picker caps the end at December of the current year, which would
// block scheduling an entry into next year; journaling also runs backwards
// (imported archives), so the floor is deliberately generous.
const CALENDAR_START_MONTH = new Date(1970, 0);
const calendarEndMonth = () => new Date(new Date().getFullYear() + 1, 11);

export function EntryDateControl({
  loggedAtUtc,
  loggedTimezone,
  onChange,
  busy = false,
  disabled = false,
  error,
}: EntryDateControlProps) {
  const parts = wallTimePartsInZone(loggedAtUtc, loggedTimezone);
  const zoneDiffers = loggedTimezone !== browserTimeZone();
  const dayLabel = formatDayLong(loggedAtUtc, loggedTimezone);
  const timeLabel = formatTimeOfDay(loggedAtUtc, loggedTimezone);

  // `react-day-picker` deals in a bare Date — used for y/m/d only, never
  // persisted as-is (its `toISOString()` would be browser-local midnight).
  const selectedDay = new Date(parts.year, parts.month - 1, parts.day);
  const timeValue = `${pad2(parts.hour)}:${pad2(parts.minute)}`;

  const commit = (next: Partial<WallTimeParts>) => {
    const utc = zonedWallTimeToUtcIso({ ...parts, ...next }, loggedTimezone);
    void onChange({ utc, timezone: loggedTimezone });
  };

  return (
    <Popover>
      <PopoverTrigger
        className="jv-date-control__trigger jv-meta"
        aria-label="Change entry date and time"
        disabled={disabled || busy}
      >
        <span>
          {dayLabel} · {timeLabel}
        </span>
        <CalendarDays aria-hidden="true" size={13} />
      </PopoverTrigger>
      <PopoverContent align="start" className="jv-date-control__popover">
        <PopoverTitle className="jv-section-title">
          Entry date &amp; time
        </PopoverTitle>

        <div className="jv-date-control__field">
          <span className="jv-label" id="entry-date-calendar-label">
            Date
          </span>
          <Suspense fallback={<Skeleton height="16.5rem" width="100%" />}>
            <Calendar
              className="jv-date-control__calendar"
              mode="single"
              required
              captionLayout="dropdown"
              startMonth={CALENDAR_START_MONTH}
              endMonth={calendarEndMonth()}
              selected={selectedDay}
              defaultMonth={selectedDay}
              disabled={disabled || busy}
              aria-labelledby="entry-date-calendar-label"
              onSelect={(picked) =>
                picked &&
                commit({
                  year: picked.getFullYear(),
                  month: picked.getMonth() + 1,
                  day: picked.getDate(),
                })
              }
            />
          </Suspense>
        </div>

        <div className="jv-date-control__field">
          <label className="jv-label" htmlFor="entry-date-time">
            Time
          </label>
          <input
            id="entry-date-time"
            type="time"
            className="jv-date-control__time"
            value={timeValue}
            disabled={disabled || busy}
            onChange={(event) => {
              const [hour, minute] = event.target.value.split(":").map(Number);
              if (Number.isFinite(hour) && Number.isFinite(minute))
                commit({ hour, minute });
            }}
          />
        </div>

        {zoneDiffers && (
          <p className="jv-caption jv-date-control__zone">
            {timeLabel} · {loggedTimezone}
          </p>
        )}
        {error && (
          <p className="jv-caption jv-date-control__error" role="alert">
            {error}
          </p>
        )}

        <div className="jv-date-control__footer">
          <Button
            variant="ghost"
            size="sm"
            disabled={busy || disabled}
            onClick={() =>
              void onChange({
                utc: new Date().toISOString(),
                timezone: browserTimeZone(),
              })
            }
          >
            Reset to now
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
