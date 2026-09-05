import { useMutation, useQuery } from "@tanstack/react-query";
import { SearchX, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../../api/client/api";
import { isNotFound } from "../../api/client/errors";
import type { PromptResponse } from "../../api/generated/types.gen";
import { dailyPromptQuery } from "../../api/query/options";
import { StatusView } from "../../components/journiv/StatusView";
import { Button } from "../../components/ui/button";
import { Skeleton } from "../../components/ui/skeleton";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../components/ui/tabs";
import { cx } from "../../lib/cx";
import { DailyPromptCard } from "./DailyPromptCard";
import { PromptCard } from "./PromptCard";
import { PromptFilters } from "./PromptFilters";
import { PromptInsightsTab } from "./PromptInsightsTab";
import { PROMPT_CATEGORIES } from "./promptDisplay";
import { usePromptBrowser } from "./usePromptBrowser";
import "./prompts.css";

export type PromptBrowserVariant = "page" | "overlay";
export type PromptBrowserTab = "discover" | "insights";

/**
 * The shared prompt browser (docs/features/prompts.md): the daily hero, the
 * filter bar, the results grid and server-backed pagination. Both the
 * `/library/prompts` page and the in-editor `PromptPickerDialog` render this —
 * they differ only in `variant` (grid density) and the select action's label
 * and effect, passed in as props.
 */
export function PromptBrowser({
  variant,
  selectActionLabel,
  dailyActionLabel,
  onSelectPrompt,
  tab: controlledTab,
  onTabChange,
}: {
  variant: PromptBrowserVariant;
  /** Row action label — "Write" on the page, "Insert" in the editor. */
  selectActionLabel: string;
  /** Daily hero primary label — "Write with this prompt" / "Insert prompt". */
  dailyActionLabel: string;
  onSelectPrompt: (prompt: PromptResponse) => void;
  /** The library page keeps this in the URL; the editor picker owns it locally. */
  tab?: PromptBrowserTab;
  onTabChange?: (tab: PromptBrowserTab) => void;
}) {
  const [uncontrolledTab, setUncontrolledTab] =
    useState<PromptBrowserTab>("discover");
  const tab = controlledTab ?? uncontrolledTab;
  const setTab = (next: PromptBrowserTab) => {
    if (controlledTab === undefined) setUncontrolledTab(next);
    onTabChange?.(next);
  };

  return (
    <div
      className={cx(
        "jv-prompts",
        variant === "overlay" && "jv-prompts--overlay",
      )}
    >
      <Tabs
        value={tab}
        onValueChange={(value) => setTab(value as PromptBrowserTab)}
      >
        <div className="jv-prompts__tabbar">
          <TabsList aria-label="Prompt sections">
            <TabsTrigger value="discover">Discover</TabsTrigger>
            <TabsTrigger value="insights">Insights</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="discover">
          <PromptDiscover
            selectActionLabel={selectActionLabel}
            dailyActionLabel={dailyActionLabel}
            onSelectPrompt={onSelectPrompt}
          />
        </TabsContent>
        <TabsContent value="insights">
          <PromptInsightsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function PromptDiscover({
  selectActionLabel,
  dailyActionLabel,
  onSelectPrompt,
}: {
  selectActionLabel: string;
  dailyActionLabel: string;
  onSelectPrompt: (prompt: PromptResponse) => void;
}) {
  const browser = usePromptBrowser();
  const daily = useQuery(dailyPromptQuery());
  const [shuffled, setShuffled] = useState<PromptResponse | null>(null);

  const shuffle = useMutation({
    mutationFn: () => api.randomPrompt(),
    onSuccess: (prompt) => setShuffled(prompt),
  });
  const shuffleUnavailable = shuffle.isError && isNotFound(shuffle.error);

  const categories = useMemo(
    () =>
      PROMPT_CATEGORIES.map((entry) => ({
        ...entry,
        count: browser.categoryCounts.get(entry.value) ?? 0,
      })).filter((entry) => entry.count > 0),
    [browser.categoryCounts],
  );

  const difficulties = useMemo(() => {
    const seen = new Set<number>();
    for (const prompt of browser.prompts) {
      if (typeof prompt.difficulty_level === "number")
        seen.add(prompt.difficulty_level);
    }
    // The visible page can miss a supported level, so the filter always offers
    // the backend's complete 1–5 range rather than only the seeded values.
    for (const level of [1, 2, 3, 4, 5]) seen.add(level);
    return [...seen].sort((a, b) => a - b);
  }, [browser.prompts]);

  if (browser.isLoading) {
    return (
      <div className="jv-prompts__discover" aria-busy="true">
        <div
          role="status"
          aria-label="Loading prompts"
          className="jv-prompts__loading"
        >
          <Skeleton height="9rem" width="100%" />
          <Skeleton height="2.25rem" width="100%" />
          <div className="jv-prompts__grid">
            {["a", "b", "c", "d", "e", "f"].map((key) => (
              <Skeleton key={key} height="8rem" width="100%" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (browser.isError) {
    return (
      <div className="jv-prompts__discover">
        <StatusView
          role="alert"
          tone="danger"
          icon={<TriangleAlert size={20} />}
          title="Prompts could not be loaded"
          description="Check your connection and try again."
          action={
            <Button variant="secondary" onClick={() => browser.refetch()}>
              Try again
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="jv-prompts__discover">
      {daily.isLoading ? (
        <Skeleton height="9rem" width="100%" />
      ) : daily.isError ? null : (
        <DailyPromptCard
          prompt={daily.data ?? null}
          shuffledPrompt={shuffled}
          actionLabel={dailyActionLabel}
          onSelect={onSelectPrompt}
          onShuffle={() => shuffle.mutate()}
          shuffling={shuffle.isPending}
          shuffleUnavailable={shuffleUnavailable}
        />
      )}

      <PromptFilters
        filters={browser.filters}
        onChange={browser.setFilter}
        categories={categories}
        allCount={browser.allCount}
        difficulties={difficulties}
      />

      {browser.prompts.length === 0 && !browser.hasNextPage ? (
        <StatusView
          icon={<SearchX size={20} />}
          title="No prompts match those filters"
          description="Try a broader search or clear a filter."
          action={
            browser.hasActiveFilters ? (
              <Button variant="secondary" onClick={browser.resetFilters}>
                Clear filters
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          {browser.prompts.length > 0 && (
            <ul className="jv-prompts__grid" aria-label="Prompts">
              {browser.prompts.map((prompt) => (
                <li key={prompt.id}>
                  <PromptCard
                    prompt={prompt}
                    actionLabel={selectActionLabel}
                    onSelect={onSelectPrompt}
                    usageCount={prompt.answered_count}
                  />
                </li>
              ))}
            </ul>
          )}

          <div className="jv-prompts__pager">
            <p className="jv-caption">
              {browser.prompts.length}{" "}
              {browser.prompts.length === browser.totalCount ? "" : "of "}
              {browser.prompts.length === browser.totalCount
                ? ""
                : `${browser.totalCount} `}
              {browser.totalCount === 1 ? "prompt" : "prompts"}
            </p>
            {browser.hasNextPage && (
              <Button
                variant="secondary"
                size="sm"
                disabled={browser.isFetchingNextPage}
                onClick={browser.fetchNextPage}
              >
                {browser.isFetchingNextPage
                  ? "Loading prompts…"
                  : "Load more prompts"}
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
