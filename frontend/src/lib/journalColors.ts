import type { JournalColor } from "../api/generated/types.gen";

/**
 * The journal colour palette. These are **API contract values**, not design
 * tokens: they mirror the backend `JournalColor` enum
 * (journiv-backend/app/models/enums.py) exactly, so the picker can only offer
 * what `POST /journals` will accept. Like a mood's colour, a journal's colour
 * is API-provided data that `JournalDot` passes straight to `--journal-accent`;
 * it never enters a stylesheet. See DESIGN.md §3.
 */
export const JOURNAL_COLORS: ReadonlyArray<{
  value: JournalColor;
  label: string;
}> = [
  { value: "#EF4444", label: "Red" },
  { value: "#F97316", label: "Orange" },
  { value: "#F59E0B", label: "Amber" },
  { value: "#EAB308", label: "Yellow" },
  { value: "#84CC16", label: "Lime" },
  { value: "#22C55E", label: "Green" },
  { value: "#10B981", label: "Emerald" },
  { value: "#14B8A6", label: "Teal" },
  { value: "#06B6D4", label: "Cyan" },
  { value: "#0EA5E9", label: "Sky blue" },
  { value: "#3B82F6", label: "Blue" },
  { value: "#6366F1", label: "Indigo" },
  { value: "#8B5CF6", label: "Violet" },
  { value: "#A855F7", label: "Purple" },
  { value: "#D946EF", label: "Fuchsia" },
  { value: "#EC4899", label: "Pink" },
  { value: "#F43F5E", label: "Rose" },
  { value: "#64748B", label: "Slate" },
  { value: "#6B7280", label: "Gray" },
  { value: "#71717A", label: "Zinc" },
  { value: "#737373", label: "Neutral" },
  { value: "#78716C", label: "Stone" },
];

const LABELS = new Map<string, string>(
  JOURNAL_COLORS.map((c) => [c.value, c.label]),
);

export function journalColorLabel(value?: string | null): string | null {
  return value ? (LABELS.get(value) ?? null) : null;
}
