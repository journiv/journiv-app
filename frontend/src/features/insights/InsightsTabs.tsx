import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../components/ui/tabs";
import { JournalsTab } from "./JournalsTab";
import { MoodTab } from "./MoodTab";
import { OverviewTab } from "./OverviewTab";
import { PeriodControl, type InsightsPeriod } from "./PeriodControl";

export type InsightsTab = "overview" | "mood" | "journals";

/**
 * Overview / Mood / Journals. The active panel is the only one mounted (Base UI
 * `Tabs.Panel` unmounts inactive panels), so each tab's queries fire only when
 * it is shown. `period` is shared and lives in the URL, so switching tabs keeps
 * it (docs/features/insights.md).
 *
 * The tab strip and the Trend-period control sit on one row — tabs left, the
 * picker right — so they read as one band of controls for the section below.
 * Journals is all-time, so it shows a static "All time" note in that slot
 * instead of the picker.
 */
export function InsightsTabs({
  tab,
  period,
  onTabChange,
  onPeriodChange,
  moodStart,
  moodEnd,
}: {
  tab: InsightsTab;
  period: InsightsPeriod;
  onTabChange: (tab: InsightsTab) => void;
  onPeriodChange: (period: InsightsPeriod) => void;
  moodStart: string;
  moodEnd: string;
}) {
  return (
    <Tabs
      value={tab}
      onValueChange={(value) => onTabChange(value as InsightsTab)}
    >
      <div className="jv-insights__tabbar">
        <TabsList aria-label="Insights sections">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="mood">Mood</TabsTrigger>
          <TabsTrigger value="journals">Journals</TabsTrigger>
        </TabsList>
        {tab === "journals" ? (
          <p className="jv-caption jv-insights__all-time">All time</p>
        ) : (
          <PeriodControl value={period} onChange={onPeriodChange} />
        )}
      </div>

      <TabsContent value="overview">
        <OverviewTab period={period} />
      </TabsContent>
      <TabsContent value="mood">
        <MoodTab start={moodStart} end={moodEnd} />
      </TabsContent>
      <TabsContent value="journals">
        <JournalsTab />
      </TabsContent>
    </Tabs>
  );
}
