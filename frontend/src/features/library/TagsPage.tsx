import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  Hash,
  Plus,
  Sparkles,
  Tags as TagsIcon,
  TriangleAlert,
} from "lucide-react";
import { useId, useMemo, useState } from "react";
import { ApiError } from "../../api/client/errors";
import { api } from "../../api/client/api";
import type { TagResponse } from "../../api/generated/types.gen";
import { queryKeys } from "../../api/query/keys";
import { tagAnalyticsQuery, tagsQuery } from "../../api/query/options";
import { LibraryRow } from "../../components/journiv/LibraryRow";
import { StatusView } from "../../components/journiv/StatusView";
import { Button } from "../../components/ui/button";
import { Dialog, DialogClose } from "../../components/ui/dialog";
import { AppAdaptiveMenu } from "../../components/journiv/AppAdaptiveMenu";
import { AppConfirmDialog } from "../../components/journiv/AppConfirmDialog";
import { viewMomentsAction } from "./viewMomentsAction";
import { Input } from "../../components/ui/input";
import { SearchInput } from "../../components/ui/search-input";
import { Skeleton } from "../../components/ui/skeleton";
import { formatDateMedium } from "../../lib/datetime";
import { usePlusCapability } from "../plus/usePlusCapability";
import { LibraryWorkspace } from "./LibraryWorkspace";
import { DistributionBars, Sparkline, StatTiles } from "./tagCharts";
import "./library.css";
import "./tags.css";

type SortKey = "usage" | "name" | "recent";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "usage", label: "Most used" },
  { key: "name", label: "A–Z" },
  { key: "recent", label: "Recently added" },
];

function sortTags(tags: TagResponse[], key: SortKey): TagResponse[] {
  const copy = [...tags];
  if (key === "name") return copy.sort((a, b) => a.name.localeCompare(b.name));
  if (key === "recent")
    return copy.sort((a, b) => b.created_at.localeCompare(a.created_at));
  return copy.sort(
    (a, b) => b.usage_count - a.usage_count || a.name.localeCompare(b.name),
  );
}

function momentCount(n: number) {
  return `${n} ${n === 1 ? "moment" : "moments"}`;
}

/** A 403/503 from a Plus endpoint is a capability answer, never a screen error. */
function isPlusLocked(error: unknown): boolean {
  return (
    error instanceof ApiError && (error.status === 403 || error.status === 503)
  );
}

export function TagsPage() {
  const qc = useQueryClient();
  const plus = usePlusCapability();

  const tagsResult = useQuery(tagsQuery());
  const tags = useMemo(() => tagsResult.data ?? [], [tagsResult.data]);

  const analyticsResult = useQuery({
    ...tagAnalyticsQuery(),
    enabled: plus.isSupporter,
  });

  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("usage");
  const [creating, setCreating] = useState(false);
  const [mergeSource, setMergeSource] = useState<TagResponse>();
  const [deleteTarget, setDeleteTarget] = useState<TagResponse>();
  const [cleanupOpen, setCleanupOpen] = useState(false);

  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: queryKeys.tags }),
      qc.invalidateQueries({ queryKey: queryKeys.tagAnalytics }),
    ]);

  const createTag = useMutation({
    mutationFn: (name: string) => api.createTag({ name }),
    onSuccess: async () => {
      setCreating(false);
      await refresh();
    },
  });
  const mergeTags = useMutation({
    mutationFn: ({ source, target }: { source: string; target: string }) =>
      api.mergeTags(source, target),
    onSuccess: async () => {
      setMergeSource(undefined);
      await refresh();
    },
  });
  const removeTag = useMutation({
    mutationFn: (id: string) => api.deleteTag(id),
    onSuccess: async () => {
      setDeleteTarget(undefined);
      await refresh();
    },
  });
  const cleanup = useMutation({
    mutationFn: () => api.deleteUnusedTags(),
    onSuccess: async () => {
      setCleanupOpen(false);
      await refresh();
    },
  });

  const normalized = search.trim().toLowerCase();
  const visible = useMemo(() => {
    const filtered = normalized
      ? tags.filter((t) => t.name.includes(normalized))
      : tags;
    return sortTags(filtered, sort);
  }, [tags, normalized, sort]);

  const usedCount = tags.filter((t) => t.usage_count > 0).length;
  const unusedCount = tags.length - usedCount;
  const avgUses = tags.length
    ? tags.reduce((sum, t) => sum + t.usage_count, 0) / tags.length
    : 0;

  const loading = tagsResult.isLoading;
  const loadError = tagsResult.isError;
  const nothing = !loading && !loadError && tags.length === 0;

  return (
    <LibraryWorkspace
      title="Tags"
      actions={
        <>
          {unusedCount > 0 && (
            <Button variant="ghost" onClick={() => setCleanupOpen(true)}>
              Clean up {unusedCount} unused
            </Button>
          )}
          <Button variant="primary" onClick={() => setCreating(true)}>
            <Plus aria-hidden="true" size={16} />
            New tag
          </Button>
        </>
      }
    >
      {!loading && !loadError && tags.length > 0 && (
        <TagInsights
          total={tags.length}
          used={usedCount}
          unused={unusedCount}
          avg={avgUses}
          plus={plus}
          analytics={
            analyticsResult.data && !analyticsResult.isError
              ? analyticsResult.data
              : undefined
          }
          analyticsLocked={
            analyticsResult.isError && isPlusLocked(analyticsResult.error)
          }
        />
      )}

      <div className="jv-tags__controls">
        <SearchInput
          className="jv-tags__search"
          label="Search tags"
          placeholder="Search tags…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          onClear={() => setSearch("")}
        />
        <label className="jv-tags__sort">
          <span className="sr-only">Sort tags</span>
          <select
            className="jv-field"
            value={sort}
            onChange={(event) => setSort(event.target.value as SortKey)}
          >
            {SORTS.map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && <TagsSkeleton />}

      {loadError && (
        <StatusView
          role="alert"
          tone="danger"
          icon={<TriangleAlert size={20} />}
          title="Tags could not be loaded"
          description="Check your connection and try again."
          action={
            <Button onClick={() => tagsResult.refetch()}>Try again</Button>
          }
        />
      )}

      {nothing && (
        <StatusView
          icon={<TagsIcon size={20} />}
          title="No tags yet"
          description="Tags are created as you add them to moments. You can also start one here."
          action={
            <Button variant="primary" onClick={() => setCreating(true)}>
              <Plus aria-hidden="true" size={16} />
              New tag
            </Button>
          }
        />
      )}

      {!loading && !loadError && tags.length > 0 && visible.length === 0 && (
        <StatusView
          title="No tags found"
          description={`No tag matches “${search.trim()}”.`}
          action={<Button onClick={() => setSearch("")}>Clear search</Button>}
        />
      )}

      {visible.length > 0 && (
        <ul className="jv-lib-section__grid">
          {visible.map((tag) => (
            <LibraryRow
              key={tag.id}
              rowLink={
                <Link
                  to="/library/tags/$tagId"
                  params={{ tagId: tag.id }}
                  search={{ q: "" }}
                />
              }
              leading={<Hash aria-hidden="true" size={15} />}
              title={tag.name}
              meta={`${momentCount(tag.usage_count)} · added ${formatDateMedium(
                tag.created_at,
              )}`}
              actions={
                <AppAdaptiveMenu
                  label={`${tag.name} actions`}
                  align="end"
                  actions={[
                    viewMomentsAction({ tag: tag.id }),
                    {
                      kind: "command",
                      id: "merge",
                      label: "Merge into…",
                      onSelect: () => setMergeSource(tag),
                    },
                    {
                      kind: "command",
                      id: "delete",
                      label: "Delete tag…",
                      destructive: true,
                      separatorBefore: true,
                      onSelect: () => setDeleteTarget(tag),
                    },
                  ]}
                />
              }
            />
          ))}
        </ul>
      )}

      {creating && (
        <TagNameDialog
          title="New tag"
          submitLabel="Add tag"
          submitting={createTag.isPending}
          failed={createTag.isError}
          onClose={() => setCreating(false)}
          onSubmit={(name) => createTag.mutateAsync(name)}
        />
      )}

      {mergeSource && (
        <MergeTagDialog
          source={mergeSource}
          candidates={tags.filter((t) => t.id !== mergeSource.id)}
          submitting={mergeTags.isPending}
          failed={mergeTags.isError}
          error={mergeTags.error}
          onClose={() => setMergeSource(undefined)}
          onSubmit={(targetId) =>
            mergeTags.mutateAsync({ source: mergeSource.id, target: targetId })
          }
        />
      )}

      {deleteTarget && (
        <AppConfirmDialog
          open
          onOpenChange={(open) => !open && setDeleteTarget(undefined)}
          title={`Delete #${deleteTarget.name}?`}
          description={
            deleteTarget.usage_count > 0
              ? `This removes #${deleteTarget.name} from ${momentCount(
                  deleteTarget.usage_count,
                )}. It can’t be undone.`
              : "This tag is on no moments. It can’t be undone."
          }
          confirmLabel={removeTag.isPending ? "Deleting…" : "Delete tag"}
          destructive
          pending={removeTag.isPending}
          onConfirm={() => removeTag.mutate(deleteTarget.id)}
        >
          {removeTag.isError && (
            <p className="jv-library__alert" role="alert">
              The tag could not be deleted. Try again.
            </p>
          )}
        </AppConfirmDialog>
      )}

      {cleanupOpen && (
        <AppConfirmDialog
          open
          onOpenChange={(open) => !open && setCleanupOpen(false)}
          title="Clean up unused tags?"
          description={`This permanently deletes ${unusedCount} ${
            unusedCount === 1 ? "tag that is" : "tags that are"
          } on no moments.`}
          confirmLabel={
            cleanup.isPending ? "Deleting…" : `Delete ${unusedCount}`
          }
          destructive
          pending={cleanup.isPending}
          onConfirm={() => cleanup.mutate()}
        >
          {cleanup.isError && (
            <p className="jv-library__alert" role="alert">
              The tags could not be cleaned up. Try again.
            </p>
          )}
        </AppConfirmDialog>
      )}
    </LibraryWorkspace>
  );
}

function TagInsights({
  total,
  used,
  unused,
  avg,
  plus,
  analytics,
  analyticsLocked,
}: {
  total: number;
  used: number;
  unused: number;
  avg: number;
  plus: ReturnType<typeof usePlusCapability>;
  analytics?: {
    tag_distribution: Record<string, number>;
    usage_over_time: Record<string, number>;
  };
  analyticsLocked: boolean;
}) {
  const months = analytics ? Object.keys(analytics.usage_over_time).sort() : [];
  const series = months.map((m) => analytics?.usage_over_time[m] ?? 0);

  return (
    <section className="jv-tag-insights" aria-label="Tag insights">
      <StatTiles
        items={[
          { label: "Total", value: String(total) },
          { label: "In use", value: String(used) },
          { label: "Unused", value: String(unused) },
          { label: "Avg / tag", value: avg.toFixed(1) },
        ]}
      />

      {plus.isSupporter && analytics && (
        <div className="jv-tag-insights__plus">
          {series.length > 1 && (
            <Sparkline
              points={series}
              labels={months}
              ariaLabel="Tag usage over time"
            />
          )}
          <DistributionBars
            ariaLabel="Tag usage distribution"
            data={Object.entries(analytics.tag_distribution).map(
              ([label, value]) => ({ label, value }),
            )}
          />
        </div>
      )}

      {plus.isSupporter && analyticsLocked && (
        <p className="jv-tag-insights__note jv-caption">
          Detailed tag analytics is currently unavailable.
        </p>
      )}

      {!plus.isSupporter && plus.available && (
        <p className="jv-tag-insights__note jv-caption">
          <Sparkles aria-hidden="true" size={13} /> Usage trends and
          distribution are part of{" "}
          <a href={plus.upgradeUrl} target="_blank" rel="noreferrer">
            Journiv Plus
          </a>
          .
        </p>
      )}
    </section>
  );
}

function TagsSkeleton() {
  return (
    <ul
      className="jv-lib-section__grid"
      role="status"
      aria-label="Loading tags"
    >
      {["a", "b", "c", "d", "e", "f"].map((k) => (
        <li className="jv-lib-row" key={k}>
          <Skeleton height="0.95rem" width="1rem" />
          <span className="jv-lib-row__text">
            <Skeleton height="0.9rem" width="55%" />
            <Skeleton height="0.75rem" width="40%" />
          </span>
        </li>
      ))}
    </ul>
  );
}

function TagNameDialog({
  title,
  submitLabel,
  initial = "",
  submitting,
  failed,
  onClose,
  onSubmit,
}: {
  title: string;
  submitLabel: string;
  initial?: string;
  submitting: boolean;
  failed: boolean;
  onClose: () => void;
  onSubmit: (name: string) => Promise<unknown>;
}) {
  const inputId = useId();
  const [name, setName] = useState(initial);
  const trimmed = name.trim().toLowerCase();
  const dirty = trimmed.length > 0 && trimmed !== initial;

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={title}
      description="Tag names are lowercase and unique."
    >
      <form
        className="jv-library-form"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!dirty || submitting) return;
          try {
            await onSubmit(trimmed);
          } catch {
            // Mutation state owns the message; the typed value stays.
          }
        }}
      >
        <label htmlFor={inputId}>
          <span>Tag name</span>
          <Input
            id={inputId}
            value={name}
            maxLength={100}
            autoFocus
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        {failed && (
          <p className="jv-library__alert" role="alert">
            The tag could not be saved. Your text is still here.
          </p>
        )}
        <div className="jv-dialog__actions">
          <DialogClose render={<Button>Cancel</Button>} />
          <Button
            type="submit"
            variant="primary"
            disabled={!dirty || submitting}
          >
            {submitting ? "Saving…" : submitLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function MergeTagDialog({
  source,
  candidates,
  submitting,
  failed,
  error,
  onClose,
  onSubmit,
}: {
  source: TagResponse;
  candidates: TagResponse[];
  submitting: boolean;
  failed: boolean;
  error: unknown;
  onClose: () => void;
  onSubmit: (targetId: string) => Promise<unknown>;
}) {
  const [filter, setFilter] = useState("");
  const [target, setTarget] = useState<string>();
  const normalized = filter.trim().toLowerCase();
  const shown = normalized
    ? candidates.filter((t) => t.name.includes(normalized))
    : candidates;
  const targetTag = candidates.find((t) => t.id === target);
  const message =
    failed && error instanceof ApiError && error.status === 400
      ? "These tags can’t be merged — they may differ only by case."
      : failed
        ? "The tags could not be merged. Try again."
        : undefined;

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Merge #${source.name} into…`}
      description={
        targetTag
          ? `#${source.name} and its ${momentCount(
              source.usage_count,
            )} move into #${targetTag.name}. #${source.name} is deleted.`
          : "Pick the tag to keep. Every moment on this tag moves to it."
      }
    >
      <div className="jv-tag-merge">
        <SearchInput
          label="Filter tags"
          placeholder="Filter tags…"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          onClear={() => setFilter("")}
        />
        {shown.length === 0 ? (
          <p className="jv-tag-merge__empty jv-caption">No other tags match.</p>
        ) : (
          <ul className="jv-tag-merge__list">
            {shown.map((tag) => (
              <li key={tag.id}>
                <label className="jv-tag-merge__option">
                  <input
                    type="radio"
                    name="merge-target"
                    checked={target === tag.id}
                    onChange={() => setTarget(tag.id)}
                  />
                  <span className="jv-tag-merge__name jv-truncate">
                    #{tag.name}
                  </span>
                  <span className="jv-caption">
                    {momentCount(tag.usage_count)}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
        {message && (
          <p className="jv-library__alert" role="alert">
            {message}
          </p>
        )}
        <div className="jv-dialog__actions">
          <DialogClose render={<Button>Cancel</Button>} />
          <Button
            variant="primary"
            disabled={!target || submitting}
            onClick={async () => {
              if (!target) return;
              try {
                await onSubmit(target);
              } catch {
                // Mutation state owns the message; the selection stays.
              }
            }}
          >
            {submitting ? "Merging…" : "Merge tags"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

export { MergeTagDialog, TagNameDialog };
