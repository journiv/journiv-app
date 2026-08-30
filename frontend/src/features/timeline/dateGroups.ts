import type { MomentResponse } from "../../api/generated/types.gen";
import { dayGroupLabel } from "../../lib/datetime";

export type DayGroup = {
  key: string;
  label: string;
  moments: MomentResponse[];
};

/**
 * Group by the Moment's own local calendar day (`logged_date_tz`), never by the
 * viewer's timezone. A trip across timezones must not re-shuffle history.
 */
export function groupMomentsByDay(
  moments: MomentResponse[],
  now = new Date(),
): DayGroup[] {
  const groups: DayGroup[] = [];
  let current: DayGroup | undefined;
  for (const moment of moments) {
    const key = moment.logged_date_tz;
    if (!current || current.key !== key) {
      current = {
        key,
        label: dayGroupLabel(
          key,
          moment.logged_timezone,
          moment.logged_at_utc,
          now,
        ),
        moments: [],
      };
      groups.push(current);
    }
    current.moments.push(moment);
  }
  return groups;
}
