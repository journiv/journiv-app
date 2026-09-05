import { useId } from "react";
import { NativeSelect } from "../../components/ui/native-select";
import { SearchInput } from "../../components/ui/search-input";
import { ToggleGroup, ToggleGroupItem } from "../../components/ui/toggle-group";
import {
  DIFFICULTY_LABELS,
  DURATION_BUCKETS,
  difficultyLabel,
} from "./promptDisplay";
import type { PromptFilterState } from "./usePromptBrowser";

const ALL = "all";

export type CategoryOption = { value: string; label: string; count: number };

/**
 * The prompt browser's filter bar (docs/features/prompts.md): free-text search,
 * a level select, a duration select, and a category chip row with counts.
 *
 * Every filter is sent to `GET /prompts/`, so search and duration apply across
 * every offset page instead of only the results already loaded in the browser.
 */
export function PromptFilters({
  filters,
  onChange,
  categories,
  allCount,
  difficulties,
}: {
  filters: PromptFilterState;
  onChange: (patch: Partial<PromptFilterState>) => void;
  categories: CategoryOption[];
  allCount: number;
  /** Difficulty levels present in the library, ascending. */
  difficulties: number[];
}) {
  const levelId = useId();
  const durationId = useId();

  return (
    <div className="jv-prompt-filters">
      <div className="jv-prompt-filters__row">
        <SearchInput
          label="Search prompts"
          placeholder="Search prompts, topics, feelings…"
          className="jv-prompt-filters__search"
          value={filters.search}
          onChange={(event) => onChange({ search: event.target.value })}
          onClear={() => onChange({ search: "" })}
        />
        <div className="jv-prompt-filters__selects">
          <label className="jv-prompt-filters__select" htmlFor={levelId}>
            <span className="sr-only">Level</span>
            <NativeSelect
              id={levelId}
              size="sm"
              value={
                filters.difficulty == null ? ALL : String(filters.difficulty)
              }
              onChange={(event) =>
                onChange({
                  difficulty:
                    event.target.value === ALL
                      ? null
                      : Number(event.target.value),
                })
              }
            >
              <option value={ALL}>All levels</option>
              {difficulties.map((level) => (
                <option key={level} value={String(level)}>
                  Level {level} ·{" "}
                  {DIFFICULTY_LABELS[level] ?? difficultyLabel(level)}
                </option>
              ))}
            </NativeSelect>
          </label>
          <label className="jv-prompt-filters__select" htmlFor={durationId}>
            <span className="sr-only">Duration</span>
            <NativeSelect
              id={durationId}
              size="sm"
              value={filters.duration ?? ALL}
              onChange={(event) =>
                onChange({
                  duration:
                    event.target.value === ALL ? null : event.target.value,
                })
              }
            >
              <option value={ALL}>All durations</option>
              {DURATION_BUCKETS.map((bucket) => (
                <option key={bucket.value} value={bucket.value}>
                  {bucket.label}
                </option>
              ))}
            </NativeSelect>
          </label>
        </div>
      </div>

      {categories.length > 0 && (
        <ToggleGroup
          className="jv-prompt-filters__categories"
          variant="outline"
          size="sm"
          aria-label="Filter by category"
          value={[filters.category ?? ALL]}
          onValueChange={(values) => {
            // ToggleGroup can briefly retain the All value while it selects a
            // category. Prefer the most recently selected concrete category.
            const category = [...values]
              .reverse()
              .find((value) => value !== ALL);
            onChange({ category: category ?? null });
          }}
        >
          <ToggleGroupItem value={ALL}>
            All <span className="jv-prompt-filters__count">{allCount}</span>
          </ToggleGroupItem>
          {categories.map((category) => (
            <ToggleGroupItem key={category.value} value={category.value}>
              {category.label}{" "}
              <span className="jv-prompt-filters__count">{category.count}</span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      )}
    </div>
  );
}
