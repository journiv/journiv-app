import { useNavigate, useSearch } from "@tanstack/react-router";
import { useMemo } from "react";
import {
  browserTimeZone,
  shiftIsoDate,
  todayInTimezone,
} from "../../lib/datetime";
import { LibraryWorkspace } from "../library/LibraryWorkspace";
import { InsightsTabs, type InsightsTab } from "./InsightsTabs";
import type { InsightsPeriod } from "./PeriodControl";
import { SummaryStrip } from "./SummaryStrip";
import "./insights.css";

/**
 * Insights — a read-only analysis workspace (docs/features/insights.md). It reuses
 * the Library workspace shell (a generic wide span-2 canvas with a compact
 * PageBar and one scroll owner), then lays out a non-sticky summary strip and
 * the Overview / Mood / Journals tabs. `tab` and `period` live in the URL so a
 * tab switch keeps the period and any link is shareable. Every analytics
 * endpoint here is free (not Plus-gated).
 */
export function InsightsPage() {
  // The `/insights` route validator guarantees both are present and valid.
  const { tab, period } = useSearch({ strict: false }) as {
    tab: InsightsTab;
    period: InsightsPeriod;
  };
  const navigate = useNavigate({ from: "/insights" });

  const setTab = (next: InsightsTab) =>
    navigate({ search: (prev) => ({ ...prev, tab: next }) });
  const setPeriod = (next: InsightsPeriod) =>
    navigate({ search: (prev) => ({ ...prev, period: next }) });

  const { moodStart, moodEnd } = useMemo(() => {
    const end = todayInTimezone(browserTimeZone());
    return { moodStart: shiftIsoDate(end, -(period - 1)), moodEnd: end };
  }, [period]);

  return (
    <LibraryWorkspace
      title="Insights"
      intro="How your journaling is going — writing rhythm, streaks and mood over time."
    >
      <div className="jv-insights">
        <SummaryStrip />
        <InsightsTabs
          tab={tab}
          period={period}
          onTabChange={setTab}
          onPeriodChange={setPeriod}
          moodStart={moodStart}
          moodEnd={moodEnd}
        />
      </div>
    </LibraryWorkspace>
  );
}
