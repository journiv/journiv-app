import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { Sparkles, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { ApiError } from "../../api/client/errors";
import { api } from "../../api/client/api";
import { queryKeys } from "../../api/query/keys";
import {
  tagDetailAnalyticsQuery,
  tagMomentsQuery,
  tagsQuery,
} from "../../api/query/options";
import { StatusView } from "../../components/journiv/StatusView";
import { Button, buttonVariants } from "../../components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { AppAdaptiveMenu } from "../../components/journiv/AppAdaptiveMenu";
import { AppConfirmDialog } from "../../components/journiv/AppConfirmDialog";
import { viewMomentsAction } from "./viewMomentsAction";
import { Skeleton } from "../../components/ui/skeleton";
import { cn } from "../../lib/utils";
import { formatDateMedium } from "../../lib/datetime";
import { usePlusCapability } from "../plus/usePlusCapability";
import { LibraryDetailView } from "./LibraryDetailView";
import { MergeTagDialog, TagNameDialog } from "./TagsPage";
import { Sparkline } from "./tagCharts";
import "./library.css";
import "./tags.css";
import { NativeSelect } from "../../components/ui/native-select";

const RANGES: { days: number; label: string }[] = [
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 365, label: "1 year" },
  { days: 3650, label: "All time" },
];

const TREND_LABEL: Record<string, string> = {
  increasing: "Trending up",
  decreasing: "Trending down",
  stable: "Steady",
  insufficient_data: "Not enough data",
};

function momentCount(n: number) {
  return `${n} ${n === 1 ? "moment" : "moments"}`;
}

function isPlusLocked(error: unknown): boolean {
  return (
    error instanceof ApiError && (error.status === 403 || error.status === 503)
  );
}

/** The moment's own calendar day, formatted without shifting it into the
 *  viewer's zone (DESIGN.md §12). */
function loggedDay(dateTz: string): string {
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${dateTz}T00:00:00Z`));
}

const TAGS_LINK = <Link to="/library/tags" search={{ q: "" }} />;

export function TagDetailPage() {
  const { tagId } = useParams({ strict: false });
  const navigate = useNavigate();
  const qc = useQueryClient();
  const plus = usePlusCapability();

  const tagsResult = useQuery(tagsQuery());
  const tag = (tagsResult.data ?? []).find((t) => t.id === tagId);

  const [days, setDays] = useState(365);
  const [renaming, setRenaming] = useState(false);
  const [merging, setMerging] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const analytics = useQuery({
    ...tagDetailAnalyticsQuery(tagId ?? "", days),
    enabled: Boolean(tagId) && plus.isSupporter,
  });
  const moments = useQuery({
    ...tagMomentsQuery(tagId ?? ""),
    enabled: Boolean(tagId),
  });

  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: queryKeys.tags }),
      qc.invalidateQueries({ queryKey: queryKeys.tagAnalytics }),
    ]);

  const rename = useMutation({
    mutationFn: (name: string) => api.updateTag(tagId ?? "", { name }),
    onSuccess: async () => {
      setRenaming(false);
      await refresh();
    },
  });
  const merge = useMutation({
    mutationFn: (target: string) => api.mergeTags(tagId ?? "", target),
    onSuccess: () => {
      // Leave the (now-gone) detail route first, then refresh the list behind it.
      navigate({ to: "/library/tags", search: { q: "" } });
      void refresh();
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteTag(tagId ?? ""),
    onSuccess: () => {
      navigate({ to: "/library/tags", search: { q: "" } });
      void refresh();
    },
  });

  if (tagsResult.isLoading) {
    return (
      <LibraryDetailView
        parentLabel="Tags"
        parentLink={TAGS_LINK}
        current="Tag"
      >
        <Skeleton height="1.75rem" width="12rem" />
        <Skeleton height="1rem" width="16rem" />
      </LibraryDetailView>
    );
  }

  if (!tag) {
    return (
      <LibraryDetailView
        parentLabel="Tags"
        parentLink={TAGS_LINK}
        current="Tag"
      >
        <StatusView
          title="Tag not found"
          description="This tag may have been deleted or merged."
          action={
            <Button
              variant="secondary"
              onClick={() =>
                navigate({ to: "/library/tags", search: { q: "" } })
              }
            >
              Back to tags
            </Button>
          }
        />
      </LibraryDetailView>
    );
  }

  const actions = (
    <>
      <Button variant="default" onClick={() => setRenaming(true)}>
        Rename
      </Button>
      <AppAdaptiveMenu
        label={`${tag.name} actions`}
        align="end"
        actions={[
          viewMomentsAction({ tag: tag.id }),
          {
            kind: "command",
            id: "merge",
            label: "Merge into…",
            onSelect: () => setMerging(true),
          },
          {
            kind: "command",
            id: "delete",
            label: "Delete tag…",
            destructive: true,
            separatorBefore: true,
            onSelect: () => setDeleting(true),
          },
        ]}
      />
    </>
  );

  return (
    <LibraryDetailView
      parentLabel="Tags"
      parentLink={TAGS_LINK}
      current={`#${tag.name}`}
      actions={actions}
    >
      <p className="jv-body jv-tag-detail__sub">
        {momentCount(tag.usage_count)} · added{" "}
        {formatDateMedium(tag.created_at)}
        {formatDateMedium(tag.updated_at) !== formatDateMedium(tag.created_at)
          ? ` · updated ${formatDateMedium(tag.updated_at)}`
          : ""}
      </p>

      {/* A titled group on a management surface: a stock `Card`, header action
          included — not a hand-built head + rule (DESIGN.md §5, §18). */}
      <Card
        className="jv-tag-detail__section"
        role="region"
        aria-label="Analytics"
      >
        <CardHeader>
          <CardTitle>
            <h2 className="jv-tag-detail__section-title">Usage</h2>
          </CardTitle>
          {plus.isSupporter && (
            <CardAction>
              <label
                className="jv-tag-detail__range"
                htmlFor="tag-detail-range"
              >
                <span className="sr-only">Analysis window</span>
                <NativeSelect
                  id="tag-detail-range"
                  value={days}
                  onChange={(event) => setDays(Number(event.target.value))}
                >
                  {RANGES.map((range) => (
                    <option key={range.days} value={range.days}>
                      {range.label}
                    </option>
                  ))}
                </NativeSelect>
              </label>
            </CardAction>
          )}
        </CardHeader>
        <CardContent>
          {!plus.isSupporter && (
            <StatusView
              icon={<Sparkles size={20} />}
              title={
                plus.available
                  ? "Tag analytics is part of Journiv Plus"
                  : "Tag analytics is not included in this build"
              }
              description={
                plus.available
                  ? "Supporter licences unlock usage trends, peak months and growth for every tag."
                  : "This Journiv instance was built without the Plus features module."
              }
              action={
                plus.available ? (
                  <a
                    className={cn(buttonVariants({ variant: "secondary" }))}
                    href={plus.upgradeUrl}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Learn about Plus
                  </a>
                ) : undefined
              }
            />
          )}

          {plus.isSupporter && analytics.isLoading && (
            <div className="jv-tag-detail__analytics">
              <Skeleton height="2rem" width="100%" />
              <Skeleton height="0.9rem" width="60%" />
            </div>
          )}

          {plus.isSupporter &&
            analytics.isError &&
            (isPlusLocked(analytics.error) ? (
              <StatusView
                icon={<Sparkles size={20} />}
                title="Tag analytics is unavailable"
                description="The Plus licence for this instance is inactive or could not be verified."
              />
            ) : (
              <StatusView
                role="alert"
                tone="danger"
                icon={<TriangleAlert size={20} />}
                title="Analytics could not be loaded"
                description="Check your connection and try again."
                action={
                  <Button
                    variant="secondary"
                    onClick={() => analytics.refetch()}
                  >
                    Try again
                  </Button>
                }
              />
            ))}

          {plus.isSupporter && analytics.data && (
            <TagAnalyticsView data={analytics.data} />
          )}
        </CardContent>
      </Card>

      <Card
        className="jv-tag-detail__section"
        role="region"
        aria-label="Recent moments"
      >
        <CardHeader>
          <CardTitle>
            <h2 className="jv-tag-detail__section-title">Recent moments</h2>
          </CardTitle>
          {tag.usage_count > 0 && (
            <CardAction>
              <Link
                className="jv-tag-detail__viewall jv-label"
                to="/timeline"
                search={{ q: "", tag: tag.id }}
              >
                View all
              </Link>
            </CardAction>
          )}
        </CardHeader>
        <CardContent>
          {moments.isLoading && (
            <ul className="jv-tag-moments" role="status" aria-label="Loading">
              {["a", "b", "c"].map((k) => (
                <li className="jv-tag-moments__row" key={k}>
                  <Skeleton height="0.85rem" width="30%" />
                  <Skeleton height="0.9rem" width="70%" />
                </li>
              ))}
            </ul>
          )}

          {moments.isError && (
            <StatusView
              role="alert"
              tone="danger"
              icon={<TriangleAlert size={20} />}
              title="Moments could not be loaded"
              action={
                <Button variant="secondary" onClick={() => moments.refetch()}>
                  Try again
                </Button>
              }
            />
          )}

          {moments.data && moments.data.length === 0 && (
            <p className="jv-tag-detail__empty jv-body">
              No moments carry this tag yet.
            </p>
          )}

          {moments.data && moments.data.length > 0 && (
            <ul className="jv-tag-moments">
              {moments.data.map((moment) => {
                const text =
                  moment.entry?.title?.trim() ||
                  moment.entry?.content_plain_text?.trim() ||
                  moment.note?.trim() ||
                  "No writing yet";
                const journalId = moment.entry?.journal_id;
                const body = (
                  <>
                    <span className="jv-tag-moments__date jv-meta">
                      {loggedDay(moment.logged_date_tz)}
                    </span>
                    <span className="jv-tag-moments__text jv-clamp-2">
                      {text}
                    </span>
                  </>
                );
                return (
                  <li className="jv-tag-moments__row" key={moment.id}>
                    {journalId ? (
                      <Link
                        className="jv-tag-moments__link"
                        to="/journals/$journalId/$momentId"
                        params={{ journalId, momentId: moment.id }}
                        search={{ q: "" }}
                      >
                        {body}
                      </Link>
                    ) : (
                      <span className="jv-tag-moments__link">{body}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      {renaming && (
        <TagNameDialog
          title={`Rename #${tag.name}`}
          submitLabel="Save"
          initial={tag.name}
          submitting={rename.isPending}
          failed={rename.isError}
          onClose={() => setRenaming(false)}
          onSubmit={(name) => rename.mutateAsync(name)}
        />
      )}

      {merging && (
        <MergeTagDialog
          source={tag}
          candidates={(tagsResult.data ?? []).filter((t) => t.id !== tag.id)}
          submitting={merge.isPending}
          failed={merge.isError}
          error={merge.error}
          onClose={() => setMerging(false)}
          onSubmit={(target) => merge.mutateAsync(target)}
        />
      )}

      {deleting && (
        <AppConfirmDialog
          open
          onOpenChange={(open) => !open && setDeleting(false)}
          title={`Delete #${tag.name}?`}
          description={
            tag.usage_count > 0
              ? `This removes #${tag.name} from ${momentCount(
                  tag.usage_count,
                )}. It can’t be undone.`
              : "This tag is on no moments. It can’t be undone."
          }
          confirmLabel={remove.isPending ? "Deleting…" : "Delete tag"}
          destructive
          pending={remove.isPending}
          onConfirm={() => remove.mutate()}
        >
          {remove.isError && (
            <p className="jv-library__alert" role="alert">
              The tag could not be deleted. Try again.
            </p>
          )}
        </AppConfirmDialog>
      )}
    </LibraryDetailView>
  );
}

function TagAnalyticsView({
  data,
}: {
  data: {
    usage_over_time: Record<string, number>;
    first_used?: string | null;
    last_used?: string | null;
    peak_month?: { month: string; count: number } | null;
    trend: string;
    growth_rate?: number | null;
  };
}) {
  const months = Object.keys(data.usage_over_time).sort();
  const series = months.map((m) => data.usage_over_time[m] ?? 0);
  const facts: { label: string; value: string }[] = [
    { label: "Trend", value: TREND_LABEL[data.trend] ?? data.trend },
  ];
  if (data.peak_month)
    facts.push({
      label: "Peak month",
      value: `${data.peak_month.month} (${data.peak_month.count})`,
    });
  if (typeof data.growth_rate === "number")
    facts.push({
      label: "Growth",
      value: `${data.growth_rate > 0 ? "+" : ""}${data.growth_rate.toFixed(0)}%`,
    });
  if (data.first_used)
    facts.push({
      label: "First used",
      value: formatDateMedium(data.first_used),
    });
  if (data.last_used)
    facts.push({ label: "Last used", value: formatDateMedium(data.last_used) });

  return (
    <div className="jv-tag-detail__analytics">
      {series.length > 1 ? (
        <Sparkline
          points={series}
          labels={months}
          ariaLabel="Usage over time"
        />
      ) : (
        <p className="jv-caption">Not enough history to chart yet.</p>
      )}
      <dl className="jv-tag-facts">
        {facts.map((fact) => (
          <div className="jv-tag-facts__row" key={fact.label}>
            <dt className="jv-caption">{fact.label}</dt>
            <dd className="jv-meta">{fact.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
