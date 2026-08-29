/**
 * All Moment dates are rendered in the timezone the Moment happened in, not the
 * viewer's. `logged_date_tz` is the authoritative local calendar day and is what
 * the Timeline groups by. See DESIGN.md "Time and grouping".
 */
import { fromZonedTime, toZonedTime } from "date-fns-tz";

const viewerTimezone = () =>
  Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

/** The viewer's own IANA timezone (e.g. `Europe/Vienna`). */
export function browserTimeZone() {
  return viewerTimezone();
}

/** A wall-clock date/time with no zone of its own. `month` is 1-based. */
export type WallTimeParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
};

/**
 * The wall-clock a UTC instant shows as in `timeZone`. Use this to seed a date
 * picker so the highlighted day is the day *in the entry's own zone*, not the
 * viewer's.
 */
export function wallTimePartsInZone(
  utcIso: string,
  timeZone: string,
): WallTimeParts {
  const zoned = toZonedTime(utcIso, timeZone);
  return {
    year: zoned.getFullYear(),
    month: zoned.getMonth() + 1,
    day: zoned.getDate(),
    hour: zoned.getHours(),
    minute: zoned.getMinutes(),
  };
}

/**
 * The UTC instant (ISO string) for a wall-clock time interpreted in `timeZone`.
 * DST-correct via `date-fns-tz`: a nonexistent spring-forward time is shifted
 * past the gap; an ambiguous fall-back time resolves to the earlier offset.
 * `react-day-picker` hands back a `Date` at browser-local midnight — take only
 * its y/m/d, combine with the time field, and pass the parts here; never
 * persist that `Date`'s own `toISOString()`.
 */
export function zonedWallTimeToUtcIso(
  { year, month, day, hour, minute }: WallTimeParts,
  timeZone: string,
): string {
  const floating = new Date(year, month - 1, day, hour, minute, 0, 0);
  return fromZonedTime(floating, timeZone).toISOString();
}

function format(
  value: string,
  timezone: string,
  options: Intl.DateTimeFormatOptions,
) {
  return new Intl.DateTimeFormat(undefined, {
    ...options,
    timeZone: timezone,
  }).format(new Date(value));
}

export function formatTimeOfDay(utc: string, timezone: string) {
  return format(utc, timezone, { hour: "numeric", minute: "2-digit" });
}

export function formatDayLong(utc: string, timezone: string) {
  return format(utc, timezone, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function formatDayMedium(utc: string, timezone: string) {
  return format(utc, timezone, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

/**
 * A short absolute date ("17 August 2026") in the viewer's timezone. For
 * journal-level aggregates such as `last_entry_at`, which — unlike a Moment —
 * have no timezone of their own, so the ambiguity rules in §12 do not apply.
 */
export function formatDateMedium(utc: string) {
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: viewerTimezone(),
  }).format(new Date(utc));
}

/** Today's calendar date (YYYY-MM-DD) in the given timezone. */
export function todayInTimezone(timezone: string, now = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

export function shiftIsoDate(isoDate: string, days: number) {
  const date = new Date(`${isoDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

/**
 * Heading for a day group.
 *
 * "Today" / "Yesterday" are only used when the Moment was logged in the
 * viewer's own timezone. Across timezones those words are ambiguous, so the
 * explicit date is shown instead. This is deliberate — do not "simplify" it.
 */
export function dayGroupLabel(
  loggedDateTz: string,
  loggedTimezone: string,
  loggedAtUtc: string,
  now = new Date(),
) {
  const viewer = viewerTimezone();
  if (loggedTimezone === viewer) {
    const today = todayInTimezone(viewer, now);
    if (loggedDateTz === today) return "Today";
    if (loggedDateTz === shiftIsoDate(today, -1)) return "Yesterday";
  }
  const thisYear = new Date(now).getUTCFullYear();
  const momentYear = Number(loggedDateTz.slice(0, 4));
  return momentYear === thisYear
    ? formatDayMedium(loggedAtUtc, loggedTimezone)
    : formatDayLong(loggedAtUtc, loggedTimezone);
}
