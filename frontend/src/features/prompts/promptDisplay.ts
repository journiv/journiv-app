import type { PromptResponse } from "../../api/generated/types.gen";

/**
 * Display helpers for journaling prompts (docs/features/prompts.md).
 *
 * The backend gives a prompt only a raw `category` string (one of the
 * `PromptCategory` enum values), an integer `difficulty_level` (1–5) and an
 * optional `estimated_time_minutes`. None of those carry a human label, an
 * icon, or a colour, and DESIGN.md reserves the palette for real data roles —
 * so every label here is frontend presentation, kept in one place rather than
 * scattered through the components.
 */

/** Known `PromptCategory` values, in the backend's grouping order, each with a
 *  display label. An unknown value still renders via `categoryLabel`'s
 *  title-case fallback. */
export const PROMPT_CATEGORIES: ReadonlyArray<{
  value: string;
  label: string;
}> = [
  { value: "gratitude", label: "Gratitude" },
  { value: "reflection", label: "Reflection" },
  { value: "emotions", label: "Emotions" },
  { value: "mindfulness", label: "Mindfulness" },
  { value: "self_discovery", label: "Self-discovery" },
  { value: "goals", label: "Goals" },
  { value: "productivity", label: "Productivity" },
  { value: "growth", label: "Growth" },
  { value: "relationships", label: "Relationships" },
  { value: "family", label: "Family" },
  { value: "love", label: "Love" },
  { value: "social", label: "Social" },
  { value: "creativity", label: "Creativity" },
  { value: "dreams", label: "Dreams" },
  { value: "memories", label: "Memories" },
  { value: "self_care", label: "Self-care" },
  { value: "health", label: "Health" },
  { value: "spirituality", label: "Spirituality" },
  { value: "general", label: "General" },
];

const CATEGORY_LABELS = new Map(
  PROMPT_CATEGORIES.map((entry) => [entry.value, entry.label]),
);

/** Human label for a prompt category. Unknown or missing values fall back to a
 *  title-cased form of the raw string ("uncategorised" when absent). */
export function categoryLabel(value: string | null | undefined): string {
  if (!value) return "Uncategorised";
  const known = CATEGORY_LABELS.get(value);
  if (known) return known;
  return value
    .split(/[_\s]+/u)
    .filter(Boolean)
    .map((word) => word[0]?.toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * Depth labels for `difficulty_level`. The backend only guarantees 1–5 and
 * ships no labels; the seed library today uses 1–3. These names read as an
 * invitation, not a warning — a "deep" prompt is not a harder one to get
 * wrong, just one that asks for more.
 */
export const DIFFICULTY_LABELS: Record<number, string> = {
  1: "Gentle",
  2: "Thoughtful",
  3: "Deep",
  4: "Searching",
  5: "Profound",
};

export function difficultyLabel(level: number | null | undefined): string {
  if (level == null) return "";
  return DIFFICULTY_LABELS[level] ?? `Level ${level}`;
}

/** "Level 2 · Thoughtful" — the paired form shown on cards. */
export function difficultyMeta(level: number | null | undefined): string {
  if (level == null) return "";
  const label = difficultyLabel(level);
  return label ? `Level ${level} · ${label}` : `Level ${level}`;
}

export function formatEstimatedTime(
  minutes: number | null | undefined,
): string | null {
  if (!minutes || minutes <= 0) return null;
  return `~${minutes} min`;
}

/**
 * Duration filter buckets. Each maps directly to the list endpoint's inclusive
 * estimated-minute bounds, so the whole matching result can be paginated.
 */
export const DURATION_BUCKETS: ReadonlyArray<{
  value: string;
  label: string;
  min_minutes: number;
  max_minutes?: number;
}> = [
  {
    value: "short",
    label: "5 min or less",
    min_minutes: 1,
    max_minutes: 5,
  },
  {
    value: "medium",
    label: "About 10 min",
    min_minutes: 6,
    max_minutes: 10,
  },
  {
    value: "long",
    label: "About 15 min",
    min_minutes: 11,
    max_minutes: 15,
  },
  {
    value: "deep",
    label: "20 min or more",
    min_minutes: 20,
  },
];

const DURATION_BY_VALUE = new Map(
  DURATION_BUCKETS.map((bucket) => [bucket.value, bucket]),
);

/** API bounds for the named duration bucket, if it is recognised. */
export function durationBounds(
  bucketValue: string | null,
): { min_minutes: number; max_minutes?: number } | undefined {
  if (!bucketValue) return undefined;
  const bucket = DURATION_BY_VALUE.get(bucketValue);
  if (!bucket) return undefined;
  return {
    min_minutes: bucket.min_minutes,
    ...(bucket.max_minutes !== undefined
      ? { max_minutes: bucket.max_minutes }
      : {}),
  };
}

/** The meta pieces shown under a prompt: category, depth, estimate. Empty
 *  segments are dropped so the separator never floats. */
export function promptMetaParts(prompt: PromptResponse): string[] {
  return [
    categoryLabel(prompt.category),
    difficultyMeta(prompt.difficulty_level),
    formatEstimatedTime(prompt.estimated_time_minutes) ?? "",
  ].filter(Boolean);
}
