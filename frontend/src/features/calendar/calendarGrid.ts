/**
 * Pure month-grid maths for the calendar. All dates are handled as `YYYY-MM-DD`
 * strings at UTC noon so daylight-saving shifts can never move a cell to the
 * wrong day. The week starts on Sunday, matching the reference apps; a
 * first-day-of-week preference is a later refinement.
 */

const MS_DAY = 86_400_000;

/** `YYYY-MM` for the current month in the given timezone. */
export function currentMonth(timezone: string, now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
  }).format(now);
}

export function isMonthKey(value: string): boolean {
  return /^\d{4}-\d{2}$/.test(value);
}

function noon(iso: string): Date {
  return new Date(`${iso}T12:00:00Z`);
}

function isoOf(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** Shift a `YYYY-MM` key by whole months. */
export function shiftMonth(month: string, delta: number): string {
  const year = Number(month.slice(0, 4));
  const monthIndex = Number(month.slice(5, 7)) - 1 + delta;
  const shifted = new Date(Date.UTC(year, monthIndex, 1, 12));
  return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, "0")}`;
}

/** "August 2026" for a `YYYY-MM` key. */
export function monthLabel(month: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(noon(`${month}-01`));
}

/** Long month names in the active locale, index 0 = January. */
export const MONTH_NAMES: string[] = Array.from({ length: 12 }, (_, i) =>
  new Intl.DateTimeFormat(undefined, { month: "long", timeZone: "UTC" }).format(
    noon(`2021-${String(i + 1).padStart(2, "0")}-01`),
  ),
);

/** `{ year, monthIndex }` (0-based month) for a `YYYY-MM` key. */
export function monthParts(month: string): {
  year: number;
  monthIndex: number;
} {
  return {
    year: Number(month.slice(0, 4)),
    monthIndex: Number(month.slice(5, 7)) - 1,
  };
}

/** A `YYYY-MM` key from a year and a 0-based month index; overflow normalises. */
export function monthKeyOf(year: number, monthIndex: number): string {
  const d = new Date(Date.UTC(year, monthIndex, 1, 12));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

/**
 * Year options for the picker, ascending — matching `EntryDateControl`'s
 * caption. Spans 1970 → next year and always widens to include `selected` so a
 * URL-driven out-of-range month still lists its own year.
 */
export function yearOptions(selected: number, now = new Date()): number[] {
  const min = Math.min(1970, selected);
  const max = Math.max(now.getUTCFullYear() + 1, selected);
  const years: number[] = [];
  for (let y = min; y <= max; y += 1) years.push(y);
  return years;
}

export type CalendarCell = { iso: string; day: number; inMonth: boolean };

/**
 * Six weeks of cells (always 42) covering `month`, padded with the tail of the
 * previous month and the head of the next so every row is full.
 */
export function buildMonthGrid(month: string): CalendarCell[] {
  const first = noon(`${month}-01`);
  const gridStart = new Date(first.getTime() - first.getUTCDay() * MS_DAY);
  const cells: CalendarCell[] = [];
  for (let i = 0; i < 42; i += 1) {
    const date = new Date(gridStart.getTime() + i * MS_DAY);
    cells.push({
      iso: isoOf(date),
      day: date.getUTCDate(),
      inMonth: date.toISOString().slice(0, 7) === month,
    });
  }
  return cells;
}

/** First and last ISO day the grid displays — the calendar query's range. */
export function gridRange(month: string): { start: string; end: string } {
  const cells = buildMonthGrid(month);
  return { start: cells[0].iso, end: cells[cells.length - 1].iso };
}

export const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** "Friday, 8 August 2026" for a `YYYY-MM-DD` day. */
export function formatDayHeading(iso: string): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(noon(iso));
}
