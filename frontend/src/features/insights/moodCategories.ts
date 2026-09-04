/**
 * Mood insight charts group logs by the backend's three mood *categories*, not
 * by a mood's identity colour (mood colours are identity, not valence —
 * docs/features/library.md). Each category maps to an existing semantic token so
 * no new global palette role is introduced: positive → the documented `success`
 * role, neutral → `muted-foreground`, negative → the `destructive` danger role.
 * One source of truth for the trend area, the distribution bars and any legend.
 */
export type MoodCategory = "positive" | "neutral" | "negative";

export const MOOD_CATEGORY_ORDER: readonly MoodCategory[] = [
  "positive",
  "neutral",
  "negative",
];

export const MOOD_CATEGORY_META: Record<
  MoodCategory,
  { label: string; cssVar: string }
> = {
  positive: { label: "Positive", cssVar: "var(--success)" },
  neutral: { label: "Neutral", cssVar: "var(--muted-foreground)" },
  negative: { label: "Negative", cssVar: "var(--destructive)" },
};

/** A backend category string that is not one of the three known ones still gets
 *  a readable label and the neutral colour rather than breaking the chart. */
export function moodCategoryMeta(category: string): {
  label: string;
  cssVar: string;
} {
  return (
    MOOD_CATEGORY_META[category as MoodCategory] ?? {
      label: category ? category[0].toUpperCase() + category.slice(1) : "Other",
      cssVar: "var(--muted-foreground)",
    }
  );
}
