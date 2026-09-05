import { describe, expect, it } from "vitest";
import type { PromptResponse } from "../../api/generated/types.gen";
import {
  categoryLabel,
  difficultyLabel,
  difficultyMeta,
  durationBounds,
  formatEstimatedTime,
  promptMetaParts,
} from "./promptDisplay";

const prompt = (overrides: Partial<PromptResponse> = {}): PromptResponse => ({
  id: "p1",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  text: "What are you grateful for today?",
  category: "gratitude",
  difficulty_level: 1,
  estimated_time_minutes: 5,
  is_active: true,
  usage_count: 0,
  answered_count: 0,
  ...overrides,
});

describe("categoryLabel", () => {
  it("maps known enum values to their display label", () => {
    expect(categoryLabel("gratitude")).toBe("Gratitude");
    expect(categoryLabel("self_care")).toBe("Self-care");
    expect(categoryLabel("self_discovery")).toBe("Self-discovery");
  });

  it("title-cases an unknown value and names a missing one", () => {
    expect(categoryLabel("night_owl")).toBe("Night Owl");
    expect(categoryLabel(null)).toBe("Uncategorised");
    expect(categoryLabel(undefined)).toBe("Uncategorised");
  });
});

describe("difficulty", () => {
  it("labels the known depth levels", () => {
    expect(difficultyLabel(1)).toBe("Gentle");
    expect(difficultyLabel(2)).toBe("Thoughtful");
    expect(difficultyLabel(3)).toBe("Deep");
  });

  it("falls back to a numbered label past the named range", () => {
    expect(difficultyLabel(9)).toBe("Level 9");
    expect(difficultyLabel(null)).toBe("");
  });

  it("pairs the number and label", () => {
    expect(difficultyMeta(2)).toBe("Level 2 · Thoughtful");
  });
});

describe("formatEstimatedTime", () => {
  it("formats a positive estimate and drops a missing one", () => {
    expect(formatEstimatedTime(10)).toBe("~10 min");
    expect(formatEstimatedTime(0)).toBeNull();
    expect(formatEstimatedTime(null)).toBeNull();
  });
});

describe("durationBounds", () => {
  it("maps a bucket to inclusive API bounds", () => {
    expect(durationBounds("short")).toEqual({
      min_minutes: 1,
      max_minutes: 5,
    });
    expect(durationBounds("long")).toEqual({
      min_minutes: 11,
      max_minutes: 15,
    });
    expect(durationBounds("deep")).toEqual({ min_minutes: 20 });
  });

  it("treats missing or unknown buckets as no filter", () => {
    expect(durationBounds(null)).toBeUndefined();
    expect(durationBounds("nonsense")).toBeUndefined();
  });
});

describe("promptMetaParts", () => {
  it("joins category, depth and estimate, dropping empties", () => {
    expect(promptMetaParts(prompt())).toEqual([
      "Gratitude",
      "Level 1 · Gentle",
      "~5 min",
    ]);
    expect(promptMetaParts(prompt({ estimated_time_minutes: null }))).toEqual([
      "Gratitude",
      "Level 1 · Gentle",
    ]);
  });
});
