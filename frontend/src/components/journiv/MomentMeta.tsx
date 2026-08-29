import { useQuery } from "@tanstack/react-query";
import { MapPin, CloudSun } from "lucide-react";
import type {
  MomentResponse,
  JournalResponse,
} from "../../api/generated/types.gen";
import { moodsQuery } from "../../api/query/options";
import { colorFromArgb } from "../../lib/color";
import { cx } from "../../lib/cx";
import { JournalBadge, JournalDot } from "./JournalBadge";

/**
 * Metadata budget by surface. A list row is not a detail view: it gets the
 * three highest-priority facts and nothing else. See DESIGN.md
 * "Metadata priority by surface" before adding a field here.
 */
const BUDGET = {
  row: 3,
  compact: 2,
  reader: Number.POSITIVE_INFINITY,
} as const;
/* Overflow is silently dropped in list surfaces: a "+2" badge is noise in a
   row whose job is to be scannable. The reader shows everything. */
export type MetaSurface = keyof typeof BUDGET;

/**
 * `location_json` shape is documented on the backend Moment model as
 * {name, street, locality, admin_area, country, latitude, longitude, timezone}.
 * Only these keys are read; nothing is derived from coordinates.
 */
export function locationLabel(moment: MomentResponse): string | null {
  const raw = moment.location_json as
    | Record<string, unknown>
    | null
    | undefined;
  if (!raw) return null;
  for (const key of ["name", "locality", "admin_area", "country"]) {
    const value = raw[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

/**
 * Mood `color_value` is a Flutter ARGB integer. The translation lives in
 * `src/lib/color.ts` now that person groups need it too; this alias keeps the
 * mood-specific name its callers read by.
 */
export const moodColor = colorFromArgb;

export function MomentMeta({
  moment,
  journal,
  surface,
  className,
}: {
  moment: MomentResponse;
  journal?: JournalResponse;
  surface: MetaSurface;
  className?: string;
}) {
  const moods = useQuery({
    ...moodsQuery(),
    enabled: Boolean(moment.primary_mood_id),
  });
  const mood = moods.data?.find((item) => item.id === moment.primary_mood_id);
  const location = locationLabel(moment);
  const weather = moment.weather_summary?.trim() || null;

  // Priority order. Only facts the API actually returned may appear here.
  const items: Array<{ key: string; node: React.ReactNode }> = [];
  if (journal)
    items.push({ key: "journal", node: <JournalBadge journal={journal} /> });
  if (location)
    items.push({
      key: "location",
      node: (
        <span className="jv-meta-item">
          <MapPin aria-hidden="true" size={13} />
          <span className="jv-truncate">{location}</span>
        </span>
      ),
    });
  if (mood)
    items.push({
      key: "mood",
      node: (
        <span className="jv-meta-item">
          <span
            className="jv-mood-dot"
            style={
              {
                "--mood-accent": moodColor(mood.color_value),
              } as React.CSSProperties
            }
            aria-hidden="true"
          />
          {mood.name}
        </span>
      ),
    });
  if (weather)
    items.push({
      key: "weather",
      node: (
        <span className="jv-meta-item">
          <CloudSun aria-hidden="true" size={13} />
          {weather}
        </span>
      ),
    });

  const limit = BUDGET[surface];
  const shown = items.slice(0, limit);
  if (!shown.length) return null;

  return (
    <div className={cx("jv-meta", "jv-meta-row", className)}>
      {shown.map((item) => (
        <span key={item.key} className="jv-meta-cell">
          {item.node}
        </span>
      ))}
    </div>
  );
}

export { JournalDot };
