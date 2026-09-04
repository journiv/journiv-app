import { useId } from "react";
import { NativeSelect } from "../../components/ui/native-select";

export type InsightsPeriod = 7 | 30 | 90 | 365;

const OPTIONS: { value: InsightsPeriod; label: string }[] = [
  { value: 7, label: "7 days" },
  { value: 30, label: "30 days" },
  { value: 90, label: "90 days" },
  { value: 365, label: "1 year" },
];

/**
 * The one shared "Trend period" for Insights. It scopes only the range-based
 * charts (the writing trend, the mood window) — never the summary strip, the
 * streaks or the productivity figures, which the API fixes to all-time /
 * this-month. It renders inside the Overview and Mood tab panels so it cannot
 * imply the summary tiles above are period-scoped (docs/features/insights.md).
 */
export function PeriodControl({
  value,
  onChange,
}: {
  value: InsightsPeriod;
  onChange: (value: InsightsPeriod) => void;
}) {
  const id = useId();
  return (
    <div className="jv-insights__toolbar">
      <label className="jv-label jv-insights__toolbar-label" htmlFor={id}>
        Trend period
      </label>
      <NativeSelect
        id={id}
        size="sm"
        className="w-auto"
        value={value}
        onChange={(event) =>
          onChange(Number(event.target.value) as InsightsPeriod)
        }
      >
        {OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}
